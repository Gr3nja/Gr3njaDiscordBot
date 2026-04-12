from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord

from utils.time import parse_iso_datetime, to_local, utc_now


if TYPE_CHECKING:
    from gr3nja_discord_bot.bot import Gr3njaBot


UPSERT_MESSAGE_LOG_SQL = """
INSERT INTO message_logs (
    message_id,
    guild_id,
    channel_id,
    user_id,
    author_name,
    content,
    created_at,
    edited_at,
    deleted_at,
    is_command,
    reply_to_message_id
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
ON CONFLICT (message_id) DO UPDATE SET
    guild_id = excluded.guild_id,
    channel_id = excluded.channel_id,
    user_id = excluded.user_id,
    author_name = excluded.author_name,
    content = excluded.content,
    edited_at = excluded.edited_at,
    deleted_at = NULL,
    is_command = excluded.is_command,
    reply_to_message_id = excluded.reply_to_message_id
"""

SUMMARY_SYSTEM_PROMPT = """
あなたは Discord サーバーの会話ログを整理するアシスタントです。
回答は日本語で、ログにある事実だけを簡潔に整理してください。
話題ごとの「提起者」は、その話題を最初に出した人物を transcript から判断してください。
人物の表記は transcript に含まれる <@user_id> を優先して使ってください。
不確かな場合は断定せず「不明」と書いてください。
"""

SUMMARY_DIRECT_PROMPT_TEMPLATE = """
以下は Discord チャンネル `{channel_name}` の会話ログです。
対象メッセージ数: {message_count}
対象期間: {time_range}

次の形式で要約してください。
## 会話の流れ
- 時系列が分かるように 3-6 行

## 主な話題と提起者
- 話題名: 提起者 / 何が話されたか

## 決まったこと・次のアクション
- なければ `なし`

## 未解決
- なければ `なし`

会話ログ:
{transcript}
""".strip()

SUMMARY_CHUNK_PROMPT_TEMPLATE = """
以下は Discord チャンネル `{channel_name}` の会話ログの一部です。
全 {chunk_count} チャンク中の {chunk_index} 番目で、時系列順です。

次の形式で中間要約を作ってください。
## 流れ
- 2-4 行

## 話題と提起者
- 話題名: 提起者 / 要点

## 決まったこと・次のアクション
- なければ `なし`

## 未解決
- なければ `なし`

会話ログ:
{transcript}
""".strip()

SUMMARY_REDUCE_PROMPT_TEMPLATE = """
以下は Discord チャンネル `{channel_name}` の会話ログを、古い順に分割して作った中間要約です。
前のチャンクほど時系列的に早いので、同じ話題ならより早いチャンクに出てくる提起者を優先してください。
重複をまとめ、最終要約を作ってください。

出力形式:
## 会話の流れ
- 時系列が分かるように 3-6 行

## 主な話題と提起者
- 話題名: 提起者 / 何が話されたか

## 決まったこと・次のアクション
- なければ `なし`

## 未解決
- なければ `なし`

中間要約:
{chunk_summaries}
""".strip()

MESSAGE_CONTENT_EXCERPT_CHARS = 180
CHUNK_RESPONSE_MAX_CHARS = 1600
PRUNE_INTERVAL = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class LoggedMessage:
    message_id: int
    guild_id: int
    channel_id: int
    user_id: int
    author_name: str
    content: str
    created_at: datetime
    reply_to_message_id: int | None


@dataclass(frozen=True, slots=True)
class ChannelSummary:
    message_count: int
    summary: str
    model_name: str


class SummaryService:
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot
        self._prune_lock = asyncio.Lock()
        self._last_pruned_at: datetime | None = None

    async def log_message(self, message: discord.Message) -> None:
        row = self._build_log_row(message)
        if row is None:
            return
        await self.bot.db.execute(UPSERT_MESSAGE_LOG_SQL, row)
        await self._maybe_prune_logs()

    async def mark_deleted(self, message_id: int) -> None:
        await self.bot.db.execute(
            """
            UPDATE message_logs
            SET deleted_at = COALESCE(deleted_at, ?)
            WHERE message_id = ?
            """,
            (utc_now().isoformat(), message_id),
        )

    async def summarize_channel(
        self,
        channel: discord.TextChannel | discord.Thread,
        *,
        message_count: int | None = None,
    ) -> ChannelSummary:
        normalized_count = self._normalize_message_count(message_count)
        messages = await self._fetch_recent_messages(channel.guild.id, channel.id, normalized_count)
        if len(messages) < normalized_count and self.bot.config.summary.enable_history_backfill:
            await self._backfill_channel_history(channel, normalized_count)
            messages = await self._fetch_recent_messages(channel.guild.id, channel.id, normalized_count)

        if not messages:
            raise ValueError("要約できる通常メッセージがまだありません。少し会話がたまってから試してください。")

        chunks = self._build_transcript_chunks(messages)
        if len(chunks) == 1:
            response = await self.bot.ai.generate_one_shot(
                channel.guild.id,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=SUMMARY_DIRECT_PROMPT_TEMPLATE.format(
                    channel_name=self._format_channel_name(channel),
                    message_count=len(messages),
                    time_range=self._build_time_range(messages),
                    transcript=chunks[0],
                ),
            )
            return ChannelSummary(message_count=len(messages), summary=response.reply, model_name=response.model_name)

        chunk_summaries: list[str] = []
        for index, transcript_chunk in enumerate(chunks, start=1):
            response = await self.bot.ai.generate_one_shot(
                channel.guild.id,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=SUMMARY_CHUNK_PROMPT_TEMPLATE.format(
                    channel_name=self._format_channel_name(channel),
                    chunk_index=index,
                    chunk_count=len(chunks),
                    transcript=transcript_chunk,
                ),
                max_chars=min(self.bot.config.ai.max_response_chars, CHUNK_RESPONSE_MAX_CHARS),
            )
            chunk_summaries.append(f"[チャンク {index}]\n{response.reply}")

        final_response = await self.bot.ai.generate_one_shot(
            channel.guild.id,
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=SUMMARY_REDUCE_PROMPT_TEMPLATE.format(
                channel_name=self._format_channel_name(channel),
                chunk_summaries="\n\n".join(chunk_summaries),
            ),
        )
        return ChannelSummary(message_count=len(messages), summary=final_response.reply, model_name=final_response.model_name)

    async def _fetch_recent_messages(self, guild_id: int, channel_id: int, limit: int) -> list[LoggedMessage]:
        rows = await self.bot.db.fetchall(
            """
            SELECT
                message_id,
                guild_id,
                channel_id,
                user_id,
                author_name,
                content,
                created_at,
                reply_to_message_id
            FROM message_logs
            WHERE guild_id = ? AND channel_id = ? AND deleted_at IS NULL AND is_command = 0 AND TRIM(content) <> ''
            ORDER BY created_at DESC, message_id DESC
            LIMIT ?
            """,
            (guild_id, channel_id, limit),
        )
        messages: list[LoggedMessage] = []
        for row in reversed(rows):
            created_at = parse_iso_datetime(row["created_at"])
            if created_at is None:
                continue
            messages.append(
                LoggedMessage(
                    message_id=row["message_id"],
                    guild_id=row["guild_id"],
                    channel_id=row["channel_id"],
                    user_id=row["user_id"],
                    author_name=str(row["author_name"]),
                    content=str(row["content"]),
                    created_at=created_at,
                    reply_to_message_id=row["reply_to_message_id"],
                )
            )
        return messages

    async def _backfill_channel_history(
        self,
        channel: discord.TextChannel | discord.Thread,
        message_count: int,
    ) -> None:
        history_limit = min(max(message_count * 4, message_count), 1000)
        rows: list[tuple] = []
        try:
            async for message in channel.history(limit=history_limit, oldest_first=False):
                row = self._build_log_row(message)
                if row is not None:
                    rows.append(row)
        except (discord.Forbidden, discord.HTTPException):
            return

        if not rows:
            return

        await self.bot.db.executemany(UPSERT_MESSAGE_LOG_SQL, rows)
        await self._maybe_prune_logs(force=True)

    def _build_log_row(self, message: discord.Message) -> tuple | None:
        if message.guild is None or message.author.bot:
            return None

        content = self._normalize_message_content(message)
        author_name = getattr(message.author, "display_name", None) or message.author.name
        edited_at = message.edited_at.isoformat() if message.edited_at is not None else None
        reply_to_message_id = message.reference.message_id if message.reference is not None else None
        return (
            message.id,
            message.guild.id,
            message.channel.id,
            message.author.id,
            author_name,
            content,
            message.created_at.isoformat(),
            edited_at,
            int(bool(message.content.startswith(self.bot.config.prefix))),
            reply_to_message_id,
        )

    def _normalize_message_content(self, message: discord.Message) -> str:
        parts: list[str] = []
        normalized_text = " ".join(message.content.split())
        if normalized_text:
            parts.append(normalized_text)

        if message.attachments:
            attachment_names = ", ".join(attachment.filename for attachment in message.attachments[:3])
            more_count = len(message.attachments) - 3
            suffix = f" ほか{more_count}件" if more_count > 0 else ""
            parts.append(f"[添付: {attachment_names}{suffix}]")

        if message.stickers:
            sticker_names = ", ".join(sticker.name for sticker in message.stickers[:3])
            more_count = len(message.stickers) - 3
            suffix = f" ほか{more_count}件" if more_count > 0 else ""
            parts.append(f"[スタンプ: {sticker_names}{suffix}]")

        return " / ".join(part for part in parts if part).strip()

    def _build_transcript_chunks(self, messages: list[LoggedMessage]) -> list[str]:
        message_map = {message.message_id: message for message in messages}
        lines = [self._format_transcript_line(message, message_map) for message in messages]
        chunks: list[str] = []
        current_lines: list[str] = []
        current_length = 0

        for line in lines:
            if current_lines and current_length + len(line) + 1 > self.bot.config.summary.chunk_char_limit:
                chunks.append("\n".join(current_lines))
                current_lines = [line]
                current_length = len(line)
                continue

            current_lines.append(line)
            current_length += len(line) + 1

        if current_lines:
            chunks.append("\n".join(current_lines))
        return chunks

    def _format_transcript_line(self, message: LoggedMessage, message_map: dict[int, LoggedMessage]) -> str:
        local_dt = to_local(message.created_at, self.bot.config.default_timezone)
        timestamp = local_dt.strftime("%Y-%m-%d %H:%M")
        reply_prefix = ""
        if message.reply_to_message_id is not None:
            reply_target = message_map.get(message.reply_to_message_id)
            if reply_target is not None:
                reply_prefix = f" ↳ <@{reply_target.user_id}>"
        compact_content = self._compact_message_content(message.content)
        return f"[{timestamp}] <@{message.user_id}> {message.author_name}{reply_prefix}: {compact_content}"

    def _compact_message_content(self, content: str) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= MESSAGE_CONTENT_EXCERPT_CHARS:
            return normalized
        return f"{normalized[:MESSAGE_CONTENT_EXCERPT_CHARS]}..."

    def _build_time_range(self, messages: list[LoggedMessage]) -> str:
        first = to_local(messages[0].created_at, self.bot.config.default_timezone).strftime("%Y-%m-%d %H:%M")
        last = to_local(messages[-1].created_at, self.bot.config.default_timezone).strftime("%Y-%m-%d %H:%M")
        return f"{first} - {last}"

    def _format_channel_name(self, channel: discord.TextChannel | discord.Thread) -> str:
        if isinstance(channel, discord.Thread):
            return f"#{channel.parent.name} / {channel.name}" if channel.parent is not None else channel.name
        return f"#{channel.name}"

    def _normalize_message_count(self, message_count: int | None) -> int:
        if message_count is None:
            message_count = self.bot.config.summary.default_message_count
        return max(1, min(message_count, self.bot.config.summary.max_message_count))

    async def _maybe_prune_logs(self, *, force: bool = False) -> None:
        now = utc_now()
        if not force and self._last_pruned_at is not None and now - self._last_pruned_at < PRUNE_INTERVAL:
            return

        async with self._prune_lock:
            now = utc_now()
            if not force and self._last_pruned_at is not None and now - self._last_pruned_at < PRUNE_INTERVAL:
                return

            cutoff = (now - timedelta(days=self.bot.config.summary.log_retention_days)).isoformat()
            await self.bot.db.execute("DELETE FROM message_logs WHERE created_at < ?", (cutoff,))
            self._last_pruned_at = now
