from __future__ import annotations

import discord
from discord.ext import commands


class ReactionCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def intro_reaction_listener(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if "ducky" in message.content.casefold():
            return
        if not await self._is_intro_channel(message):
            return
        await self._try_add_intro_reaction(message)

    async def _is_intro_channel(self, message: discord.Message) -> bool:
        configured = await self.bot.db.fetchval(
            "SELECT intro_channel_id FROM guild_settings WHERE guild_id = ?",
            (message.guild.id,),
        )
        if configured:
            return configured == message.channel.id

        channel_name = message.channel.name.casefold()
        return channel_name in {"自己紹介", "introductions", "introduction"} or "intro" in channel_name

    async def _try_add_intro_reaction(self, message: discord.Message) -> None:
        emoji = await self.bot.db.fetchval(
            "SELECT intro_reaction_emoji FROM guild_settings WHERE guild_id = ?",
            (message.guild.id,),
            default=self.bot.config.intro_reaction_emoji,
        )
        emoji = emoji or self.bot.config.intro_reaction_emoji
        try:
            await message.add_reaction(emoji)
        except (discord.Forbidden, discord.HTTPException):
            return

    @commands.group(name="config", invoke_without_command=True)
    @commands.guild_only()
    async def config_group(self, ctx: commands.Context) -> None:
        await ctx.send("`intro` サブコマンドを使ってください。例: `!config intro #自己紹介 🤝`")

    @config_group.command(name="intro")
    @commands.has_permissions(manage_guild=True)
    async def config_intro(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        emoji: str | None = None,
    ) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO guild_settings (guild_id, intro_channel_id, intro_reaction_emoji)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                intro_channel_id = excluded.intro_channel_id,
                intro_reaction_emoji = COALESCE(excluded.intro_reaction_emoji, guild_settings.intro_reaction_emoji),
                updated_at = CURRENT_TIMESTAMP
            """,
            (ctx.guild.id, channel.id, emoji or self.bot.config.intro_reaction_emoji),
        )
        await ctx.send(f"自己紹介チャンネルを {channel.mention}、リアクションを `{emoji or self.bot.config.intro_reaction_emoji}` に設定しました。")


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(ReactionCog(bot))
