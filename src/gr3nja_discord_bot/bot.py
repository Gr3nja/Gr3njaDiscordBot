from __future__ import annotations

import logging

import discord
from discord.ext import commands

from advancement.service import AchievementAward, AchievementService
from database import Database
from money.service import EconomyService
from vc.service import VoiceMonitorService

from .config import BotConfig, load_config


LOGGER = logging.getLogger(__name__)
EXTENSIONS = (
    "advancement.cog",
    "buy.cog",
    "casino.cog",
    "event.cog",
    "money.cog",
    "reaction.cog",
    "role.cog",
    "rule.cog",
    "shiritori.cog",
    "vc.cog",
    "warning.cog",
)


class Gr3njaBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        intents.reactions = True
        intents.voice_states = True

        super().__init__(
            command_prefix=config.prefix,
            intents=intents,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            help_command=commands.DefaultHelpCommand(dm_help=False),
            activity=discord.Game(name=f"{config.prefix}help"),
        )
        self.config = config
        self.db = Database(config.database_path)
        self.achievements = AchievementService(self)
        self.economy = EconomyService(self)
        self.voice_monitors = VoiceMonitorService(self)

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init()
        await self.achievements.sync_builtin_definitions()

        for extension in EXTENSIONS:
            await self.load_extension(extension)

    async def close(self) -> None:
        await self.voice_monitors.shutdown()
        await self.db.close()
        await super().close()

    async def announce_achievements(
        self,
        channel: discord.abc.Messageable,
        member: discord.abc.User,
        awards: list[AchievementAward],
    ) -> None:
        if not awards:
            return
        lines = [f"{award.icon} **{award.name}** (+{award.points})" for award in awards]
        await channel.send(f"{member.mention} が実績を解除しました。\n" + "\n".join(lines))

    async def on_ready(self) -> None:
        if self.user is None:
            return
        LOGGER.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if ctx.command is not None and hasattr(ctx.command, "on_error"):
            return
        original = getattr(error, "original", error)
        if isinstance(original, commands.CommandNotFound):
            return
        if isinstance(original, commands.MissingPermissions):
            await ctx.send("このコマンドを使う権限がありません。")
            return
        if isinstance(original, commands.MissingRequiredArgument):
            await ctx.send(f"引数が足りません: `{original.param.name}`")
            return
        if isinstance(original, commands.BadArgument):
            await ctx.send("引数の形式が正しくありません。")
            return
        raise original


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = load_config()
    bot = Gr3njaBot(config)
    bot.run(config.token, log_handler=None)
