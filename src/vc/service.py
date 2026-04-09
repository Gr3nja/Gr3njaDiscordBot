from __future__ import annotations

import asyncio
import logging
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any

import discord

try:
    from discord.ext import voice_recv
except Exception as exc:  # pragma: no cover - dependency/runtime guard
    voice_recv = None
    VOICE_RECV_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - imported at runtime when dependency exists
    VOICE_RECV_IMPORT_ERROR = None


LOGGER = logging.getLogger(__name__)
PCM_SAMPLE_RATE = 48_000
PCM_CHANNELS = 2
PCM_SAMPLE_WIDTH = 2
PCM_BYTES_PER_SECOND = PCM_SAMPLE_RATE * PCM_CHANNELS * PCM_SAMPLE_WIDTH


@dataclass(slots=True)
class PCMFrame:
    timestamp: float
    pcm: bytes


@dataclass(slots=True)
class ActiveClip:
    started_at: float
    deadline: float
    frames: list[bytes] = field(default_factory=list)
    peak: float = 0.0


@dataclass(slots=True)
class UserMonitorState:
    recent_frames: deque[PCMFrame] = field(default_factory=deque)
    active_clip: ActiveClip | None = None
    last_clip_at: float = 0.0


@dataclass(slots=True)
class MonitorHandle:
    guild_id: int
    text_channel_id: int
    voice_channel_id: int
    threshold: float
    voice_client: Any
    sink: Any


def pcm_rms(pcm: bytes) -> float:
    samples = memoryview(pcm).cast("h")
    if len(samples) == 0:
        return 0.0

    total = 0
    count = 0
    for index in range(0, len(samples), 4):
        sample = samples[index]
        total += sample * sample
        count += 1
    return (total / max(count, 1)) ** 0.5


class VoiceMonitorService:
    def __init__(self, bot: "Gr3njaBot") -> None:
        self.bot = bot
        self.monitors: dict[int, MonitorHandle] = {}
        self.clips_dir = Path("data/clips")

    @property
    def available(self) -> bool:
        return voice_recv is not None

    async def set_clip_channel(self, guild_id: int, channel_id: int | None) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO guild_settings (guild_id, voice_clip_channel_id)
            VALUES (?, ?)
            ON CONFLICT (guild_id) DO UPDATE SET
                voice_clip_channel_id = excluded.voice_clip_channel_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id),
        )

    async def get_clip_channel_id(self, guild_id: int) -> int | None:
        return await self.bot.db.fetchval(
            "SELECT voice_clip_channel_id FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )

    async def start_monitor(
        self,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        *,
        threshold: float | None = None,
    ) -> MonitorHandle:
        if voice_recv is None:
            raise RuntimeError(f"voice receive is unavailable: {VOICE_RECV_IMPORT_ERROR}")

        guild = voice_channel.guild
        if guild.voice_client and not isinstance(guild.voice_client, voice_recv.VoiceRecvClient):
            await guild.voice_client.disconnect(force=True)

        if guild.voice_client is None:
            voice_client = await voice_channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=True)
        else:
            voice_client = guild.voice_client
            if voice_client.channel.id != voice_channel.id:
                await voice_client.move_to(voice_channel)
            if voice_client.is_listening():
                voice_client.stop_listening()

        scream_threshold = threshold or self.bot.config.voice_scream_threshold
        sink = VoiceClipSink(
            service=self,
            guild_id=guild.id,
            text_channel_id=text_channel.id,
            threshold=scream_threshold,
        )
        voice_client.listen(sink)

        handle = MonitorHandle(
            guild_id=guild.id,
            text_channel_id=text_channel.id,
            voice_channel_id=voice_channel.id,
            threshold=scream_threshold,
            voice_client=voice_client,
            sink=sink,
        )
        self.monitors[guild.id] = handle
        await self.set_clip_channel(guild.id, text_channel.id)
        return handle

    async def stop_monitor(self, guild_id: int) -> bool:
        handle = self.monitors.pop(guild_id, None)
        if handle is None:
            guild = self.bot.get_guild(guild_id)
            guild_voice_client = guild.voice_client if guild else None
            if guild_voice_client:
                await guild_voice_client.disconnect(force=True)
                return True
            return False

        try:
            if handle.voice_client.is_listening():
                handle.voice_client.stop_listening()
        finally:
            await handle.voice_client.disconnect(force=True)
        return True

    async def shutdown(self) -> None:
        for guild_id in list(self.monitors):
            try:
                await self.stop_monitor(guild_id)
            except Exception:  # pragma: no cover - defensive shutdown
                LOGGER.exception("failed to stop voice monitor for guild %s", guild_id)

    def dispatch_clip_from_thread(
        self,
        *,
        guild_id: int,
        text_channel_id: int,
        member_id: int,
        member_name: str,
        file_path: Path,
        peak: float,
        duration: float,
    ) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self._send_clip(
                guild_id=guild_id,
                text_channel_id=text_channel_id,
                member_id=member_id,
                member_name=member_name,
                file_path=file_path,
                peak=peak,
                duration=duration,
            ),
            self.bot.loop,
        )

        def _log_failure(done: asyncio.Future[Any]) -> None:
            try:
                done.result()
            except Exception:
                LOGGER.exception("failed to send voice clip")

        future.add_done_callback(_log_failure)

    async def _send_clip(
        self,
        *,
        guild_id: int,
        text_channel_id: int,
        member_id: int,
        member_name: str,
        file_path: Path,
        peak: float,
        duration: float,
    ) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            file_path.unlink(missing_ok=True)
            return

        channel = guild.get_channel(text_channel_id)
        if not isinstance(channel, discord.TextChannel):
            saved_channel_id = await self.get_clip_channel_id(guild_id)
            if saved_channel_id:
                channel = guild.get_channel(saved_channel_id)

        if not isinstance(channel, discord.TextChannel):
            channel = guild.system_channel or next(
                (candidate for candidate in guild.text_channels if candidate.permissions_for(guild.me).send_messages),
                None,
            )

        if channel is None:
            file_path.unlink(missing_ok=True)
            return

        try:
            await channel.send(
                content=(
                    f"発狂クリップを検知しました: <@{member_id}> "
                    f"({member_name}) / peak={peak:.0f} / {duration:.1f}s"
                ),
                file=discord.File(file_path, filename=file_path.name),
            )
        finally:
            file_path.unlink(missing_ok=True)

    def write_clip_file(self, guild_id: int, member_id: int, frames: list[bytes]) -> tuple[Path, float]:
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        guild_dir = self.clips_dir / str(guild_id)
        guild_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{member_id}-{int(monotonic() * 1000)}.wav"
        file_path = guild_dir / filename

        with wave.open(str(file_path), "wb") as output:
            output.setnchannels(PCM_CHANNELS)
            output.setsampwidth(PCM_SAMPLE_WIDTH)
            output.setframerate(PCM_SAMPLE_RATE)
            for frame in frames:
                output.writeframes(frame)

        total_bytes = sum(len(frame) for frame in frames)
        duration = total_bytes / PCM_BYTES_PER_SECOND
        return file_path, duration


if voice_recv is not None:  # pragma: no branch
    class VoiceClipSink(voice_recv.AudioSink):
        def __init__(
            self,
            *,
            service: VoiceMonitorService,
            guild_id: int,
            text_channel_id: int,
            threshold: float,
        ) -> None:
            super().__init__()
            self.service = service
            self.guild_id = guild_id
            self.text_channel_id = text_channel_id
            self.threshold = threshold
            self.pre_buffer_seconds = service.bot.config.voice_pre_buffer_seconds
            self.post_buffer_seconds = service.bot.config.voice_post_buffer_seconds
            self.cooldown_seconds = service.bot.config.voice_clip_cooldown_seconds
            self.min_clip_seconds = service.bot.config.voice_min_clip_seconds
            self.user_states: dict[int, UserMonitorState] = {}
            self.recording_allowed: dict[int, bool] = {}

        def wants_opus(self) -> bool:
            return False

        def write(self, user: discord.Member | discord.User | None, data: Any) -> None:
            if user is None or user.bot or not data.pcm:
                return
            if self.recording_allowed.get(user.id, True) is False:
                return

            now = monotonic()
            state = self.user_states.setdefault(user.id, UserMonitorState())
            frame = PCMFrame(timestamp=now, pcm=bytes(data.pcm))
            amplitude = pcm_rms(frame.pcm)

            state.recent_frames.append(frame)
            while state.recent_frames and now - state.recent_frames[0].timestamp > self.pre_buffer_seconds:
                state.recent_frames.popleft()

            if state.active_clip is not None:
                state.active_clip.frames.append(frame.pcm)
                state.active_clip.peak = max(state.active_clip.peak, amplitude)
                if amplitude >= self.threshold:
                    state.active_clip.deadline = max(state.active_clip.deadline, now + self.post_buffer_seconds)
                if now >= state.active_clip.deadline:
                    self._finalize_clip(user, state)
                return

            if amplitude < self.threshold:
                return
            if now - state.last_clip_at < self.cooldown_seconds:
                return

            state.active_clip = ActiveClip(
                started_at=now,
                deadline=now + self.post_buffer_seconds,
                frames=[item.pcm for item in state.recent_frames],
                peak=amplitude,
            )

        @voice_recv.AudioSink.listener()
        def on_voice_member_flags(self, member: discord.Member, flags: Any) -> None:
            allowed = bool(
                getattr(flags, "allow_voice_recording", False)
                or getattr(flags, "allow_any_viewer_clips", False)
                or getattr(flags, "clips_enabled", False)
            )
            self.recording_allowed[member.id] = allowed

        @voice_recv.AudioSink.listener()
        def on_voice_member_disconnect(self, member: discord.Member, ssrc: int | None) -> None:
            del ssrc
            self.user_states.pop(member.id, None)
            self.recording_allowed.pop(member.id, None)

        def cleanup(self) -> None:
            self.user_states.clear()
            self.recording_allowed.clear()

        def _finalize_clip(self, user: discord.Member | discord.User, state: UserMonitorState) -> None:
            clip = state.active_clip
            state.active_clip = None
            state.last_clip_at = monotonic()
            if clip is None or not clip.frames:
                return

            file_path, duration = self.service.write_clip_file(self.guild_id, user.id, clip.frames)
            if duration < self.min_clip_seconds:
                file_path.unlink(missing_ok=True)
                return

            self.service.dispatch_clip_from_thread(
                guild_id=self.guild_id,
                text_channel_id=self.text_channel_id,
                member_id=user.id,
                member_name=getattr(user, "display_name", user.name),
                file_path=file_path,
                peak=clip.peak,
                duration=duration,
            )
