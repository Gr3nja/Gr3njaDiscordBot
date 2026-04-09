from __future__ import annotations

import discord
from discord.ext import commands
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from gr3nja_discord_bot.bot import Gr3njaBot


class MusicCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.command(name="play")
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        if not isinstance(ctx.author, discord.Member):
            await ctx.send("このコマンドはサーバー内で使用してください。")
            return
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("このコマンドは通常のテキストチャンネルで実行してください。")
            return
        if ctx.author.voice is None or not isinstance(ctx.author.voice.channel, discord.VoiceChannel):
            await ctx.send("先にボイスチャンネルへ参加してください。")
            return
        if not self.bot.music.available:
            await ctx.send(self.bot.music.status_message)
            return

        bot_member = ctx.guild.me
        if bot_member is None:
            await ctx.send("Bot のメンバー情報を取得できません。")
            return

        permissions = ctx.author.voice.channel.permissions_for(bot_member)
        if not permissions.connect:
            await ctx.send("この VC に接続する権限がありません。")
            return
        if not permissions.speak:
            await ctx.send("この VC で発言する権限がありません。")
            return

        async with ctx.typing():
            try:
                summary = await self.bot.music.play(
                    voice_channel=ctx.author.voice.channel,
                    text_channel=ctx.channel,
                    query=query,
                )
            except ValueError as exc:
                await ctx.send(str(exc))
                return
            except LookupError as exc:
                await ctx.send(str(exc))
                return
            except RuntimeError as exc:
                await ctx.send(str(exc))
                return
            except Exception:
                await ctx.send("音楽の再生に失敗しました。Lavalink と Bot のログを確認してください。")
                raise

        await ctx.send(summary.message)

    @commands.command(name="stop")
    @commands.guild_only()
    async def stop(self, ctx: commands.Context) -> None:
        stopped = await self.bot.music.stop(ctx.guild)
        if not stopped:
            await ctx.send("現在再生中の音楽はありません。")
            return
        await ctx.send("⏹ 音楽を停止して VC から退出しました。")


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(MusicCog(bot))
