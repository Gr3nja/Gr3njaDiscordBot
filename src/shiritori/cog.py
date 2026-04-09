from __future__ import annotations

import json
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from .text import first_kana, last_kana, normalize_shiritori_word


@dataclass(slots=True)
class ShiritoriSession:
    channel_id: int
    guild_id: int
    started_by: int
    last_word: str | None = None
    last_kana: str | None = None
    used_words: set[str] = field(default_factory=set)
    chain_length: int = 0
    last_player_id: int | None = None


class ShiritoriCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot
        self.sessions: dict[int, ShiritoriSession] = {}

    async def cog_load(self) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT channel_id, guild_id, started_by, last_word, last_kana, used_words_json, chain_length, last_player_id
            FROM shiritori_sessions
            WHERE active = 1
            """
        )
        for row in rows:
            self.sessions[row["channel_id"]] = ShiritoriSession(
                channel_id=row["channel_id"],
                guild_id=row["guild_id"],
                started_by=row["started_by"],
                last_word=row["last_word"],
                last_kana=row["last_kana"],
                used_words=set(json.loads(row["used_words_json"])),
                chain_length=row["chain_length"],
                last_player_id=row["last_player_id"],
            )

    @commands.group(name="shiritori", invoke_without_command=True)
    @commands.guild_only()
    async def shiritori_group(self, ctx: commands.Context) -> None:
        await ctx.send("`start` `stop` `status` `ranking` が使えます。")

    @shiritori_group.command(name="start")
    async def shiritori_start(self, ctx: commands.Context) -> None:
        if ctx.channel.id in self.sessions:
            await ctx.send("このチャンネルでは既にしりとりが進行中です。")
            return

        session = ShiritoriSession(channel_id=ctx.channel.id, guild_id=ctx.guild.id, started_by=ctx.author.id)
        self.sessions[ctx.channel.id] = session
        await self._save_session(session)
        await ctx.send("しりとりを開始しました。ひらがな・カタカナで送ってください。")

    @shiritori_group.command(name="stop")
    async def shiritori_stop(self, ctx: commands.Context) -> None:
        session = self.sessions.pop(ctx.channel.id, None)
        if session is None:
            await ctx.send("このチャンネルではしりとりが動いていません。")
            return

        await self.bot.db.execute(
            "UPDATE shiritori_sessions SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE channel_id = ?",
            (ctx.channel.id,),
        )
        await ctx.send("しりとりを停止しました。")

    @shiritori_group.command(name="status")
    async def shiritori_status(self, ctx: commands.Context) -> None:
        session = self.sessions.get(ctx.channel.id)
        if session is None:
            await ctx.send("このチャンネルではしりとりが動いていません。")
            return
        await ctx.send(
            f"現在のしりとり\n"
            f"最後の単語: `{session.last_word or 'なし'}`\n"
            f"次の頭文字: `{session.last_kana or '自由'}`\n"
            f"チェーン: {session.chain_length}"
        )

    @shiritori_group.command(name="ranking")
    async def shiritori_ranking(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, plays, wins, losses, longest_chain
            FROM shiritori_scores
            WHERE guild_id = ?
            ORDER BY wins DESC, longest_chain DESC, plays DESC
            LIMIT 10
            """,
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("しりとりランキングはまだありません。")
            return

        lines = [
            f"{index}. <@{row['user_id']}> - wins:{row['wins']} plays:{row['plays']} longest:{row['longest_chain']}"
            for index, row in enumerate(rows, start=1)
        ]
        await ctx.send("しりとりランキング\n" + "\n".join(lines))

    @commands.Cog.listener("on_message")
    async def shiritori_listener(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if message.content.startswith(self.bot.config.prefix):
            return
        if "ducky" in message.content.casefold():
            return

        session = self.sessions.get(message.channel.id)
        if session is None:
            return

        normalized = normalize_shiritori_word(message.content)
        if not normalized:
            return

        first = first_kana(normalized)
        last = last_kana(normalized)
        if first is None or last is None:
            return

        if session.last_kana and first != session.last_kana:
            await message.reply(f"その単語は `{session.last_kana}` から始まっていません。", mention_author=False)
            return
        if normalized in session.used_words:
            await message.reply("その単語はもう使われています。", mention_author=False)
            return

        if last == "ん":
            await self._record_loss(message, session, normalized)
            return

        session.last_word = normalized
        session.last_kana = last
        session.used_words.add(normalized)
        session.chain_length += 1
        session.last_player_id = message.author.id
        await self._save_session(session)

        await self.bot.db.execute(
            """
            INSERT INTO shiritori_scores (guild_id, user_id, plays, longest_chain)
            VALUES (?, ?, 1, ?)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                plays = plays + 1,
                longest_chain = MAX(longest_chain, excluded.longest_chain)
            """,
            (message.guild.id, message.author.id, session.chain_length),
        )
        await self.bot.economy.add_balance(message.guild.id, message.author.id, self.bot.config.shiritori_reward)
        awards = await self.bot.achievements.record_shiritori_play(message.guild.id, message.author.id, won=False)
        await self.bot.announce_achievements(message.channel, message.author, awards)

        try:
            await message.add_reaction("⭕")
        except (discord.Forbidden, discord.HTTPException):
            return

    async def _record_loss(self, message: discord.Message, session: ShiritoriSession, normalized: str) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO shiritori_scores (guild_id, user_id, plays, losses)
            VALUES (?, ?, 1, 1)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                plays = plays + 1,
                losses = losses + 1
            """,
            (message.guild.id, message.author.id),
        )
        loser_awards = await self.bot.achievements.record_shiritori_play(message.guild.id, message.author.id, won=False)
        await self.bot.announce_achievements(message.channel, message.author, loser_awards)

        winner_message = ""
        if session.last_player_id and session.last_player_id != message.author.id:
            await self.bot.db.execute(
                """
                INSERT INTO shiritori_scores (guild_id, user_id, wins)
                VALUES (?, ?, 1)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET
                    wins = wins + 1
                """,
                (message.guild.id, session.last_player_id),
            )
            await self.bot.achievements.increment_counter(message.guild.id, session.last_player_id, "shiritori_wins", 1)
            winner_awards = await self.bot.achievements.evaluate_auto_achievements(message.guild.id, session.last_player_id)
            if winner_awards:
                winner = message.guild.get_member(session.last_player_id)
                if winner is not None:
                    await self.bot.announce_achievements(message.channel, winner, winner_awards)
            winner_message = f"\n今回の勝者: <@{session.last_player_id}>"

        session.last_word = None
        session.last_kana = None
        session.used_words.clear()
        session.chain_length = 0
        session.last_player_id = None
        await self._save_session(session)
        await message.reply(
            f"`{normalized}` は `ん` で終わったのでラウンド終了です。{winner_message}\n新しい単語で再開できます。",
            mention_author=False,
        )

    async def _save_session(self, session: ShiritoriSession) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO shiritori_sessions
                (channel_id, guild_id, last_word, last_kana, used_words_json, chain_length, last_player_id, started_by, active)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT (channel_id) DO UPDATE SET
                guild_id = excluded.guild_id,
                last_word = excluded.last_word,
                last_kana = excluded.last_kana,
                used_words_json = excluded.used_words_json,
                chain_length = excluded.chain_length,
                last_player_id = excluded.last_player_id,
                started_by = excluded.started_by,
                active = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                session.channel_id,
                session.guild_id,
                session.last_word,
                session.last_kana,
                json.dumps(sorted(session.used_words), ensure_ascii=False),
                session.chain_length,
                session.last_player_id,
                session.started_by,
            ),
        )


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(ShiritoriCog(bot))
