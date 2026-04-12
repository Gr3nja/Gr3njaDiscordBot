from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

import aiosqlite


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    intro_channel_id INTEGER,
    intro_reaction_emoji TEXT,
    currency_name TEXT,
    voice_clip_channel_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wallets (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0,
    last_daily_at TEXT,
    last_message_reward_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS self_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS shop_roles (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    price INTEGER NOT NULL,
    description TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS owned_shop_roles (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id, role_id)
);

CREATE TABLE IF NOT EXISTS trigger_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'contains',
    keyword TEXT NOT NULL,
    response TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shiritori_sessions (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    last_word TEXT,
    last_kana TEXT,
    used_words_json TEXT NOT NULL DEFAULT '[]',
    chain_length INTEGER NOT NULL DEFAULT 0,
    last_player_id INTEGER,
    started_by INTEGER NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS shiritori_scores (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    plays INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    longest_chain INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS achievement_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    code TEXT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    icon TEXT NOT NULL DEFAULT '🏆',
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (guild_id, code)
);

CREATE TABLE IF NOT EXISTS user_achievements (
    achievement_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    awarded_by INTEGER,
    note TEXT,
    awarded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (achievement_id, guild_id, user_id),
    FOREIGN KEY (achievement_id) REFERENCES achievement_definitions (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity_counters (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    messages INTEGER NOT NULL DEFAULT 0,
    trigger_rules_created INTEGER NOT NULL DEFAULT 0,
    events_joined INTEGER NOT NULL DEFAULT 0,
    roles_purchased INTEGER NOT NULL DEFAULT 0,
    casino_games INTEGER NOT NULL DEFAULT 0,
    casino_wins INTEGER NOT NULL DEFAULT 0,
    shiritori_plays INTEGER NOT NULL DEFAULT 0,
    shiritori_wins INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    starts_at TEXT NOT NULL,
    reward INTEGER NOT NULL DEFAULT 0,
    max_participants INTEGER,
    creator_id INTEGER NOT NULL,
    completed_at TEXT,
    cancelled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_participants (
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS event_reminders (
    event_id INTEGER NOT NULL,
    reminder_key TEXT NOT NULL,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, reminder_key),
    FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_guild_settings (
    guild_id INTEGER PRIMARY KEY,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_logs (
    message_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    edited_at TEXT,
    deleted_at TEXT,
    is_command INTEGER NOT NULL DEFAULT 0,
    reply_to_message_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ai_conversation_scope
ON ai_conversation_messages (guild_id, channel_id, user_id, id);

CREATE INDEX IF NOT EXISTS idx_message_logs_channel_created
ON message_logs (guild_id, channel_id, created_at DESC, message_id DESC);

CREATE INDEX IF NOT EXISTS idx_message_logs_guild_created
ON message_logs (guild_id, created_at DESC, message_id DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database has not been connected yet.")
        return self._connection

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.commit()

    async def init(self) -> None:
        await self.connection.executescript(SCHEMA)
        await self.connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def execute(self, query: str, parameters: Sequence[Any] = ()) -> aiosqlite.Cursor:
        cursor = await self.connection.execute(query, parameters)
        await self.connection.commit()
        return cursor

    async def executemany(self, query: str, values: Iterable[Sequence[Any]]) -> None:
        await self.connection.executemany(query, values)
        await self.connection.commit()

    async def fetchone(self, query: str, parameters: Sequence[Any] = ()) -> aiosqlite.Row | None:
        cursor = await self.connection.execute(query, parameters)
        return await cursor.fetchone()

    async def fetchall(self, query: str, parameters: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        cursor = await self.connection.execute(query, parameters)
        return await cursor.fetchall()

    async def fetchval(self, query: str, parameters: Sequence[Any] = (), default: Any = None) -> Any:
        row = await self.fetchone(query, parameters)
        if row is None:
            return default
        return row[0]
