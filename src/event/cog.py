from __future__ import annotations

from datetime import timedelta

import discord
from discord.ext import commands, tasks

from utils.time import format_local, parse_iso_datetime, parse_user_datetime, utc_now


class EventCog(commands.Cog):
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        if self.reminder_loop.is_running():
            self.reminder_loop.cancel()

    @commands.Cog.listener("on_ready")
    async def ensure_reminder_loop(self) -> None:
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()

    @commands.group(name="event", invoke_without_command=True)
    @commands.guild_only()
    async def event_group(self, ctx: commands.Context) -> None:
        await ctx.send(
            "`create` `list` `info` `join` `leave` `cancel` `complete` が使えます。\n"
            "例: `!event create 2026-04-10T21:00 100 20 ゲーム会 | 金曜夜の対戦会`"
        )

    @event_group.command(name="create")
    async def event_create(
        self,
        ctx: commands.Context,
        when: str,
        reward: int | None = None,
        max_participants: int | None = None,
        *,
        payload: str,
    ) -> None:
        title, separator, description = payload.partition("|")
        title = title.strip()
        description = description.strip()
        if not title:
            await ctx.send("形式: `!event create <日時> <報酬> <上限> タイトル | 説明`")
            return

        try:
            starts_at = parse_user_datetime(when, self.bot.config.default_timezone)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        if starts_at <= utc_now():
            await ctx.send("未来の日時を指定してください。")
            return

        reward_value = reward if reward is not None else self.bot.config.event_default_reward
        if reward_value < 0:
            await ctx.send("報酬は 0 以上で指定してください。")
            return
        limit_value = None if max_participants in (None, 0) else max_participants
        if limit_value is not None and limit_value < 0:
            await ctx.send("参加上限は 0 以上で指定してください。")
            return

        cursor = await self.bot.db.execute(
            """
            INSERT INTO events
                (guild_id, channel_id, title, description, starts_at, reward, max_participants, creator_id)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ctx.guild.id,
                ctx.channel.id,
                title,
                description,
                starts_at.isoformat(),
                reward_value,
                limit_value,
                ctx.author.id,
            ),
        )
        event_id = int(cursor.lastrowid)
        await ctx.send(
            f"イベント `{event_id}` を作成しました。\n"
            f"タイトル: **{title}**\n"
            f"開始: {format_local(starts_at, self.bot.config.default_timezone)}\n"
            f"報酬: {reward_value} {await self.bot.economy.get_currency_name(ctx.guild.id)}"
        )

    @event_group.command(name="list")
    async def event_list(self, ctx: commands.Context) -> None:
        rows = await self.bot.db.fetchall(
            """
            SELECT
                e.id,
                e.title,
                e.starts_at,
                e.reward,
                e.max_participants,
                e.cancelled_at,
                e.completed_at,
                COALESCE((SELECT COUNT(*) FROM event_participants ep WHERE ep.event_id = e.id), 0) AS participant_count
            FROM events e
            WHERE e.guild_id = ?
            ORDER BY e.starts_at ASC
            LIMIT 20
            """,
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.send("イベントはまだありません。")
            return

        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        lines = []
        for row in rows:
            status = "終了" if row["completed_at"] else "中止" if row["cancelled_at"] else "募集中"
            limit_text = row["max_participants"] or "∞"
            lines.append(
                f"`{row['id']}` [{status}] **{row['title']}** "
                f"- {format_local(parse_iso_datetime(row['starts_at']), self.bot.config.default_timezone)} "
                f"/ {row['participant_count']}/{limit_text}人 / {row['reward']} {currency}"
            )
        await ctx.send("\n".join(lines))

    @event_group.command(name="info")
    async def event_info(self, ctx: commands.Context, event_id: int) -> None:
        row = await self._fetch_event(ctx.guild.id, event_id)
        if row is None:
            await ctx.send("イベントが見つかりません。")
            return

        participants = await self.bot.db.fetchall(
            "SELECT user_id FROM event_participants WHERE event_id = ? ORDER BY joined_at ASC",
            (event_id,),
        )
        mention_list = " ".join(f"<@{item['user_id']}>" for item in participants) or "なし"
        await ctx.send(
            f"`{row['id']}` **{row['title']}**\n"
            f"開始: {format_local(parse_iso_datetime(row['starts_at']), self.bot.config.default_timezone)}\n"
            f"作成者: <@{row['creator_id']}>\n"
            f"説明: {row['description'] or 'なし'}\n"
            f"参加者: {mention_list}"
        )

    @event_group.command(name="join")
    async def event_join(self, ctx: commands.Context, event_id: int) -> None:
        row = await self._fetch_event(ctx.guild.id, event_id)
        if row is None or row["completed_at"] or row["cancelled_at"]:
            await ctx.send("参加できるイベントが見つかりません。")
            return

        current_count = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM event_participants WHERE event_id = ?",
            (event_id,),
            default=0,
        )
        if row["max_participants"] and current_count >= row["max_participants"]:
            already_joined = await self.bot.db.fetchval(
                "SELECT 1 FROM event_participants WHERE event_id = ? AND user_id = ?",
                (event_id, ctx.author.id),
                default=0,
            )
            if not already_joined:
                await ctx.send("そのイベントは満員です。")
                return

        cursor = await self.bot.db.execute(
            """
            INSERT INTO event_participants (event_id, user_id)
            VALUES (?, ?)
            ON CONFLICT (event_id, user_id) DO NOTHING
            """,
            (event_id, ctx.author.id),
        )
        if cursor.rowcount == 0:
            await ctx.send("既に参加しています。")
            return

        awards = await self.bot.achievements.record_event_join(ctx.guild.id, ctx.author.id)
        await ctx.send(f"{ctx.author.mention} をイベント `{event_id}` に追加しました。")
        await self.bot.announce_achievements(ctx.channel, ctx.author, awards)

    @event_group.command(name="leave")
    async def event_leave(self, ctx: commands.Context, event_id: int) -> None:
        cursor = await self.bot.db.execute(
            "DELETE FROM event_participants WHERE event_id = ? AND user_id = ?",
            (event_id, ctx.author.id),
        )
        if cursor.rowcount == 0:
            await ctx.send("そのイベントには参加していません。")
            return
        await ctx.send(f"イベント `{event_id}` から退出しました。")

    @event_group.command(name="cancel")
    async def event_cancel(self, ctx: commands.Context, event_id: int) -> None:
        row = await self._fetch_event(ctx.guild.id, event_id)
        if row is None:
            await ctx.send("イベントが見つかりません。")
            return
        if not await self._can_manage_event(ctx, row):
            await ctx.send("作成者またはサーバー管理権限が必要です。")
            return

        await self.bot.db.execute(
            "UPDATE events SET cancelled_at = ? WHERE id = ? AND guild_id = ?",
            (utc_now().isoformat(), event_id, ctx.guild.id),
        )
        await ctx.send(f"イベント `{event_id}` を中止しました。")

    @event_group.command(name="complete")
    async def event_complete(self, ctx: commands.Context, event_id: int) -> None:
        row = await self._fetch_event(ctx.guild.id, event_id)
        if row is None:
            await ctx.send("イベントが見つかりません。")
            return
        if not await self._can_manage_event(ctx, row):
            await ctx.send("作成者またはサーバー管理権限が必要です。")
            return
        if row["completed_at"]:
            await ctx.send("そのイベントは既に完了済みです。")
            return

        participants = await self.bot.db.fetchall(
            "SELECT user_id FROM event_participants WHERE event_id = ?",
            (event_id,),
        )
        reward = row["reward"]
        if reward > 0:
            for participant in participants:
                await self.bot.economy.add_balance(ctx.guild.id, participant["user_id"], reward)

        await self.bot.db.execute(
            "UPDATE events SET completed_at = ? WHERE id = ? AND guild_id = ?",
            (utc_now().isoformat(), event_id, ctx.guild.id),
        )
        mentions = " ".join(f"<@{item['user_id']}>" for item in participants) or "参加者なし"
        currency = await self.bot.economy.get_currency_name(ctx.guild.id)
        await ctx.send(
            f"イベント `{event_id}` を完了しました。\n"
            f"参加者: {mentions}\n"
            f"付与報酬: {reward} {currency}"
        )

    async def _fetch_event(self, guild_id: int, event_id: int):
        return await self.bot.db.fetchone(
            """
            SELECT *
            FROM events
            WHERE guild_id = ? AND id = ?
            """,
            (guild_id, event_id),
        )

    async def _can_manage_event(self, ctx: commands.Context, row) -> bool:
        return bool(ctx.author.guild_permissions.manage_guild or row["creator_id"] == ctx.author.id)

    @tasks.loop(minutes=1)
    async def reminder_loop(self) -> None:
        now = utc_now()
        rows = await self.bot.db.fetchall(
            """
            SELECT id, guild_id, channel_id, title, starts_at
            FROM events
            WHERE completed_at IS NULL AND cancelled_at IS NULL
            """,
        )

        for row in rows:
            starts_at = parse_iso_datetime(row["starts_at"])
            if starts_at is None or starts_at <= now:
                continue

            delta = starts_at - now
            reminder_key = None
            if delta <= timedelta(minutes=10):
                reminder_key = "10m"
            elif delta <= timedelta(minutes=60):
                reminder_key = "60m"
            if reminder_key is None:
                continue

            already_sent = await self.bot.db.fetchval(
                "SELECT 1 FROM event_reminders WHERE event_id = ? AND reminder_key = ?",
                (row["id"], reminder_key),
                default=0,
            )
            if already_sent:
                continue

            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            channel = guild.get_channel(row["channel_id"])
            if not isinstance(channel, discord.TextChannel):
                continue
            participants = await self.bot.db.fetchall(
                "SELECT user_id FROM event_participants WHERE event_id = ?",
                (row["id"],),
            )
            mentions = " ".join(f"<@{item['user_id']}>" for item in participants) or ""
            await channel.send(
                f"イベント `{row['id']}` **{row['title']}** が "
                f"{format_local(starts_at, self.bot.config.default_timezone)} に始まります。 {mentions}".strip()
            )
            await self.bot.db.execute(
                "INSERT INTO event_reminders (event_id, reminder_key) VALUES (?, ?)",
                (row["id"], reminder_key),
            )

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "Gr3njaBot") -> None:
    await bot.add_cog(EventCog(bot))
