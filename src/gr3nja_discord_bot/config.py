from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class BotConfig:
    token: str
    prefix: str
    database_path: Path
    default_timezone: str
    intro_reaction_emoji: str
    default_currency_name: str
    daily_reward: int
    message_reward: int
    message_reward_cooldown: int
    shiritori_reward: int
    event_default_reward: int
    voice_scream_threshold: float
    voice_pre_buffer_seconds: float
    voice_post_buffer_seconds: float
    voice_clip_cooldown_seconds: float
    voice_min_clip_seconds: float


def load_config() -> BotConfig:
    load_dotenv()

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN が設定されていません。")

    return BotConfig(
        token=token,
        prefix=os.getenv("BOT_PREFIX", "!"),
        database_path=Path(os.getenv("DATABASE_PATH", "data/bot.db")),
        default_timezone=os.getenv("BOT_TIMEZONE", "Asia/Tokyo"),
        intro_reaction_emoji=os.getenv("INTRO_REACTION_EMOJI", "🤝"),
        default_currency_name=os.getenv("DEFAULT_CURRENCY_NAME", "グレコイン"),
        daily_reward=int(os.getenv("DAILY_REWARD", "150")),
        message_reward=int(os.getenv("MESSAGE_REWARD", "5")),
        message_reward_cooldown=int(os.getenv("MESSAGE_REWARD_COOLDOWN", "60")),
        shiritori_reward=int(os.getenv("SHIRITORI_REWARD", "10")),
        event_default_reward=int(os.getenv("EVENT_DEFAULT_REWARD", "100")),
        voice_scream_threshold=float(os.getenv("VOICE_SCREAM_THRESHOLD", "9000")),
        voice_pre_buffer_seconds=float(os.getenv("VOICE_PRE_BUFFER_SECONDS", "3.0")),
        voice_post_buffer_seconds=float(os.getenv("VOICE_POST_BUFFER_SECONDS", "2.5")),
        voice_clip_cooldown_seconds=float(os.getenv("VOICE_CLIP_COOLDOWN_SECONDS", "20.0")),
        voice_min_clip_seconds=float(os.getenv("VOICE_MIN_CLIP_SECONDS", "1.5")),
    )
