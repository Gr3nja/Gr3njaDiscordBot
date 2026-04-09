from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING

from .client import AIClientError
from .service import ConversationScope


if TYPE_CHECKING:
    from gr3nja_discord_bot.bot import Gr3njaBot


class AICog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.hybrid_group(name="ai", with_app_command=True, invoke_without_command=True)
    async def ai_group(self, ctx: commands.Context) -> None:
        """AI 機能の親コマンドです。"""
        if ctx.guild is None:
            await self._send_chunks(ctx, "このコマンドはサーバー内で使用してください。")
            return
        await self._send_chunks(
            ctx,
            "`chat` と `model` が使えます。\n"
            "例: `/ai chat こんにちは` または `!ai chat こんにちは`\n"
            "例: `/ai model gemini`\n"
            "使用可能モデル: `gemini` / `gpt-oss:20b` / `gemma3:27b`",
        )

    @ai_group.command(name="chat")
    @app_commands.describe(message="AI に送るメッセージ")
    async def ai_chat(self, ctx: commands.Context, *, message: str) -> None:
        """AI にメッセージを送り、会話履歴つきで応答を返します。"""
        if ctx.guild is None or ctx.channel is None:
            await self._send_chunks(ctx, "このコマンドはサーバー内で使用してください。")
            return

        normalized = message.strip()
        if not normalized:
            await self._send_chunks(ctx, "メッセージは空にできません。")
            return

        try:
            if ctx.interaction is not None and not ctx.interaction.response.is_done():
                await ctx.interaction.response.defer()

            if ctx.interaction is None:
                async with ctx.typing():
                    response = await self.bot.ai.generate_reply(
                        ConversationScope(
                            guild_id=ctx.guild.id,
                            channel_id=ctx.channel.id,
                            user_id=ctx.author.id,
                        ),
                        normalized,
                    )
            else:
                response = await self.bot.ai.generate_reply(
                    ConversationScope(
                        guild_id=ctx.guild.id,
                        channel_id=ctx.channel.id,
                        user_id=ctx.author.id,
                    ),
                    normalized,
                )
        except (AIClientError, RuntimeError, ValueError) as exc:
            await self._send_chunks(ctx, str(exc))
            return

        await self._send_chunks(ctx, response.reply)

    @ai_group.command(name="model")
    @app_commands.describe(model_name="設定するモデル名。省略時は現在値を表示")
    @app_commands.choices(
        model_name=[
            app_commands.Choice(name="Gemini", value="gemini"),
            app_commands.Choice(name="gpt-oss:20b", value="gpt-oss:20b"),
            app_commands.Choice(name="Gemma3:27b", value="gemma3:27b"),
        ]
    )
    async def ai_model(self, ctx: commands.Context, *, model_name: str | None = None) -> None:
        """現在の AI モデルを表示、またはサーバー単位で変更します。"""
        if ctx.guild is None:
            await self._send_chunks(ctx, "このコマンドはサーバー内で使用してください。")
            return

        normalized = model_name.strip() if model_name is not None else ""
        if not normalized:
            current = await self.bot.ai.get_model_status(ctx.guild.id)
            source = "サーバー設定" if current.is_override else "既定値"
            lines = [
                f"現在のAIモデル: `{current.label}` ({source})",
                "選択可能: `gemini` / `gpt-oss:20b` / `gemma3:27b`",
            ]
            if not self.bot.ai.is_available:
                lines.append("AI機能は未設定です。`.env` に `AI_BASE_URL` を設定してください。")
            elif not current.api_model_name:
                lines.append(
                    "モデル名が未設定です。`.env` の `AI_DEFAULT_MODEL` か `/ai model <modelname>` を設定してください。"
                )
            elif current.api_model_name != current.key:
                lines.append(f"実APIモデル: `{current.api_model_name}`")
            await self._send_chunks(ctx, "\n".join(lines))
            return

        author = ctx.author
        if not isinstance(author, discord.Member) or not author.guild_permissions.manage_guild:
            await self._send_chunks(ctx, "モデル変更にはサーバー管理権限が必要です。")
            return

        try:
            current = await self.bot.ai.set_model(ctx.guild.id, normalized)
        except ValueError as exc:
            await self._send_chunks(ctx, str(exc))
            return

        if current.is_override:
            lines = [f"AIモデルを `{current.label}` に変更しました。"]
        else:
            lines = [f"AIモデルを既定値 `{current.label}` に戻しました。"]

        if current.api_model_name != current.key:
            lines.append(f"実APIモデル: `{current.api_model_name}`")

        if not self.bot.ai.is_available:
            lines.append("設定は保存されましたが、AI機能を使うには `.env` の `AI_BASE_URL` 設定が必要です。")

        await self._send_chunks(ctx, "\n".join(lines))

    async def _send_chunks(self, ctx: commands.Context, content: str) -> None:
        chunks = _split_for_discord(content)
        if ctx.interaction is not None:
            if ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(chunks[0])
            else:
                await ctx.interaction.response.send_message(chunks[0])
            for chunk in chunks[1:]:
                await ctx.interaction.followup.send(chunk)
            return

        for chunk in chunks:
            await ctx.send(chunk)


def _split_for_discord(content: str, max_length: int = 1900) -> list[str]:
    text = content.strip()
    if not text:
        return ["（応答が空でした）"]
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        candidate = remaining[:max_length]
        split_at = _find_split_point(candidate)
        chunk = remaining[:split_at].strip()
        chunks.append(chunk or candidate)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


def _find_split_point(text: str) -> int:
    minimum = int(len(text) * 0.6)
    for separator in ("\n\n", "\n", " "):
        index = text.rfind(separator)
        if index >= minimum:
            return index + len(separator)
    return len(text)


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(AICog(bot))
