from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AIConfig:
    base_url: str
    api_key: str
    default_model: str
    gemini_model: str
    gpt_oss_20b_model: str
    gemma3_27b_model: str
    system_prompt: str
    request_timeout_seconds: float
    max_history_turns: int
    max_response_chars: int

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url.strip())


@dataclass(slots=True)
class MusicConfig:
    lavalink_host: str
    lavalink_port: int
    lavalink_password: str
    lavalink_secure: bool
    default_search: str
    default_volume: int
    idle_disconnect_seconds: int

    @property
    def is_configured(self) -> bool:
        return bool(self.lavalink_host.strip() and self.lavalink_password.strip())


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
    ai: AIConfig
    music: MusicConfig


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
        ai=AIConfig(
            base_url=os.getenv("AI_BASE_URL", "").strip(),
            api_key=os.getenv("AI_API_KEY", "").strip(),
            default_model=os.getenv("AI_DEFAULT_MODEL", "gemini").strip(),
            gemini_model=os.getenv("AI_MODEL_GEMINI", "gemini").strip(),
            gpt_oss_20b_model=os.getenv("AI_MODEL_GPT_OSS_20B", "gpt-oss:20b").strip(),
            gemma3_27b_model=os.getenv("AI_MODEL_GEMMA3_27B", "gemma3:27b").strip(),
            system_prompt=os.getenv(
                "AI_SYSTEM_PROMPT",
                "あなたはDiscordサーバーで動作するAIアシスタントです。回答は日本語で簡潔かつ親しみやすくしてください。",
            ).strip(),
            request_timeout_seconds=float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60")),
            max_history_turns=max(1, int(os.getenv("AI_MAX_HISTORY_TURNS", "8"))),
            max_response_chars=max(500, int(os.getenv("AI_MAX_RESPONSE_CHARS", "4000"))),
        ),
        music=MusicConfig(
            lavalink_host=os.getenv("LAVALINK_HOST", "").strip(),
            lavalink_port=int(os.getenv("LAVALINK_PORT", "2333")),
            lavalink_password=os.getenv("LAVALINK_PASSWORD", "").strip(),
            lavalink_secure=os.getenv("LAVALINK_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"},
            default_search=os.getenv("MUSIC_DEFAULT_SEARCH", "ytsearch").strip() or "ytsearch",
            default_volume=max(0, min(1000, int(os.getenv("MUSIC_DEFAULT_VOLUME", "75")))),
            idle_disconnect_seconds=max(10, int(os.getenv("MUSIC_IDLE_DISCONNECT_SECONDS", "300"))),
        ),
    )
