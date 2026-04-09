from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BuiltinAchievement:
    code: str
    name: str
    description: str
    points: int
    icon: str


@dataclass(frozen=True, slots=True)
class AchievementAward:
    achievement_id: int
    name: str
    description: str
    points: int
    icon: str


BUILTIN_ACHIEVEMENTS = (
    BuiltinAchievement("first_message", "はじめての一言", "サーバーで初めて発言した", 5, "💬"),
    BuiltinAchievement("chatterbox", "雑談マイスター", "100回発言した", 20, "🗣️"),
    BuiltinAchievement("trigger_smith", "自動化見習い", "トリガールールを1つ作成した", 15, "🛠️"),
    BuiltinAchievement("shiritori_debut", "しりとり入門", "しりとりに初参加した", 10, "📝"),
    BuiltinAchievement("shiritori_ace", "しりとり番長", "しりとりで5勝した", 30, "👑"),
    BuiltinAchievement("event_joiner", "イベント常連", "イベントに初参加した", 15, "🎉"),
    BuiltinAchievement("first_purchase", "お買い上げ", "ショップロールを初購入した", 20, "🛍️"),
    BuiltinAchievement("casino_debut", "初カジノ", "カジノを初プレイした", 10, "🎰"),
    BuiltinAchievement("lucky_streak", "豪運", "カジノで10回勝利した", 35, "🍀"),
    BuiltinAchievement("moneybag", "成金", "残高が1,000を超えた", 20, "💰"),
    BuiltinAchievement("tycoon", "大富豪", "残高が5,000を超えた", 40, "🏦"),
)

COUNTER_FIELDS = {
    "messages",
    "trigger_rules_created",
    "events_joined",
    "roles_purchased",
    "casino_games",
    "casino_wins",
    "shiritori_plays",
    "shiritori_wins",
}


class AchievementService:
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    async def sync_builtin_definitions(self) -> None:
        await self.bot.db.executemany(
            """
            INSERT INTO achievement_definitions
                (guild_id, code, name, description, points, icon, is_builtin)
            VALUES
                (0, ?, ?, ?, ?, ?, 1)
            ON CONFLICT (guild_id, code) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                points = excluded.points,
                icon = excluded.icon
            """,
            [
                (item.code, item.name, item.description, item.points, item.icon)
                for item in BUILTIN_ACHIEVEMENTS
            ],
        )

    async def create_custom_definition(
        self,
        guild_id: int,
        creator_id: int,
        name: str,
        description: str,
        points: int,
        icon: str,
    ) -> int:
        cursor = await self.bot.db.execute(
            """
            INSERT INTO achievement_definitions
                (guild_id, code, name, description, points, icon, is_builtin, created_by)
            VALUES
                (?, NULL, ?, ?, ?, ?, 0, ?)
            """,
            (guild_id, name, description, points, icon, creator_id),
        )
        return int(cursor.lastrowid)

    async def list_definitions(self, guild_id: int) -> list:
        return await self.bot.db.fetchall(
            """
            SELECT id, guild_id, code, name, description, points, icon, is_builtin
            FROM achievement_definitions
            WHERE guild_id IN (0, ?)
            ORDER BY is_builtin DESC, points DESC, id ASC
            """,
            (guild_id,),
        )

    async def list_member_achievements(self, guild_id: int, user_id: int) -> list:
        return await self.bot.db.fetchall(
            """
            SELECT
                ad.id,
                ad.name,
                ad.description,
                ad.points,
                ad.icon,
                ua.awarded_at
            FROM user_achievements ua
            INNER JOIN achievement_definitions ad
                ON ad.id = ua.achievement_id
            WHERE ua.guild_id = ? AND ua.user_id = ?
            ORDER BY ua.awarded_at DESC
            """,
            (guild_id, user_id),
        )

    async def leaderboard(self, guild_id: int, limit: int = 10) -> list:
        return await self.bot.db.fetchall(
            """
            SELECT user_id, SUM(ad.points) AS total_points, COUNT(*) AS achievement_count
            FROM user_achievements ua
            INNER JOIN achievement_definitions ad
                ON ad.id = ua.achievement_id
            WHERE ua.guild_id = ?
            GROUP BY user_id
            ORDER BY total_points DESC, achievement_count DESC, user_id ASC
            LIMIT ?
            """,
            (guild_id, limit),
        )

    async def grant(
        self,
        guild_id: int,
        user_id: int,
        achievement_id: int,
        awarded_by: int | None,
        note: str | None = None,
    ) -> AchievementAward | None:
        exists = await self.bot.db.fetchone(
            """
            SELECT id, name, description, points, icon
            FROM achievement_definitions
            WHERE id = ? AND guild_id IN (0, ?)
            """,
            (achievement_id, guild_id),
        )
        if exists is None:
            return None

        cursor = await self.bot.db.execute(
            """
            INSERT INTO user_achievements (achievement_id, guild_id, user_id, awarded_by, note)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (achievement_id, guild_id, user_id) DO NOTHING
            """,
            (achievement_id, guild_id, user_id, awarded_by, note),
        )
        if cursor.rowcount == 0:
            return None

        return AchievementAward(
            achievement_id=exists["id"],
            name=exists["name"],
            description=exists["description"],
            points=exists["points"],
            icon=exists["icon"],
        )

    async def revoke(self, guild_id: int, user_id: int, achievement_id: int) -> bool:
        cursor = await self.bot.db.execute(
            """
            DELETE FROM user_achievements
            WHERE guild_id = ? AND user_id = ? AND achievement_id = ?
            """,
            (guild_id, user_id, achievement_id),
        )
        return cursor.rowcount > 0

    async def award_builtin(self, guild_id: int, user_id: int, code: str, awarded_by: int | None = None) -> AchievementAward | None:
        definition = await self.bot.db.fetchone(
            "SELECT id FROM achievement_definitions WHERE guild_id = 0 AND code = ?",
            (code,),
        )
        if definition is None:
            return None
        return await self.grant(guild_id, user_id, definition["id"], awarded_by)

    async def increment_counter(self, guild_id: int, user_id: int, field: str, amount: int = 1) -> None:
        if field not in COUNTER_FIELDS:
            raise ValueError(f"Unsupported counter field: {field}")
        await self.bot.db.execute(
            """
            INSERT INTO activity_counters (guild_id, user_id, {field})
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                {field} = {field} + excluded.{field}
            """.format(field=field),
            (guild_id, user_id, amount),
        )

    async def get_counters(self, guild_id: int, user_id: int) -> dict[str, int]:
        row = await self.bot.db.fetchone(
            """
            SELECT
                messages,
                trigger_rules_created,
                events_joined,
                roles_purchased,
                casino_games,
                casino_wins,
                shiritori_plays,
                shiritori_wins
            FROM activity_counters
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        if row is None:
            return {field: 0 for field in COUNTER_FIELDS}
        return {field: row[field] for field in COUNTER_FIELDS}

    async def evaluate_auto_achievements(self, guild_id: int, user_id: int) -> list[AchievementAward]:
        counters = await self.get_counters(guild_id, user_id)
        balance = await self.bot.db.fetchval(
            "SELECT balance FROM wallets WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
            default=0,
        )

        candidates: list[str] = []
        if counters["messages"] >= 1:
            candidates.append("first_message")
        if counters["messages"] >= 100:
            candidates.append("chatterbox")
        if counters["trigger_rules_created"] >= 1:
            candidates.append("trigger_smith")
        if counters["shiritori_plays"] >= 1:
            candidates.append("shiritori_debut")
        if counters["shiritori_wins"] >= 5:
            candidates.append("shiritori_ace")
        if counters["events_joined"] >= 1:
            candidates.append("event_joiner")
        if counters["roles_purchased"] >= 1:
            candidates.append("first_purchase")
        if counters["casino_games"] >= 1:
            candidates.append("casino_debut")
        if counters["casino_wins"] >= 10:
            candidates.append("lucky_streak")
        if balance >= 1000:
            candidates.append("moneybag")
        if balance >= 5000:
            candidates.append("tycoon")

        awarded: list[AchievementAward] = []
        for code in candidates:
            achievement = await self.award_builtin(guild_id, user_id, code)
            if achievement is not None:
                awarded.append(achievement)
        return awarded

    async def record_message(self, guild_id: int, user_id: int) -> list[AchievementAward]:
        await self.increment_counter(guild_id, user_id, "messages", 1)
        return await self.evaluate_auto_achievements(guild_id, user_id)

    async def record_trigger_creation(self, guild_id: int, user_id: int) -> list[AchievementAward]:
        await self.increment_counter(guild_id, user_id, "trigger_rules_created", 1)
        return await self.evaluate_auto_achievements(guild_id, user_id)

    async def record_event_join(self, guild_id: int, user_id: int) -> list[AchievementAward]:
        await self.increment_counter(guild_id, user_id, "events_joined", 1)
        return await self.evaluate_auto_achievements(guild_id, user_id)

    async def record_role_purchase(self, guild_id: int, user_id: int) -> list[AchievementAward]:
        await self.increment_counter(guild_id, user_id, "roles_purchased", 1)
        return await self.evaluate_auto_achievements(guild_id, user_id)

    async def record_casino_game(self, guild_id: int, user_id: int, *, won: bool) -> list[AchievementAward]:
        await self.increment_counter(guild_id, user_id, "casino_games", 1)
        if won:
            await self.increment_counter(guild_id, user_id, "casino_wins", 1)
        return await self.evaluate_auto_achievements(guild_id, user_id)

    async def record_shiritori_play(self, guild_id: int, user_id: int, *, won: bool) -> list[AchievementAward]:
        await self.increment_counter(guild_id, user_id, "shiritori_plays", 1)
        if won:
            await self.increment_counter(guild_id, user_id, "shiritori_wins", 1)
        return await self.evaluate_auto_achievements(guild_id, user_id)
