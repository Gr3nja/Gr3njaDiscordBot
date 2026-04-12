from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING

from ai.client import AIClientError


if TYPE_CHECKING:
    from gr3nja_discord_bot.bot import Gr3njaBot


class SummaryCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def summary_message_logger(self, message: discord.Message) -> None:
        await self.bot.summary.log_message(message)

    @commands.Cog.listener("on_message_edit")
    async def summary_message_edit_logger(self, before: discord.Message, after: discord.Message) -> None:
        del before
        await self.bot.summary.log_message(after)

    @commands.Cog.listener("on_raw_message_delete")
    async def summary_message_delete_logger(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        await self.bot.summary.mark_deleted(payload.message_id)

    @commands.hybrid_group(name="summary", with_app_command=True, invoke_without_command=True)
    @commands.guild_only()
    async def summary_group(self, ctx: commands.Context) -> None:
        await self._send_chunks(
            ctx,
            "`recent` が使えます。\n"
            "例: `!summary recent`\n"
            "例: `!summary recent 150`",
        )

    @summary_group.command(name="recent")
    @app_commands.describe(count="要約対象にする直近メッセージ件数")
    async def summary_recent(self, ctx: commands.Context, count: int | None = None) -> None:
        if ctx.guild is None:
            await self._send_chunks(ctx, "このコマンドはサーバー内で使用してください。")
            return
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await self._send_chunks(ctx, "このチャンネルでは要約できません。")
            return
        if count is not None and count <= 0:
            await self._send_chunks(ctx, "件数は 1 以上で指定してください。")
            return

        try:
            if ctx.interaction is not None and not ctx.interaction.response.is_done():
                await ctx.interaction.response.defer()

            if ctx.interaction is None:
                async with ctx.typing():
                    result = await self.bot.summary.summarize_channel(ctx.channel, message_count=count)
            else:
                result = await self.bot.summary.summarize_channel(ctx.channel, message_count=count)
        except (AIClientError, RuntimeError, ValueError) as exc:
            await self._send_chunks(ctx, str(exc))
            return

        header = (
            f"{ctx.channel.mention} の直近 {result.message_count} 件を要約しました。\n"
            f"モデル: `{result.model_name}`\n\n"
        )
        await self._send_chunks(ctx, header + result.summary)

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
    await bot.add_cog(SummaryCog(bot))
