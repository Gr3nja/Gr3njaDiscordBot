from __future__ import annotations

import discord
from discord.ext import commands


class WarningCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def ducky_warning_listener(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if "ducky" not in message.content.casefold():
            return
        await message.reply("焼き鳥に修正してください", mention_author=False)


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(WarningCog(bot))
