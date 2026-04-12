from __future__ import annotations

import logging

import discord
from discord.ext import commands

from ai.service import AIService
from advancement.service import AchievementAward, AchievementService
from database import Database
from music.service import MusicService
from summary.service import SummaryService
from money.service import EconomyService
from vc.service import VoiceMonitorService

from .config import BotConfig, load_config


LOGGER = logging.getLogger(__name__)
EXTENSIONS = (
    "ai.cog",
    "advancement.cog",
    "buy.cog",
    "casino.cog",
    "event.cog",
    "music.cog",
    "money.cog",
    "reaction.cog",
    "role.cog",
    "rule.cog",
    "shiritori.cog",
    "summary.cog",
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
        self.ai = AIService(self)
        self.achievements = AchievementService(self)
        self.economy = EconomyService(self)
        self.music = MusicService(self)
        self.summary = SummaryService(self)
        self.voice_monitors = VoiceMonitorService(self)

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init()
        await self.achievements.sync_builtin_definitions()
        await self.music.connect()

        for extension in EXTENSIONS:
            await self.load_extension(extension)

        try:
            synced_commands = await self.tree.sync()
            LOGGER.info("Synced %s application commands.", len(synced_commands))
        except discord.DiscordException:
            LOGGER.exception("Failed to sync application commands.")

    async def close(self) -> None:
        await self.voice_monitors.shutdown()
        await self.music.shutdown()
        await self.ai.close()
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

    async def on_track_end(self, event) -> None:
        await self.music.handle_track_end(event)

    async def on_track_exception(self, event) -> None:
        await self.music.handle_track_exception(event)

    async def on_track_stuck(self, event) -> None:
        await self.music.handle_track_stuck(event)

    async def on_node_ready(self, node) -> None:
        LOGGER.info("Lavalink node ready: %s (%s:%s)", getattr(node, "label", "unknown"), getattr(node, "host", "unknown"), getattr(node, "port", "unknown"))

    async def on_node_unavailable(self, node) -> None:
        LOGGER.warning("Lavalink node unavailable: %s", getattr(node, "label", "unknown"))

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
