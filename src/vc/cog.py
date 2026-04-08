from __future__ import annotations

import discord
from discord.ext import commands

from .service import VOICE_RECV_IMPORT_ERROR


class VoiceCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.group(name="voice", invoke_without_command=True)
    @commands.guild_only()
    async def voice_group(self, ctx: commands.Context) -> None:
        await ctx.send("`watch` `stop` `status` `channel` を使えます。")

    @voice_group.command(name="channel")
    @commands.has_permissions(manage_guild=True)
    async def voice_channel(self, ctx: commands.Context, channel: discord.TextChannel | None = None) -> None:
        if channel is None:
            saved = await self.bot.voice_monitors.get_clip_channel_id(ctx.guild.id)
            if saved:
                current = ctx.guild.get_channel(saved)
                if isinstance(current, discord.TextChannel):
                    await ctx.send(f"現在のクリップ送信先は {current.mention} です。")
                    return
            await ctx.send("クリップ送信先は未設定です。`!voice channel #text-channel` で設定してください。")
            return

        await self.bot.voice_monitors.set_clip_channel(ctx.guild.id, channel.id)
        await ctx.send(f"VC クリップ送信先を {channel.mention} に設定しました。")

    @voice_group.command(name="watch")
    @commands.has_permissions(manage_guild=True)
    async def voice_watch(self, ctx: commands.Context, threshold: float | None = None) -> None:
        if not self.bot.voice_monitors.available:
            await ctx.send(f"VC 監視は利用できません: `{VOICE_RECV_IMPORT_ERROR}`")
            return
        if ctx.author.voice is None or not isinstance(ctx.author.voice.channel, discord.VoiceChannel):
            await ctx.send("先に監視したいボイスチャンネルへ参加してください。")
            return
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("このコマンドは通常のテキストチャンネルで実行してください。")
            return

        clip_channel_id = await self.bot.voice_monitors.get_clip_channel_id(ctx.guild.id)
        clip_channel = ctx.guild.get_channel(clip_channel_id) if clip_channel_id else ctx.channel
        if not isinstance(clip_channel, discord.TextChannel):
            clip_channel = ctx.channel

        handle = await self.bot.voice_monitors.start_monitor(
            ctx.author.voice.channel,
            clip_channel,
            threshold=threshold,
        )
        await ctx.send(
            f"{ctx.author.voice.channel.mention} の監視を開始しました。"
            f" クリップ送信先: {clip_channel.mention} / threshold={handle.threshold:.0f}"
        )

    @voice_group.command(name="stop")
    @commands.has_permissions(manage_guild=True)
    async def voice_stop(self, ctx: commands.Context) -> None:
        stopped = await self.bot.voice_monitors.stop_monitor(ctx.guild.id)
        if not stopped:
            await ctx.send("現在 VC 監視は動いていません。")
            return
        await ctx.send("VC 監視を停止しました。")

    @voice_group.command(name="status")
    async def voice_status(self, ctx: commands.Context) -> None:
        handle = self.bot.voice_monitors.monitors.get(ctx.guild.id)
        if handle is None:
            await ctx.send("VC 監視は停止中です。")
            return

        voice_channel = ctx.guild.get_channel(handle.voice_channel_id)
        text_channel = ctx.guild.get_channel(handle.text_channel_id)
        await ctx.send(
            "VC 監視中です。\n"
            f"対象VC: {voice_channel.mention if isinstance(voice_channel, discord.VoiceChannel) else handle.voice_channel_id}\n"
            f"送信先: {text_channel.mention if isinstance(text_channel, discord.TextChannel) else handle.text_channel_id}\n"
            f"threshold: {handle.threshold:.0f}"
        )


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(VoiceCog(bot))
