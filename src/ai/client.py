from __future__ import annotations

import asyncio
import json
from typing import Literal, Sequence, TypedDict

import aiohttp


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(TypedDict):
    role: ChatRole
    content: str


class AIClientError(RuntimeError):
    """Raised when the chat completion API request fails."""


class AIChatClient:
    def __init__(self, api_key: str, base_url: str, timeout_seconds: float) -> None:
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def generate_reply(
        self,
        model_name: str,
        messages: Sequence[ChatMessage],
    ) -> str:
        session = await self._get_session()
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": model_name,
            "messages": list(messages),
            "stream": False,
        }

        try:
            async with session.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                raw_body = await response.text()
                if response.status >= 400:
                    detail = _compact_text(raw_body, 280)
                    message = f"AIモデル API がエラーを返しました: {response.status} {response.reason or ''}".strip()
                    if detail:
                        message = f"{message} | {detail}"
                    raise AIClientError(message)
        except asyncio.TimeoutError as exc:
            raise AIClientError(
                f"AIモデルへのリクエストがタイムアウトしました ({self._timeout_seconds:.1f} 秒)。"
            ) from exc
        except aiohttp.ClientError as exc:
            raise AIClientError(f"AIモデルへの接続に失敗しました: {exc}") from exc

        try:
            response_payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise AIClientError("AIモデル API の応答を JSON として解釈できませんでした。") from exc

        reply = _extract_assistant_text(response_payload)
        if not reply:
            raise AIClientError("AIモデル API の応答に本文テキストが含まれていませんでした。")
        return reply.strip()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds),
            )
        return self._session


def _extract_assistant_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if isinstance(message, dict):
        content = _normalize_content(message.get("content"))
        if content:
            return content

    text = first_choice.get("text")
    if isinstance(text, str) and text.strip():
        return text

    return None


def _normalize_content(content: object) -> str | None:
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)

    merged = "".join(parts).strip()
    return merged if merged else None


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.strip().split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[:max_length]}..."
