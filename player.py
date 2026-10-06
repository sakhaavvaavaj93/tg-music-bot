```python
"""
Music Downloader and Player for Telegram Music Bot.

Compatible with:
    pytgcalls==3.0.0.dev24
    tgcalls==3.0.0.dev6

This version uses the older GroupCallFactory / GroupCallFile API
instead of the newer PyTgCalls / AudioPiped API.
"""

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import yt_dlp

from config import config
from optional_deps import VOICE_CHAT_AVAILABLE

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    """Information about a music track."""
    title: str
    duration: int
    url: str
    webpage_url: str
    thumbnail: str
    uploader: str
    filepath: Optional[str] = None

    # RAW PCM file used by pytgcalls GroupCallFile
    playback_filepath: Optional[str] = None


class MusicDownloader:
    """Downloads audio using yt-dlp."""

    def __init__(self):
        self.downloads_dir = Path(config.downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        self._ydl_opts = {
            "format": config.ytdl_format,
            "outtmpl": str(self.downloads_dir / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
        }

    async def extract_info(self, query: str) -> Optional[TrackInfo]:
        """Extract track information without downloading."""
        loop = asyncio.get_running_loop()

        try:
            with yt_dlp.YoutubeDL(
                {**self._ydl_opts, "extract_flat": True}
            ) as ydl:

                if query.startswith(("http://", "https://")):
                    info = await loop.run_in_executor(
                        None,
                        lambda: ydl.extract_info(query, download=False),
                    )
                else:
                    info = await loop.run_in_executor(
                        None,
                        lambda: ydl.extract_info(
                            f"ytsearch:{query}",
                            download=False,
                        ),
                    )

                if not info:
                    return None

                if "entries" in info:
                    entries = info.get("entries") or []
                    info = entries[0] if entries else None

                if not info:
                    return None

                return TrackInfo(
                    title=info.get("title", "Unknown"),
                    duration=int(info.get("duration", 0) or 0),
                    url=info.get("url", ""),
                    webpage_url=info.get("webpage_url", ""),
                    thumbnail=info.get("thumbnail", ""),
                    uploader=info.get("uploader", "Unknown"),
                )

        except Exception as e:
            logger.error("Error extracting info: %s", e, exc_info=True)
            return None

    async def download(self, track: TrackInfo) -> Optional[str]:
        """Download audio file for a track."""
        loop = asyncio.get_running_loop()

        try:
            ydl_opts = {
                **self._ydl_opts,
                "outtmpl": str(
                    self.downloads_dir / f"{track.title}.%(ext)s"
                ),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([track.webpage_url])

                    for ext in ("mp3", "m4a", "webm", "opus"):
                        files = list(
                            self.downloads_dir.glob(
                                f"{track.title}.{ext}"
                            )
                        )

                        if files:
                            return str(files[0])

                return None

            filepath = await loop.run_in_executor(None, _download)

            if filepath and Path(filepath).exists():
                track.filepath = filepath
                logger.info("Downloaded: %s", filepath)
                return filepath

            logger.error("Downloaded file could not be found")
            return None

        except Exception as e:
            logger.error(
                "Error downloading %s: %s",
                track.title,
                e,
                exc_info=True,
            )
            return None

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> List[TrackInfo]:
        """Search for tracks."""
        loop = asyncio.get_running_loop()

        try:
            with yt_dlp.YoutubeDL(
                {**self._ydl_opts, "extract_flat": True}
            ) as ydl:

                info = await loop.run_in_executor(
                    None,
                    lambda: ydl.extract_info(
                        f"ytsearch{limit}:{query}",
                        download=False,
                    ),
                )

                tracks: List[TrackInfo] = []

                if info and "entries" in info:
                    for entry in (info.get("entries") or [])[:limit]:
                        if not entry:
                            continue

                        tracks.append(
                            TrackInfo(
                                title=entry.get(
                                    "title",
                                    "Unknown",
                                ),
                                duration=int(
                                    entry.get(
                                        "duration",
                                        0,
                                    )
                                    or 0
                                ),
                                url=entry.get("url", ""),
                                webpage_url=entry.get(
                                    "webpage_url",
                                    "",
                                ),
                                thumbnail=entry.get(
                                    "thumbnail",
                                    "",
                                ),
                                uploader=entry.get(
                                    "uploader",
                                    "Unknown",
                                ),
                            )
                        )

                return tracks

        except Exception as e:
            logger.error(
                "Search error: %s",
                e,
                exc_info=True,
            )
            return []


class MusicPlayer:
    """
    Voice-chat playback using pytgcalls 3.0.0.dev24.

    Expected client:
        pytgcalls.GroupCallFile

    It is created in main.py using:

        GroupCallFactory(app).get_file_group_call()

    The file GroupCall API expects RAW PCM audio.
    """

    def __init__(self, group_call=None):
        self.client = group_call

        self.current_track: Optional[TrackInfo] = None
        self.current_chat_id: Optional[int] = None

        self.volume: int = config.default_volume
        self.repeat_mode: str = "off"

        self.is_playing: bool = False
        self.is_paused: bool = False

        self._leave_task: Optional[asyncio.Task] = None

        self._available = (
            VOICE_CHAT_AVAILABLE and self.client is not None
        )

        if not self._available:
            logger.warning(
                "MusicPlayer initialized without available voice chat"
            )

    # ---------------------------------------------------------
    # RAW audio conversion
    # ---------------------------------------------------------

    async def _convert_to_raw(
        self,
        input_file: str,
        track: TrackInfo,
    ) -> Optional[str]:
        """
        Convert audio to RAW PCM required by pytgcalls.

        Format:
            signed 16-bit little endian
            stereo
            48000 Hz
        """

        ffmpeg_path = shutil.which("ffmpeg")

        if not ffmpeg_path:
            logger.error(
                "FFmpeg not found. Install ffmpeg on Render/server."
            )
            return None

        input_path = Path(input_file)

        if not input_path.exists():
            logger.error(
                "Input audio file does not exist: %s",
                input_file,
            )
            return None

        raw_path = input_path.with_suffix(".raw")

        loop = asyncio.get_running_loop()

        def _convert():
            command = [
                ffmpeg_path,
                "-y",
                "-i",
                str(input_path),
                "-f",
                "s16le",
                "-acodec",
                "pcm_s16le",
                "-ac",
                "2",
                "-ar",
                "48000",
                str(raw_path),
            ]

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0:
                logger.error(
                    "FFmpeg conversion failed:\n%s",
                    result.stderr[-4000:],
                )
                return None

            if not raw_path.exists() or raw_path.stat().st_size == 0:
                logger.error(
                    "FFmpeg created no usable RAW file"
                )
                return None

            return str(raw_path)

        raw_file = await loop.run_in_executor(
            None,
            _convert,
        )

        if raw_file:
            track.playback_filepath = raw_file
            logger.info(
                "RAW playback file created: %s",
                raw_file,
            )

        return raw_file

    # ---------------------------------------------------------
    # Voice chat
    # ---------------------------------------------------------

    async def join_call(self, chat_id: int) -> bool:
        """
        Join Telegram voice chat.

        GroupCallFile.start() handles joining.
        """

        if not self._available:
            logger.error(
                "Voice chat is not available"
            )
            return False

        try:
            # If already connected to another chat,
            # leave it first.
            if (
                self.current_chat_id is not None
                and self.current_chat_id != chat_id
            ):
                await self.leave_call(
                    self.current_chat_id
                )

            await self.client.start(chat_id)

            self.current_chat_id = chat_id
            self._cancel_leave_timer()

            logger.info(
                "Joined voice chat: %s",
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to join voice chat %s: %s",
                chat_id,
                e,
                exc_info=True,
            )
            return False

    async def leave_call(self, chat_id: int) -> bool:
        """Leave the current voice chat."""

        if not self._available:
            return False

        try:
            await self.client.stop()

            self.current_chat_id = None
            self.current_track = None
            self.is_playing = False
            self.is_paused = False

            self._cancel_leave_timer()

            logger.info(
                "Left voice chat: %s",
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to leave voice chat: %s",
                e,
                exc_info=True,
            )
            return False

    async def play(
        self,
        chat_id: int,
        track: TrackInfo,
    ) -> bool:
        """Play a track in Telegram voice chat."""

        if not self._available:
            logger.error(
                "Voice chat is not available"
            )
            return False

        if not track.filepath:
            logger.error(
                "Track has no downloaded file"
            )
            return False

        if not Path(track.filepath).exists():
            logger.error(
                "Downloaded file not found: %s",
                track.filepath,
            )
            return False

        try:
            # Convert only when necessary.
            raw_file = track.playback_filepath

            if not raw_file or not Path(raw_file).exists():
                raw_file = await self._convert_to_raw(
                    track.filepath,
                    track,
                )

            if not raw_file:
                return False

            # If connected to another chat, switch chat.
            if (
                self.current_chat_id is not None
                and self.current_chat_id != chat_id
            ):
                await self.leave_call(
                    self.current_chat_id
                )

            # Set input before starting.
            self.client.input_filename = raw_file

            # Join if not connected.
            if (
                self.current_chat_id != chat_id
                or not getattr(
                    self.client,
                    "is_connected",
                    False,
                )
            ):
                started = await self.join_call(chat_id)

                if not started:
                    return False

            else:
                # Already connected.
                # Changing input_filename automatically
                # restarts playout in GroupCallFile.
                self.client.input_filename = raw_file

            self.current_track = track
            self.current_chat_id = chat_id
            self.is_playing = True
            self.is_paused = False

            self._cancel_leave_timer()

            logger.info(
                "Playing '%s' in chat %s",
                track.title,
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Error playing '%s': %s",
                track.title,
                e,
                exc_info=True,
            )
            return False

    async def pause(self, chat_id: int) -> bool:
        """Pause audio playback."""

        if not self._available:
            return False

        if (
            self.current_chat_id != chat_id
            or not self.is_playing
        ):
            return False

        try:
            # dev24 GroupCallFile method is synchronous.
            self.client.pause_playout()

            self.is_paused = True
            self.is_playing = False

            logger.info(
                "Playback paused in chat %s",
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Error pausing playback: %s",
                e,
                exc_info=True,
            )
            return False

    async def resume(self, chat_id: int) -> bool:
        """Resume audio playback."""

        if not self._available:
            return False

        if self.current_chat_id != chat_id:
            return False

        try:
            # dev24 GroupCallFile method is synchronous.
            self.client.resume_playout()

            self.is_paused = False
            self.is_playing = True

            logger.info(
                "Playback resumed in chat %s",
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Error resuming playback: %s",
                e,
                exc_info=True,
            )
            return False

    async def stop(self, chat_id: int) -> bool:
        """
        Stop playback and leave voice chat.
        """

        if not self._available:
            return False

        try:
            self.client.stop_playout()

            await self.client.stop()

            self.current_track = None
            self.current_chat_id = None

            self.is_playing = False
            self.is_paused = False

            self._cancel_leave_timer()

            logger.info(
                "Playback stopped in chat %s",
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Error stopping playback: %s",
                e,
                exc_info=True,
            )
            return False

    async def set_volume(
        self,
        chat_id: int,
        volume: int,
    ) -> bool:
        """Set playback volume from 1 to 200."""

        if not self._available:
            return False

        if self.current_chat_id != chat_id:
            return False

        try:
            volume = max(1, min(200, int(volume)))

            await self.client.set_my_volume(
                volume
            )

            self.volume = volume

            logger.info(
                "Volume set to %s in chat %s",
                volume,
                chat_id,
            )

            return True

        except Exception as e:
            logger.error(
                "Error setting volume: %s",
                e,
                exc_info=True,
            )
            return False

    # ---------------------------------------------------------
    # Automatic leave
    # ---------------------------------------------------------

    def _cancel_leave_timer(self):
        if self._leave_task:
            self._leave_task.cancel()
            self._leave_task = None

    def _schedule_auto_leave(
        self,
        chat_id: int,
        timeout: int,
    ):
        self._cancel_leave_timer()

        if timeout > 0:
            self._leave_task = asyncio.create_task(
                self._auto_leave(
                    chat_id,
                    timeout,
                )
            )

    async def _auto_leave(
        self,
        chat_id: int,
        timeout: int,
    ):
        try:
            await asyncio.sleep(timeout)

            if (
                self.current_chat_id == chat_id
                and not self.is_playing
            ):
                await self.leave_call(
                    chat_id
                )

        except asyncio.CancelledError:
            pass

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "available": self._available,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "current_track": (
                self.current_track.title
                if self.current_track
                else None
            ),
            "current_chat_id": self.current_chat_id,
            "volume": self.volume,
            "repeat_mode": self.repeat_mode,
        }

    def is_voice_chat_available(self) -> bool:
        return self._available


# Global downloader instance.
downloader = MusicDownloader()

# MusicPlayer is initialized from main.py
# after GroupCallFactory creates GroupCallFile.
```
