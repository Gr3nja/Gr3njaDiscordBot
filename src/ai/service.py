from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .client import AIChatClient, ChatMessage


if TYPE_CHECKING:
    from gr3nja_discord_bot.bot import Gr3njaBot


@dataclass(frozen=True, slots=True)
class AIModelDefinition:
    key: str
    label: str
    aliases: tuple[str, ...]


MODEL_DEFINITIONS: tuple[AIModelDefinition, ...] = (
    AIModelDefinition(key="gemini", label="Gemini", aliases=("gemini",)),
    AIModelDefinition(
        key="gpt-oss:20b",
        label="gpt-oss:20b",
        aliases=("gpt-oss:20b", "gpt-oss", "gptoss", "gpt_oss"),
    ),
    AIModelDefinition(
        key="gemma3:27b",
        label="Gemma3:27b",
        aliases=("gemma3:27b", "gemma3", "gemma-3:27b", "gemma-3"),
    ),
)


@dataclass(frozen=True, slots=True)
class ConversationScope:
    guild_id: int
    channel_id: int
    user_id: int


@dataclass(frozen=True, slots=True)
class GuildModel:
    key: str
    label: str
    api_model_name: str
    is_override: bool


@dataclass(frozen=True, slots=True)
class AIResponse:
    reply: str
    model_name: str


class AIService:
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot
        self._client = AIChatClient(
            api_key=bot.config.ai.api_key,
            base_url=bot.config.ai.base_url,
            timeout_seconds=bot.config.ai.request_timeout_seconds,
        )
        self._locks: dict[ConversationScope, asyncio.Lock] = {}

    @property
    def is_available(self) -> bool:
        return self.bot.config.ai.is_configured

    async def close(self) -> None:
        await self._client.close()

    def list_available_models(self) -> tuple[AIModelDefinition, ...]:
        return MODEL_DEFINITIONS

    async def get_model_status(self, guild_id: int) -> GuildModel:
        row = await self.bot.db.fetchone(
            """
            SELECT model_name
            FROM ai_guild_settings
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        if row is not None:
            selected = self._normalize_model_key(str(row["model_name"]))
            if selected is not None:
                return self._build_guild_model(selected, is_override=True)
        return self._build_guild_model(self.bot.config.ai.default_model, is_override=False)

    async def set_model(self, guild_id: int, model_name: str) -> GuildModel:
        normalized = model_name.strip()
        if not normalized:
            raise ValueError("モデル名は空にできません。")

        if normalized.casefold() in {"default", "reset", "既定"}:
            await self.bot.db.execute(
                "DELETE FROM ai_guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            return self._build_guild_model(self.bot.config.ai.default_model, is_override=False)

        model_key = self._normalize_model_key(normalized)
        if model_key is None:
            raise ValueError(
                "使用できるモデルは `gemini` / `gpt-oss:20b` / `gemma3:27b` の3種類だけです。"
            )

        default_key = self._normalize_model_key(self.bot.config.ai.default_model) or MODEL_DEFINITIONS[0].key
        if model_key == default_key:
            await self.bot.db.execute(
                "DELETE FROM ai_guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            return self._build_guild_model(model_key, is_override=False)

        await self.bot.db.execute(
            """
            INSERT INTO ai_guild_settings (guild_id, model_name)
            VALUES (?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                model_name = excluded.model_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, model_key),
        )
        return self._build_guild_model(model_key, is_override=True)

    async def generate_reply(self, scope: ConversationScope, user_message: str) -> AIResponse:
        if not self.is_available:
            raise RuntimeError("AI機能は未設定です。`.env` に `AI_BASE_URL` を設定してください。")

        normalized_user_message = user_message.strip()
        if not normalized_user_message:
            raise ValueError("メッセージは空にできません。")

        model = await self.get_model_status(scope.guild_id)
        if not model.api_model_name.strip():
            raise RuntimeError(
                "AIモデルが未設定です。`.env` の `AI_DEFAULT_MODEL` か `/ai model <modelname>` を設定してください。"
            )

        async with self._get_lock(scope):
            history = await self._fetch_history(scope)
            messages: list[ChatMessage] = []
            system_prompt = self.bot.config.ai.system_prompt.strip()
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.extend(history)
            messages.append({"role": "user", "content": normalized_user_message})

            reply = await self._client.generate_reply(model.api_model_name, messages)
            trimmed_reply = _limit_text(reply, self.bot.config.ai.max_response_chars)
            await self._append_turn(scope, normalized_user_message, trimmed_reply)
            return AIResponse(reply=trimmed_reply, model_name=model.label)

    async def _fetch_history(self, scope: ConversationScope) -> list[ChatMessage]:
        max_messages = max(0, self.bot.config.ai.max_history_turns * 2)
        if max_messages == 0:
            return []

        rows = await self.bot.db.fetchall(
            """
            SELECT role, content
            FROM ai_conversation_messages
            WHERE guild_id = ? AND channel_id = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (scope.guild_id, scope.channel_id, scope.user_id, max_messages),
        )

        history: list[ChatMessage] = []
        for row in reversed(rows):
            role = str(row["role"])
            if role not in {"user", "assistant"}:
                continue
            history.append({"role": role, "content": str(row["content"])})
        return history

    async def _append_turn(
        self,
        scope: ConversationScope,
        user_message: str,
        assistant_message: str,
    ) -> None:
        rows = [
            (scope.guild_id, scope.channel_id, scope.user_id, "user", user_message),
            (scope.guild_id, scope.channel_id, scope.user_id, "assistant", assistant_message),
        ]
        await self.bot.db.executemany(
            """
            INSERT INTO ai_conversation_messages (guild_id, channel_id, user_id, role, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )

        max_messages = max(2, self.bot.config.ai.max_history_turns * 2)
        await self.bot.db.execute(
            """
            DELETE FROM ai_conversation_messages
            WHERE guild_id = ? AND channel_id = ? AND user_id = ?
              AND id NOT IN (
                  SELECT id
                  FROM ai_conversation_messages
                  WHERE guild_id = ? AND channel_id = ? AND user_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (
                scope.guild_id,
                scope.channel_id,
                scope.user_id,
                scope.guild_id,
                scope.channel_id,
                scope.user_id,
                max_messages,
            ),
        )

    def _get_lock(self, scope: ConversationScope) -> asyncio.Lock:
        lock = self._locks.get(scope)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[scope] = lock
        return lock

    def _build_guild_model(self, raw_model_key: str, *, is_override: bool) -> GuildModel:
        model_key = self._normalize_model_key(raw_model_key) or MODEL_DEFINITIONS[0].key
        definition = self._get_definition(model_key)
        return GuildModel(
            key=definition.key,
            label=definition.label,
            api_model_name=self._resolve_api_model_name(definition.key),
            is_override=is_override,
        )

    def _normalize_model_key(self, value: str) -> str | None:
        normalized = value.strip().casefold()
        if not normalized:
            return None

        model_name_candidates = {
            self.bot.config.ai.gemini_model.strip().casefold(): "gemini",
            self.bot.config.ai.gpt_oss_20b_model.strip().casefold(): "gpt-oss:20b",
            self.bot.config.ai.gemma3_27b_model.strip().casefold(): "gemma3:27b",
        }
        mapped_key = model_name_candidates.get(normalized)
        if mapped_key:
            return mapped_key

        for definition in MODEL_DEFINITIONS:
            if normalized == definition.key.casefold() or normalized in definition.aliases:
                return definition.key
        return None

    def _resolve_api_model_name(self, model_key: str) -> str:
        if model_key == "gemini":
            return self.bot.config.ai.gemini_model
        if model_key == "gpt-oss:20b":
            return self.bot.config.ai.gpt_oss_20b_model
        if model_key == "gemma3:27b":
            return self.bot.config.ai.gemma3_27b_model
        return ""

    def _get_definition(self, model_key: str) -> AIModelDefinition:
        for definition in MODEL_DEFINITIONS:
            if definition.key == model_key:
                return definition
        return MODEL_DEFINITIONS[0]


def _limit_text(text: str, max_chars: int) -> str:
    normalized = text.strip()
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized

    notice = "\n\n[...応答が長いため省略しました...]"
    available = max(0, max_chars - len(notice))
    return f"{normalized[:available]}{notice}"
