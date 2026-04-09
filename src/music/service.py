from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord

try:
    import mafic
except Exception as exc:  # pragma: no cover - runtime dependency guard
    mafic = None
    MAFIC_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - imported at runtime
    MAFIC_IMPORT_ERROR = None


if TYPE_CHECKING:
    from gr3nja_discord_bot.bot import Gr3njaBot


LOGGER = logging.getLogger(__name__)
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PlaySummary:
    message: str


if mafic is not None:  # pragma: no branch
    class MusicPlayer(mafic.Player["Gr3njaBot"]):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.queue: deque[mafic.Track] = deque()
            self.text_channel_id: int | None = None

        def enqueue(self, track: mafic.Track) -> int:
            self.queue.append(track)
            return len(self.queue)

        def pop_next(self) -> mafic.Track | None:
            if not self.queue:
                return None
            return self.queue.popleft()

        def clear_queue(self) -> None:
            self.queue.clear()


else:
    class MusicPlayer:  # pragma: no cover - fallback stub when mafic is unavailable
        pass


class MusicService:
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot
        self._node_pool = mafic.NodePool(bot) if mafic is not None else None
        self._ready = False
        self._last_error: str | None = None
        self._idle_disconnect_tasks: dict[int, asyncio.Task[None]] = {}

    @property
    def available(self) -> bool:
        return self._ready

    @property
    def status_message(self) -> str:
        if mafic is None:
            return f"Mafic を読み込めませんでした: `{MAFIC_IMPORT_ERROR}`"
        if not self.bot.config.music.is_configured:
            return (
                "音楽機能は未設定です。`.env` に `LAVALINK_HOST` / "
                "`LAVALINK_PORT` / `LAVALINK_PASSWORD` を設定してください。"
            )
        if self._last_error:
            return f"Lavalink に接続できていません: {self._last_error}"
        return "Lavalink はまだ初期化中です。少し待ってから再試行してください。"

    async def connect(self) -> None:
        if mafic is None or self._node_pool is None:
            return
        if not self.bot.config.music.is_configured:
            return

        try:
            await self._node_pool.create_node(
                host=self.bot.config.music.lavalink_host,
                port=self.bot.config.music.lavalink_port,
                label="main",
                password=self.bot.config.music.lavalink_password,
                secure=self.bot.config.music.lavalink_secure,
                player_cls=MusicPlayer,
            )
        except Exception as exc:  # pragma: no cover - network/runtime guard
            self._ready = False
            self._last_error = str(exc)
            LOGGER.exception("failed to connect to lavalink")
            return

        self._ready = True
        self._last_error = None

    async def shutdown(self) -> None:
        for guild_id in list(self._idle_disconnect_tasks):
            self._cancel_idle_disconnect(guild_id)

        if self._node_pool is not None and self._ready:
            await self._node_pool.close()
        self._ready = False

    async def play(
        self,
        *,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        query: str,
    ) -> PlaySummary:
        if not self.available:
            raise RuntimeError(self.status_message)

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("再生するキーワードまたはURLを指定してください。")

        player = await self._get_or_connect_player(voice_channel, text_channel)
        search_result = await self._fetch_tracks(player, normalized_query)
        if not search_result:
            raise LookupError("曲が見つかりませんでした。キーワードかURLを見直してください。")

        playlist_name: str | None = None
        if mafic is None:
            raise RuntimeError(self.status_message)
        if isinstance(search_result, mafic.Playlist):
            playlist_name = search_result.name
            tracks = list(search_result.tracks)
        else:
            tracks = list(search_result)

        if not tracks:
            raise LookupError("曲が見つかりませんでした。キーワードかURLを見直してください。")

        player.text_channel_id = text_channel.id
        self._cancel_idle_disconnect(voice_channel.guild.id)

        if player.current is None and not player.queue:
            first_track = tracks[0]
            for track in tracks[1:]:
                player.enqueue(track)
            await player.play(first_track, volume=self.bot.config.music.default_volume)
            return PlaySummary(
                message=self._build_start_message(first_track, len(tracks), playlist_name),
            )

        for track in tracks:
            player.enqueue(track)
        return PlaySummary(
            message=self._build_queue_message(tracks[0], len(tracks), len(player.queue), playlist_name),
        )

    async def stop(self, guild: discord.Guild) -> bool:
        voice_client = guild.voice_client
        if not isinstance(voice_client, MusicPlayer):
            return False

        self._cancel_idle_disconnect(guild.id)
        voice_client.clear_queue()
        try:
            await voice_client.stop()
        except Exception:
            LOGGER.debug("player stop failed during disconnect", exc_info=True)
        await voice_client.disconnect(force=True)
        return True

    async def handle_track_end(self, event: Any) -> None:
        player = getattr(event, "player", None)
        if not isinstance(player, MusicPlayer):
            return

        self._cancel_idle_disconnect(player.guild.id)
        await self._play_next(player)

    async def handle_track_exception(self, event: Any) -> None:
        player = getattr(event, "player", None)
        track = getattr(event, "track", None)
        if not isinstance(player, MusicPlayer):
            return
        await self._send_text_update(
            player,
            f"⚠️ 再生中にエラーが発生しました: **{self._display_title(track)}**",
        )

    async def handle_track_stuck(self, event: Any) -> None:
        player = getattr(event, "player", None)
        track = getattr(event, "track", None)
        if not isinstance(player, MusicPlayer):
            return
        await self._send_text_update(
            player,
            f"⚠️ 再生が停止しました: **{self._display_title(track)}**",
        )

    async def _play_next(self, player: MusicPlayer) -> None:
        next_track = player.pop_next()
        if next_track is None:
            self._schedule_idle_disconnect(player)
            return

        try:
            await player.play(next_track, volume=self.bot.config.music.default_volume)
        except Exception:
            LOGGER.exception("failed to start next track")
            await self._send_text_update(
                player,
                f"⚠️ 次の曲の再生に失敗しました: **{self._display_title(next_track)}**",
            )
            await self._play_next(player)

    async def _get_or_connect_player(
        self,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.TextChannel,
    ) -> MusicPlayer:
        guild = voice_channel.guild

        if guild.id in self.bot.voice_monitors.monitors:
            await self.bot.voice_monitors.stop_monitor(guild.id)

        voice_client = guild.voice_client
        if voice_client is not None and not isinstance(voice_client, MusicPlayer):
            await voice_client.disconnect(force=True)
            voice_client = None

        if isinstance(voice_client, MusicPlayer):
            if getattr(voice_client.channel, "id", None) != voice_channel.id:
                active_channel = getattr(voice_client.channel, "mention", f"VC:{getattr(voice_client.channel, 'id', 'unknown')}")
                if voice_client.current is not None or voice_client.queue:
                    raise RuntimeError(f"既に {active_channel} で音楽を再生中です。")
                await voice_client.disconnect(force=True)
            else:
                voice_client.text_channel_id = text_channel.id
                return voice_client

        player = await voice_channel.connect(cls=MusicPlayer, self_deaf=True)
        player.text_channel_id = text_channel.id
        await player.set_volume(self.bot.config.music.default_volume)
        return player

    async def _fetch_tracks(self, player: MusicPlayer, query: str) -> Any:
        if mafic is None:
            return None

        if HTTP_URL_RE.match(query):
            return await player.fetch_tracks(query)
        return await player.fetch_tracks(query, search_type=self._resolve_search_type())

    def _resolve_search_type(self) -> Any:
        if mafic is None:
            return self.bot.config.music.default_search

        normalized = self.bot.config.music.default_search.strip().lower().replace("-", "_")
        mapping = {
            "youtube": mafic.SearchType.YOUTUBE,
            "ytsearch": mafic.SearchType.YOUTUBE,
            "youtube_music": mafic.SearchType.YOUTUBE_MUSIC,
            "ytmsearch": mafic.SearchType.YOUTUBE_MUSIC,
            "soundcloud": mafic.SearchType.SOUNDCLOUD,
            "scsearch": mafic.SearchType.SOUNDCLOUD,
        }
        return mapping.get(normalized, self.bot.config.music.default_search)

    def _build_start_message(
        self,
        first_track: Any,
        track_count: int,
        playlist_name: str | None,
    ) -> str:
        title = self._display_title(first_track)
        if playlist_name and track_count > 1:
            return (
                f"▶ 再生開始: **{title}**\n"
                f"🎵 プレイリスト **{playlist_name}** から {track_count} 曲を読み込みました。"
            )
        return f"▶ 再生開始: **{title}**"

    def _build_queue_message(
        self,
        first_track: Any,
        track_count: int,
        queue_size: int,
        playlist_name: str | None,
    ) -> str:
        title = self._display_title(first_track)
        if playlist_name and track_count > 1:
            return (
                f"⏱ プレイリスト **{playlist_name}** から {track_count} 曲をキューへ追加しました。\n"
                f"先頭追加曲: **{title}** / 待機数: {queue_size}"
            )
        return f"⏱ キューに追加しました: **{title}**（待機数: {queue_size}）"

    def _display_title(self, track: Any) -> str:
        title = getattr(track, "title", None)
        if (not isinstance(title, str) or not title.strip()) and track is not None:
            info = getattr(track, "info", None)
            title = getattr(info, "title", None)
        if isinstance(title, str) and title.strip():
            return title.strip()
        return "Unknown title"

    def _schedule_idle_disconnect(self, player: MusicPlayer) -> None:
        guild_id = player.guild.id
        self._cancel_idle_disconnect(guild_id)

        async def _task() -> None:
            try:
                await asyncio.sleep(self.bot.config.music.idle_disconnect_seconds)
                if player.guild.voice_client is not player:
                    return
                if player.current is not None or player.queue:
                    return
                await player.disconnect(force=True)
                await self._send_text_update(player, "⏹ キューが空のため、VC から切断しました。")
            except Exception:
                LOGGER.exception("idle disconnect failed for guild %s", guild_id)
            finally:
                self._idle_disconnect_tasks.pop(guild_id, None)

        self._idle_disconnect_tasks[guild_id] = asyncio.create_task(_task())

    def _cancel_idle_disconnect(self, guild_id: int) -> None:
        task = self._idle_disconnect_tasks.pop(guild_id, None)
        if task is not None:
            task.cancel()

    async def _send_text_update(self, player: MusicPlayer, content: str) -> None:
        text_channel = self._get_text_channel(player)
        if text_channel is None:
            return
        await text_channel.send(content)

    def _get_text_channel(self, player: MusicPlayer) -> discord.TextChannel | None:
        channel_id = player.text_channel_id
        if channel_id is None:
            return None
        channel = player.guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None
