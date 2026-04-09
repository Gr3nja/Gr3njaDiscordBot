from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from utils.time import parse_iso_datetime, to_local, utc_now


@dataclass(slots=True)
class Wallet:
    guild_id: int
    user_id: int
    balance: int
    last_daily_at: datetime | None
    last_message_reward_at: datetime | None


class EconomyService:
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot

    async def _ensure_wallet_row(self, guild_id: int, user_id: int) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO wallets (guild_id, user_id)
            VALUES (?, ?)
            ON CONFLICT (guild_id, user_id) DO NOTHING
            """,
            (guild_id, user_id),
        )

    async def ensure_wallet(self, guild_id: int, user_id: int) -> Wallet:
        await self._ensure_wallet_row(guild_id, user_id)
        return await self.get_wallet(guild_id, user_id)

    async def get_wallet(self, guild_id: int, user_id: int) -> Wallet:
        await self._ensure_wallet_row(guild_id, user_id)
        row = await self.bot.db.fetchone(
            """
            SELECT guild_id, user_id, balance, last_daily_at, last_message_reward_at
            FROM wallets
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        if row is None:
            raise RuntimeError("wallet could not be loaded")
        return Wallet(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            balance=row["balance"],
            last_daily_at=parse_iso_datetime(row["last_daily_at"]),
            last_message_reward_at=parse_iso_datetime(row["last_message_reward_at"]),
        )

    async def get_currency_name(self, guild_id: int) -> str:
        row = await self.bot.db.fetchone(
            "SELECT currency_name FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        return row["currency_name"] if row and row["currency_name"] else self.bot.config.default_currency_name

    async def set_currency_name(self, guild_id: int, currency_name: str) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO guild_settings (guild_id, currency_name)
            VALUES (?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                currency_name = excluded.currency_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, currency_name),
        )

    async def add_balance(self, guild_id: int, user_id: int, amount: int) -> Wallet:
        await self.ensure_wallet(guild_id, user_id)
        await self.bot.db.execute(
            """
            UPDATE wallets
            SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND user_id = ?
            """,
            (amount, guild_id, user_id),
        )
        wallet = await self.get_wallet(guild_id, user_id)
        await self.bot.achievements.evaluate_auto_achievements(guild_id, user_id)
        return wallet

    async def spend_balance(self, guild_id: int, user_id: int, amount: int) -> tuple[bool, Wallet]:
        wallet = await self.get_wallet(guild_id, user_id)
        if wallet.balance < amount:
            return False, wallet
        await self.bot.db.execute(
            """
            UPDATE wallets
            SET balance = balance - ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND user_id = ?
            """,
            (amount, guild_id, user_id),
        )
        updated_wallet = await self.get_wallet(guild_id, user_id)
        return True, updated_wallet

    async def reward_message(self, guild_id: int, user_id: int) -> tuple[bool, Wallet]:
        wallet = await self.get_wallet(guild_id, user_id)
        now = utc_now()
        if wallet.last_message_reward_at is not None:
            elapsed = (now - wallet.last_message_reward_at).total_seconds()
            if elapsed < self.bot.config.message_reward_cooldown:
                return False, wallet

        await self.bot.db.execute(
            """
            UPDATE wallets
            SET balance = balance + ?, last_message_reward_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND user_id = ?
            """,
            (self.bot.config.message_reward, now.isoformat(), guild_id, user_id),
        )
        updated_wallet = await self.get_wallet(guild_id, user_id)
        return True, updated_wallet

    async def claim_daily(self, guild_id: int, user_id: int) -> tuple[bool, Wallet, datetime | None]:
        wallet = await self.get_wallet(guild_id, user_id)
        now = utc_now()
        tz_name = self.bot.config.default_timezone
        if wallet.last_daily_at is not None:
            last_local = to_local(wallet.last_daily_at, tz_name)
            now_local = to_local(now, tz_name)
            if last_local.date() == now_local.date():
                return False, wallet, wallet.last_daily_at

        await self.bot.db.execute(
            """
            UPDATE wallets
            SET balance = balance + ?, last_daily_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ? AND user_id = ?
            """,
            (self.bot.config.daily_reward, now.isoformat(), guild_id, user_id),
        )
        updated_wallet = await self.get_wallet(guild_id, user_id)
        await self.bot.achievements.evaluate_auto_achievements(guild_id, user_id)
        return True, updated_wallet, now
