from __future__ import annotations

import discord
from discord.ext import commands

from utils.time import format_local


class MoneyCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def reward_message_listener(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not message.content.strip() or message.content.startswith(self.bot.config.prefix):
            return
        if "ducky" in message.content.casefold():
            return
        if len(message.content.strip()) < 2:
            return

        await self.bot.economy.reward_message(message.guild.id, message.author.id)
        awards = await self.bot.achievements.record_message(message.guild.id, message.author.id)
        await self.bot.announce_achievements(message.channel, message.author, awards)

    @commands.command(name="money")
    @commands.guild_only()
    async def money(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        target = member or ctx.author
        wallet = await self.bot.economy.get_wallet(ctx.guild.id, target.id)
        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        await ctx.send(f"{target.mention} の所持金: **{wallet.balance} {currency}**")

    @commands.command(name="daily")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context) -> None:
        claimed, wallet, last_claimed = await self.bot.economy.claim_daily(ctx.guild.id, ctx.author.id)
        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        if not claimed:
            formatted = format_local(last_claimed, self.bot.config.default_timezone) if last_claimed else "不明"
            await ctx.send(f"今日はもう受け取り済みです。最終受け取り: {formatted}")
            return

        awards = await self.bot.achievements.evaluate_auto_achievements(ctx.guild.id, ctx.author.id)
        await ctx.send(f"{self.bot.config.daily_reward} {currency} を受け取りました。現在残高: {wallet.balance} {currency}")
        await self.bot.announce_achievements(ctx.channel, ctx.author, awards)


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(MoneyCog(bot))
