"""
Command handlers for Telegram Music Bot.

Compatible with:
    Pyrogram 2.x
    pytgcalls 3.0.0.dev24
    GroupCallFactory / GroupCallFile

Voice-chat API used here:
    GroupCallFile.on_playout_ended()
    GroupCallFile.start(group)
    GroupCallFile.input_filename
    GroupCallFile.stop_playout()
    GroupCallFile.pause_playout()
    GroupCallFile.resume_playout()
    GroupCallFile.set_my_volume()
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config import config, VOICE_CHAT_AVAILABLE
from database import db, QueueItem
from player import downloader, MusicPlayer, TrackInfo

logger = logging.getLogger(__name__)

PREFIX = config.command_prefix

# ============================================================
# GLOBAL INSTANCES
# ============================================================

app: Optional[Client] = None

# This is GroupCallFile in pytgcalls dev24.
group_call = None

player: Optional[MusicPlayer] = None
shutdown_event: Optional[asyncio.Event] = None

_handlers_registered = False


# ============================================================
# INITIALIZATION
# ============================================================

def set_bot_instances(
    app_instance: Client,
    pytgcalls_instance,
    player_instance: MusicPlayer,
    shutdown_evt: asyncio.Event,
):
    """
    Receive instances from main.py and register handlers.
    """

    global app
    global group_call
    global player
    global shutdown_event
    global _handlers_registered

    app = app_instance
    group_call = pytgcalls_instance
    player = player_instance
    shutdown_event = shutdown_evt

    logger.info(
        "🔧 Handlers initialized | voice=%s | group_call=%s",
        VOICE_CHAT_AVAILABLE,
        type(group_call).__name__ if group_call else None,
    )

    if not _handlers_registered:
        _register_handlers()
        _handlers_registered = True
        logger.info("✅ Telegram handlers registered")


# ============================================================
# HELPERS
# ============================================================

def is_admin(user_id: int) -> bool:
    return user_id in config.admin_ids or config.admin_ids == []


async def get_queue_text(chat_id: int) -> str:
    queue = await db.get_queue(chat_id)

    if not queue:
        return "📭 صف پخش خالی است."

    text = "📋 **صف پخش:**\n\n"

    for i, item in enumerate(queue[:10], 1):
        duration = (
            f"{item.duration // 60}:{item.duration % 60:02d}"
            if item.duration > 0
            else "??:??"
        )

        text += (
            f"{i}. **{item.title}** "
            f"(`{duration}`) — @{item.requested_by}\n"
        )

    if len(queue) > 10:
        text += f"\n... و {len(queue) - 10} موزیک دیگر"

    return text


# ============================================================
# PLAY NEXT
# ============================================================

async def play_next(chat_id: int):
    """
    Get next item from database and play it.

    GroupCallFile itself handles the actual playout.
    """

    if not VOICE_CHAT_AVAILABLE or not player:
        logger.warning("play_next called but voice chat is unavailable")
        return

    try:
        next_item = await db.get_next_in_queue(chat_id)

        if not next_item:
            logger.info(
                "📭 Queue empty for %s; scheduling auto-leave",
                chat_id,
            )

            try:
                settings = await db.get_chat_settings(chat_id)

                timeout = settings.get(
                    "auto_leave_timeout",
                    config.auto_leave_timeout,
                )

                player._schedule_auto_leave(chat_id, timeout)

            except Exception:
                logger.exception("Auto-leave scheduling failed")

            return

        logger.info(
            "▶️ Next track: %s | chat=%s",
            next_item.title,
            chat_id,
        )

        # ----------------------------------------------------
        # Download if necessary
        # ----------------------------------------------------

        if (
            not next_item.filepath
            or not Path(next_item.filepath).exists()
        ):
            logger.info(
                "⬇️ Downloading queued track: %s",
                next_item.title,
            )

            track = TrackInfo(
                title=next_item.title,
                duration=next_item.duration,
                url=next_item.url,
                webpage_url=next_item.url,
                thumbnail="",
                uploader=next_item.requested_by,
                filepath=next_item.filepath,
            )

            filepath = await downloader.download(track)

            if filepath:
                next_item.filepath = filepath
                logger.info("✅ Download completed: %s", filepath)
            else:
                logger.error(
                    "❌ Download failed: %s",
                    next_item.title,
                )

        # ----------------------------------------------------
        # Play
        # ----------------------------------------------------

        if next_item.filepath:
            track = TrackInfo(
                title=next_item.title,
                duration=next_item.duration,
                url=next_item.url,
                webpage_url=next_item.url,
                thumbnail="",
                uploader=next_item.requested_by,
                filepath=next_item.filepath,
            )

            success = await player.play(chat_id, track)

            if success:
                logger.info(
                    "🎵 Now playing: %s",
                    next_item.title,
                )

                await db.remove_from_queue(next_item.id)
                await db.reorder_queue(chat_id)

            else:
                logger.error(
                    "❌ Playback failed: %s",
                    next_item.title,
                )

                await db.remove_from_queue(next_item.id)
                await db.reorder_queue(chat_id)

                await play_next(chat_id)

        else:
            logger.error(
                "❌ No filepath available: %s",
                next_item.title,
            )

            await db.remove_from_queue(next_item.id)
            await db.reorder_queue(chat_id)

            await play_next(chat_id)

    except Exception:
        logger.exception(
            "❌ play_next() failed for chat %s",
            chat_id,
        )


# ============================================================
# STREAM / PLAYOUT EVENTS
# ============================================================

def _register_voice_handlers():
    """
    Register pytgcalls dev24 callbacks.

    GroupCallFile does NOT provide:
        on_stream_end()
        on_kicked()
        on_left()

    The important callback for file playback is:
        on_playout_ended(group_call, filename)
    """

    if not VOICE_CHAT_AVAILABLE:
        logger.info("Voice handlers skipped: voice chat unavailable")
        return

    if not group_call:
        logger.warning("Voice handlers skipped: group_call is None")
        return

    # --------------------------------------------------------
    # PLAYOUT ENDED
    # --------------------------------------------------------

    if hasattr(group_call, "on_playout_ended"):

        @group_call.on_playout_ended
        async def on_playout_ended(call, filename):
            """
            Called when GroupCallFile finishes the input file.

            pytgcalls dev24 callback signature:
                (group_call, filename)
            """

            try:
                logger.info(
                    "🏁 Playout ended: %s",
                    filename,
                )

                if not player:
                    return

                chat_id = player.current_chat_id

                if not chat_id:
                    logger.warning(
                        "Playout ended but current_chat_id is empty"
                    )
                    return

                current_track = player.current_track

                # ------------------------------------------------
                # Repeat ONE
                # ------------------------------------------------

                settings = await db.get_chat_settings(chat_id)

                repeat_mode = settings.get(
                    "repeat_mode",
                    "off",
                )

                if repeat_mode == "one" and current_track:
                    logger.info(
                        "🔁 Repeat ONE: %s",
                        current_track.title,
                    )

                    success = await player.play(
                        chat_id,
                        current_track,
                    )

                    if not success:
                        logger.error(
                            "❌ Failed to repeat current track"
                        )
                        await play_next(chat_id)

                    return

                # ------------------------------------------------
                # Repeat ALL
                # ------------------------------------------------

                if repeat_mode == "all" and current_track:

                    logger.info(
                        "🔁 Repeat ALL: adding %s back to queue",
                        current_track.title,
                    )

                    queue = await db.get_queue(chat_id)

                    position = len(queue) + 1

                    item = QueueItem(
                        id=None,
                        chat_id=chat_id,
                        user_id=0,
                        title=current_track.title,
                        duration=current_track.duration,
                        url=current_track.url,
                        filepath=current_track.filepath,
                        requested_by="auto-repeat",
                        added_at=datetime.now(),
                        position=position,
                    )

                    await db.add_to_queue(item)

                # ------------------------------------------------
                # Clear player state before next track
                # ------------------------------------------------

                player.is_playing = False
                player.is_paused = False

                # ------------------------------------------------
                # NORMAL / ALL -> NEXT
                # ------------------------------------------------

                await play_next(chat_id)

            except Exception:
                logger.exception(
                    "❌ Error in on_playout_ended"
                )

    else:
        logger.warning(
            "⚠️ GroupCall object has no on_playout_ended()"
        )

    logger.info("✅ pytgcalls dev24 voice handlers registered")


# ============================================================
# TELEGRAM HANDLERS
# ============================================================

def _register_handlers():

    if not app:
        logger.warning(
            "Cannot register handlers: app is None"
        )
        return

    # Register voice callback first.
    _register_voice_handlers()

    # ========================================================
    # /start
    # ========================================================

    @app.on_message(
        filters.command("start", prefixes=PREFIX)
        & filters.private
    )
    async def start_cmd(client: Client, message: Message):

        if VOICE_CHAT_AVAILABLE:

            text = """
🎵 **ربات موزیک تلگرام** 🎵

این ربات می‌تواند در ویس کال‌های گروهی آهنگ پخش کند.

**دستورات اصلی:**
• `/play <نام یا لینک>` - اضافه کردن به صف و پخش
• `/queue` - نمایش صف پخش
• `/skip` - رد کردن آهنگ فعلی
• `/pause` - توقف موقت
• `/resume` - ادامه پخش
• `/stop` - توقف و خروج از کال
• `/volume <0-200>` - تنظیم صدا
• `/now` - آهنگ در حال پخش
• `/help` - راهنمای کامل

**نکات:**
• ربات باید ادمین گروه باشد
• ربات را به گروه اضافه و ادمین کنید
• ابتدا یک Voice Chat در گروه ایجاد کنید
• سپس از `/play` استفاده کنید
"""

        else:

            text = """
🎵 **ربات موزیک تلگرام** 🎵

⚠️ **Voice Chat در این محیط فعال نیست.**

فقط قابلیت دانلود موزیک فعال است.

**دستورات:**
• `/play <نام یا لینک>`
• `/queue`
• `/help`
"""

        await message.reply(text)

    # ========================================================
    # /help
    # ========================================================

    @app.on_message(
        filters.command("help", prefixes=PREFIX)
    )
    async def help_cmd(client: Client, message: Message):

        if VOICE_CHAT_AVAILABLE:

            text = """
🎵 **راهنمای ربات موزیک**

**പ്ലേബാക്ക്:**
• `/play <لینک/متن>` - اضافه کردن موزیک
• `/queue` - نمایش صف
• `/skip` - آهنگ بعدی
• `/pause` - توقف موقت
• `/resume` - ادامه
• `/stop` - توقف کامل
• `/now` - آهنگ فعلی
• `/volume <0-200>` - تنظیم صدا

**صف:**
• `/clear` - پاک کردن صف
• `/repeat <off|one|all>` - حالت تکرار

**مدیریت:**
• `/leave` - خروج از Voice Chat
"""

        else:

            text = """
🎵 **راهنمای ربات موزیک**

⚠️ Voice Chat در حال حاضر فعال نیست.

• `/play <نام یا لینک>` - دانلود موزیک
• `/queue` - نمایش صف
• `/clear` - پاک کردن صف
"""

        await message.reply(text)

    # ========================================================
    # /play
    # ========================================================

    @app.on_message(
        filters.command("play", prefixes=PREFIX)
        & filters.group
    )
    async def play_cmd(client: Client, message: Message):

        if len(message.command) < 2:
            await message.reply(
                "❌ لطفاً نام آهنگ یا لینک را وارد کنید.\n\n"
                "مثال:\n"
                "`/play shape of you`\n"
                "`/play https://youtube.com/...`"
            )
            return

        query = " ".join(message.command[1:])
        chat_id = message.chat.id
        user = message.from_user

        status_msg = await message.reply(
            "🔍 در حال جستجو..."
        )

        # ----------------------------------------------------
        # Extract
        # ----------------------------------------------------

        track = await downloader.extract_info(query)

        if not track:
            await status_msg.edit(
                "❌ موزیکی یافت نشد."
            )
            return

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        await status_msg.edit(
            f"⬇️ در حال دانلود:\n**{track.title}**"
        )

        filepath = await downloader.download(track)

        if not filepath:
            await status_msg.edit(
                "❌ خطا در دانلود موزیک."
            )
            return

        # ----------------------------------------------------
        # Queue
        # ----------------------------------------------------

        queue = await db.get_queue(chat_id)
        position = len(queue) + 1

        item = QueueItem(
            id=None,
            chat_id=chat_id,
            user_id=user.id,
            title=track.title,
            duration=track.duration,
            url=track.webpage_url,
            filepath=filepath,
            requested_by=(
                user.username
                or user.first_name
                or str(user.id)
            ),
            added_at=datetime.now(),
            position=position,
        )

        await db.add_to_queue(item)

        # ----------------------------------------------------
        # Playback
        # ----------------------------------------------------

        if VOICE_CHAT_AVAILABLE:

            if (
                not player.is_playing
                or player.current_chat_id != chat_id
            ):

                await status_msg.edit(
                    f"▶️ **{track.title}**\n"
                    "Voice Chat-ൽ പ്ലേ ചെയ്യുന്നു..."
                )

                await play_next(chat_id)

            else:

                await status_msg.edit(
                    f"✅ **{track.title}** queue-ലേക്ക് ചേർത്തു.\n"
                    f"📍 Position: `{position}`"
                )

        else:

            await status_msg.edit(
                f"✅ ഡൗൺലോഡ് ചെയ്തു:\n"
                f"**{track.title}**\n\n"
                f"📁 `{filepath}`"
            )

    # ========================================================
    # /queue
    # ========================================================

    @app.on_message(
        filters.command("queue", prefixes=PREFIX)
        & filters.group
    )
    async def queue_cmd(client: Client, message: Message):

        text = await get_queue_text(message.chat.id)

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔀 ഷഫിൾ",
                    callback_data="queue_shuffle",
                ),
                InlineKeyboardButton(
                    "🗑 ക്ലിയർ",
                    callback_data="queue_clear",
                ),
            ]
        ]

        if VOICE_CHAT_AVAILABLE:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "⏭ Skip",
                        callback_data="queue_skip",
                    ),
                    InlineKeyboardButton(
                        "⏸ Pause",
                        callback_data="queue_pause",
                    ),
                ]
            )

        await message.reply(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ========================================================
    # /skip
    # ========================================================

    @app.on_message(
        filters.command("skip", prefixes=PREFIX)
        & filters.group
    )
    async def skip_cmd(client: Client, message: Message):

        if not VOICE_CHAT_AVAILABLE:
            await message.reply(
                "❌ Voice Chat ലഭ്യമല്ല."
            )
            return

        chat_id = message.chat.id

        if (
            not player
            or player.current_chat_id != chat_id
            or not player.is_playing
        ):
            await message.reply(
                "❌ ഇപ്പോൾ ഒരു പാട്ടും പ്ലേ ചെയ്യുന്നില്ല."
            )
            return

        try:

            # Stop current file.
            # on_playout_ended is NOT fired by stop_playout(),
            # therefore explicitly start next track.
            group_call.stop_playout()

            player.is_playing = False
            player.is_paused = False

            await message.reply(
                "⏭️ Skip ചെയ്തു. അടുത്ത പാട്ട്..."
            )

            await play_next(chat_id)

        except Exception:

            logger.exception(
                "Skip failed"
            )

            await message.reply(
                "❌ Skip ചെയ്യുന്നതിൽ പിശക്."
            )

    # ========================================================
    # /pause
    # ========================================================

    @app.on_message(
        filters.command("pause", prefixes=PREFIX)
        & filters.group
    )
    async def pause_cmd(client: Client, message: Message):

        if not VOICE_CHAT_AVAILABLE:
            await message.reply(
                "❌ Voice Chat ലഭ്യമല്ല."
            )
            return

        chat_id = message.chat.id

        if (
            not player
            or player.current_chat_id != chat_id
            or not player.is_playing
        ):
            await message.reply(
                "❌ ഇപ്പോൾ പാട്ട് പ്ലേ ചെയ്യുന്നില്ല."
            )
            return

        if player.is_paused:
            await message.reply(
                "❌ പാട്ട് ഇതിനകം paused ആണ്."
            )
            return

        success = await player.pause(chat_id)

        if success:
            await message.reply(
                "⏸️ പാട്ട് pause ചെയ്തു."
            )
        else:
            await message.reply(
                "❌ Pause ചെയ്യാൻ കഴിഞ്ഞില്ല."
            )

    # ========================================================
    # /resume
    # ========================================================

    @app.on_message(
        filters.command("resume", prefixes=PREFIX)
        & filters.group
    )
    async def resume_cmd(client: Client, message: Message):

        if not VOICE_CHAT_AVAILABLE:
            await message.reply(
                "❌ Voice Chat ലഭ്യമല്ല."
            )
            return

        chat_id = message.chat.id

        if (
            not player
            or player.current_chat_id != chat_id
            or not player.is_paused
        ):
            await message.reply(
                "❌ Resume ചെയ്യാൻ paused track ഇല്ല."
            )
            return

        success = await player.resume(chat_id)

        if success:
            await message.reply(
                "▶️ പാട്ട് resume ചെയ്തു."
            )
        else:
            await message.reply(
                "❌ Resume ചെയ്യാൻ കഴിഞ്ഞില്ല."
            )

    # ========================================================
    # /stop
    # ========================================================

    @app.on_message(
        filters.command("stop", prefixes=PREFIX)
        & filters.group
    )
    async def stop_cmd(client: Client, message: Message):

        if not VOICE_CHAT_AVAILABLE:
            await message.reply(
                "❌ Voice Chat ലഭ്യമല്ല."
            )
            return

        chat_id = message.chat.id

        if (
            not player
            or player.current_chat_id != chat_id
        ):
            await message.reply(
                "❌ റബോട്ട് ഈ group-ലെ Voice Chat-ൽ ഇല്ല."
            )
            return

        try:

            success = await player.stop(chat_id)

            await db.clear_queue(chat_id)

            if success:
                await message.reply(
                    "⏹️ Playback നിർത്തി.\n"
                    "👋 Voice Chat-ൽ നിന്ന് പുറത്തുകടന്നു.\n"
                    "🗑 Queue clear ചെയ്തു."
                )
            else:
                await message.reply(
                    "❌ Stop ചെയ്യുന്നതിൽ പിശക്."
                )

        except Exception:

            logger.exception(
                "Stop command failed"
            )

            await message.reply(
                "❌ Stop ചെയ്യുന്നതിൽ പിശക്."
            )

    # ========================================================
    # /now
    # ========================================================

    @app.on_message(
        filters.command("now", prefixes=PREFIX)
        & filters.group
    )
    async def now_cmd(client: Client, message: Message):

        if (
            not VOICE_CHAT_AVAILABLE
            or not player
            or not player.current_track
            or player.current_chat_id != message.chat.id
        ):
            await message.reply(
                "❌ ഇപ്പോൾ പാട്ട് പ്ലേ ചെയ്യുന്നില്ല."
            )
            return

        track = player.current_track
        status = player.get_status()

        duration = (
            f"{track.duration // 60}:"
            f"{track.duration % 60:02d}"
            if track.duration > 0
            else "??:??"
        )

        text = (
            "🎵 **ഇപ്പോൾ പ്ലേ ചെയ്യുന്നത്:**\n\n"
            f"**{track.title}**\n\n"
            f"⏱ `{duration}`\n"
            f"🔊 `{status['volume']}%`\n"
            f"🔁 `{status['repeat_mode']}`"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⏭ Skip",
                        callback_data="queue_skip",
                    ),
                    InlineKeyboardButton(
                        "⏸ Pause",
                        callback_data="queue_pause",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔊 +",
                        callback_data="vol_up",
                    ),
                    InlineKeyboardButton(
                        "🔉 -",
                        callback_data="vol_down",
                    ),
                ],
            ]
        )

        await message.reply(
            text,
            reply_markup=keyboard,
        )

    # ========================================================
    # /volume
    # ========================================================

    @app.on_message(
        filters.command("volume", prefixes=PREFIX)
        & filters.group
    )
    async def volume_cmd(client: Client, message: Message):

        if not VOICE_CHAT_AVAILABLE:
            await message.reply(
                "❌ Voice Chat ലഭ്യമല്ല."
            )
            return

        if len(message.command) < 2:

            current = (
                player.volume
                if player
                else 100
            )

            await message.reply(
                f"🔊 നിലവിലെ volume: `{current}%`\n\n"
                "ഉപയോഗം:\n"
                "`/volume 100`"
            )
            return

        try:
            volume = int(message.command[1])
            volume = max(0, min(200, volume))

        except ValueError:
            await message.reply(
                "❌ 0 മുതൽ 200 വരെ ഒരു number നൽകുക."
            )
            return

        chat_id = message.chat.id

        if (
            not player
            or player.current_chat_id != chat_id
        ):
            await message.reply(
                "❌ റബോട്ട് Voice Chat-ൽ ഇല്ല."
            )
            return

        success = await player.set_volume(
            chat_id,
            volume,
        )

        if success:
            await db.update_chat_settings(
                chat_id,
                volume=volume,
            )

            await message.reply(
                f"🔊 Volume: `{volume}%`"
            )
        else:
            await message.reply(
                "❌ Volume മാറ്റാൻ കഴിഞ്ഞില്ല."
            )

    # ========================================================
    # /repeat
    # ========================================================

    @app.on_message(
        filters.command("repeat", prefixes=PREFIX)
        & filters.group
    )
    async def repeat_cmd(client: Client, message: Message):

        if not is_admin(message.from_user.id):
            await message.reply(
                "❌ ഇത് admin-കൾക്ക് മാത്രം."
            )
            return

        if len(message.command) < 2:

            settings = await db.get_chat_settings(
                message.chat.id
            )

            await message.reply(
                "🔁 Repeat mode: "
                f"`{settings.get('repeat_mode', 'off')}`\n\n"
                "ഉപയോഗം:\n"
                "`/repeat off`\n"
                "`/repeat one`\n"
                "`/repeat all`"
            )
            return

        mode = message.command[1].lower()

        if mode not in (
            "off",
            "one",
            "all",
        ):
            await message.reply(
                "❌ Valid modes: `off`, `one`, `all`"
            )
            return

        if player:
            player.repeat_mode = mode

        await db.update_chat_settings(
            message.chat.id,
            repeat_mode=mode,
        )

        await message.reply(
            f"🔁 Repeat mode: `{mode}`"
        )

    # ========================================================
    # /clear
    # ========================================================

    @app.on_message(
        filters.command("clear", prefixes=PREFIX)
        & filters.group
    )
    async def clear_cmd(client: Client, message: Message):

        if not is_admin(message.from_user.id):
            await message.reply(
                "❌ ഇത് admin-കൾക്ക് മാത്രം."
            )
            return

        count = await db.clear_queue(
            message.chat.id
        )

        await message.reply(
            f"🗑️ Queue clear ചെയ്തു.\n"
            f"Deleted: `{count}`"
        )

    # ========================================================
    # /leave
    # ========================================================

    @app.on_message(
        filters.command("leave", prefixes=PREFIX)
        & filters.group
    )
    async def leave_cmd(client: Client, message: Message):

        if not is_admin(message.from_user.id):
            await message.reply(
                "❌ ഇത് admin-കൾക്ക് മാത്രം."
            )
            return

        if not VOICE_CHAT_AVAILABLE:
            await message.reply(
                "❌ Voice Chat ലഭ്യമല്ല."
            )
            return

        chat_id = message.chat.id

        if (
            not player
            or player.current_chat_id != chat_id
        ):
            await message.reply(
                "❌ റബോട്ട് ഈ Voice Chat-ൽ ഇല്ല."
            )
            return

        await player.stop(chat_id)
        await db.clear_queue(chat_id)

        await message.reply(
            "👋 Voice Chat-ൽ നിന്ന് പുറത്തുകടന്നു.\n"
            "🗑️ Queue clear ചെയ്തു."
        )

    # ========================================================
    # CALLBACK QUERIES
    # ========================================================

    @app.on_callback_query()
    async def callback_handler(
        client: Client,
        query: CallbackQuery,
    ):

        data = query.data

        # ----------------------------------------------------
        # Limited mode
        # ----------------------------------------------------

        if (
            not VOICE_CHAT_AVAILABLE
            and data != "queue_clear"
        ):
            await query.answer(
                "❌ Voice Chat ലഭ്യമല്ല.",
                show_alert=True,
            )
            return

        if not query.message:
            await query.answer()
            return

        chat_id = query.message.chat.id

        # ----------------------------------------------------
        # SKIP
        # ----------------------------------------------------

        if data == "queue_skip":

            if (
                player
                and player.current_chat_id == chat_id
                and player.is_playing
            ):

                try:

                    group_call.stop_playout()

                    player.is_playing = False
                    player.is_paused = False

                    await query.answer(
                        "⏭️ Skip ചെയ്തു"
                    )

                    await play_next(chat_id)

                except Exception:

                    logger.exception(
                        "Callback skip failed"
                    )

                    await query.answer(
                        "❌ Skip failed",
                        show_alert=True,
                    )

            else:

                await query.answer(
                    "❌ പാട്ട് പ്ലേ ചെയ്യുന്നില്ല.",
                    show_alert=True,
                )

        # ----------------------------------------------------
        # PAUSE / RESUME
        # ----------------------------------------------------

        elif data == "queue_pause":

            if (
                player
                and player.current_chat_id == chat_id
                and player.is_playing
            ):

                if player.is_paused:

                    success = await player.resume(
                        chat_id
                    )

                    await query.answer(
                        "▶️ Resume ചെയ്തു"
                        if success
                        else "❌ Resume failed"
                    )

                else:

                    success = await player.pause(
                        chat_id
                    )

                    await query.answer(
                        "⏸️ Pause ചെയ്തു"
                        if success
                        else "❌ Pause failed"
                    )

            else:

                await query.answer(
                    "❌ പാട്ട് പ്ലേ ചെയ്യുന്നില്ല.",
                    show_alert=True,
                )

        # ----------------------------------------------------
        # CLEAR
        # ----------------------------------------------------

        elif data == "queue_clear":

            if not is_admin(
                query.from_user.id
            ):
                await query.answer(
                    "❌ Admin മാത്രം.",
                    show_alert=True,
                )
                return

            count = await db.clear_queue(
                chat_id
            )

            await query.answer(
                f"🗑️ {count} items deleted"
            )

            await query.message.edit_text(
                await get_queue_text(chat_id)
            )

        # ----------------------------------------------------
        # SHUFFLE
        # ----------------------------------------------------

        elif data == "queue_shuffle":

            if not is_admin(
                query.from_user.id
            ):
                await query.answer(
                    "❌ Admin മാത്രം.",
                    show_alert=True,
                )
                return

            await query.answer(
                "🔀 Shuffle ഇപ്പോൾ implement ചെയ്തിട്ടില്ല."
            )

        # ----------------------------------------------------
        # VOLUME UP
        # ----------------------------------------------------

        elif data == "vol_up":

            if (
                player
                and player.current_chat_id == chat_id
            ):

                new_volume = min(
                    200,
                    player.volume + 10,
                )

                success = await player.set_volume(
                    chat_id,
                    new_volume,
                )

                if success:

                    await db.update_chat_settings(
                        chat_id,
                        volume=new_volume,
                    )

                    await query.answer(
                        f"🔊 Volume: {new_volume}%"
                    )

                else:
                    await query.answer(
                        "❌ Volume failed",
                        show_alert=True,
                    )

        # ----------------------------------------------------
        # VOLUME DOWN
        # ----------------------------------------------------

        elif data == "vol_down":

            if (
                player
                and player.current_chat_id == chat_id
            ):

                new_volume = max(
                    0,
                    player.volume - 10,
                )

                success = await player.set_volume(
                    chat_id,
                    new_volume,
                )

                if success:

                    await db.update_chat_settings(
                        chat_id,
                        volume=new_volume,
                    )

                    await query.answer(
                        f"🔉 Volume: {new_volume}%"
                    )

                else:
                    await query.answer(
                        "❌ Volume failed",
                        show_alert=True,
                    )

        else:
            await query.answer()
