#!/usr/bin/env python3
"""
Telegram Music Bot - Main Entry Point
A self-bot for playing music in Telegram group voice calls.
Gracefully handles environments where PyTgCalls is not available.
"""

import asyncio
import logging
import sys
import signal
import os
from pathlib import Path

from aiohttp import web

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import config, validate_config
from database import db
from player import downloader, MusicPlayer
from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    PyTgCalls,
    check_voice_chat_support,
    get_platform_info
)
from handlers import set_bot_instances
from pyrogram import Client


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

# ============================================================
# PLATFORM INFORMATION
# ============================================================

platform_info = get_platform_info()

logger.info("=== Platform Info ===")

for key, value in platform_info.items():
    logger.info(f"  {key}: {value}")

logger.info("=====================")


# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

errors = validate_config()

if errors:
    logger.error("Configuration errors:")

    for error in errors:
        logger.error(f"  - {error}")

    sys.exit(1)


# ============================================================
# VOICE CHAT STATUS
# ============================================================

voice_supported, voice_msg = check_voice_chat_support()

if VOICE_CHAT_AVAILABLE:
    logger.info("✅ Voice chat: AVAILABLE")
else:
    logger.warning(
        f"⚠️ Voice chat: NOT AVAILABLE - {voice_msg}"
    )


# ============================================================
# PYROGRAM CLIENT
# ============================================================

app = Client(
    config.session_name,
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token
)


# ============================================================
# PYTGCalls
# ============================================================

pytgcalls = None

if VOICE_CHAT_AVAILABLE:
    pytgcalls = PyTgCalls(app)


# ============================================================
# MUSIC PLAYER
# ============================================================

player = MusicPlayer(pytgcalls)


# ============================================================
# SHUTDOWN EVENT
# ============================================================

shutdown_event = asyncio.Event()


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

async def health_server():
    """
    Small HTTP server required by Render Web Service.
    Render checks this port to determine whether the service is alive.
    """

    async def health(request):
        return web.Response(
            text="Telegram Music Bot is running"
        )

    web_app = web.Application()

    web_app.router.add_get("/", health)

    # Render provides PORT automatically.
    # 10000 is used as fallback for local testing.
    port = int(os.environ.get("PORT", 10000))

    runner = web.AppRunner(web_app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logger.info(
        f"🌐 Health server started on port {port}"
    )


# ============================================================
# STARTUP
# ============================================================

async def startup():
    """Initialize database and start clients."""

    logger.info(
        "🚀 Starting Telegram Music Bot..."
    )

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    await db.init()

    logger.info(
        "✅ Database initialized"
    )

    # --------------------------------------------------------
    # Pyrogram
    # --------------------------------------------------------

    await app.start()

    logger.info(
        "✅ Pyrogram client started"
    )

    # --------------------------------------------------------
    # PyTgCalls
    # --------------------------------------------------------

    if pytgcalls:

        await pytgcalls.start()

        logger.info(
            "✅ PyTgCalls started"
        )

    else:

        logger.info(
            "ℹ️ PyTgCalls skipped "
            "(not available on this platform)"
        )

    # --------------------------------------------------------
    # Register bot instances
    # --------------------------------------------------------

    set_bot_instances(
        app,
        pytgcalls,
        player,
        shutdown_event
    )

    # --------------------------------------------------------
    # Get bot information
    # --------------------------------------------------------

    me = await app.get_me()

    logger.info(
        f"🤖 Bot: @{me.username} ({me.first_name})"
    )

    logger.info(
        f"📋 Admin IDs: "
        f"{config.admin_ids if config.admin_ids else 'All users'}"
    )

    # --------------------------------------------------------
    # Ready message
    # --------------------------------------------------------

    if VOICE_CHAT_AVAILABLE:

        logger.info(
            "🎵 Bot is ready! "
            "Send /play <song> in a group to start."
        )

    else:

        logger.info(
            "🎵 Bot is ready "
            "(LIMITED MODE - no voice chat). "
            "Send /play <song> to download music."
        )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():
    """Graceful shutdown."""

    logger.info(
        "🛑 Shutting down..."
    )

    shutdown_event.set()

    # --------------------------------------------------------
    # Leave active voice calls
    # --------------------------------------------------------

    try:

        if pytgcalls:

            await pytgcalls.leave_all_calls()

    except Exception as e:

        logger.warning(
            f"Error leaving calls: {e}"
        )

    # --------------------------------------------------------
    # Stop PyTgCalls
    # --------------------------------------------------------

    try:

        if pytgcalls:

            await pytgcalls.stop()

    except Exception as e:

        logger.warning(
            f"Error stopping PyTgCalls: {e}"
        )

    # --------------------------------------------------------
    # Stop Pyrogram
    # --------------------------------------------------------

    try:

        if app.is_connected:

            await app.stop()

    except Exception as e:

        logger.warning(
            f"Error stopping Pyrogram: {e}"
        )

    logger.info(
        "✅ Shutdown complete"
    )


# ============================================================
# SIGNAL HANDLER
# ============================================================

def signal_handler(signum, frame):

    logger.info(
        f"Received signal {signum}"
    )

    try:

        asyncio.create_task(
            shutdown()
        )

    except RuntimeError:

        pass


# ============================================================
# MAIN
# ============================================================

async def main():

    # --------------------------------------------------------
    # Register shutdown signals
    # --------------------------------------------------------

    loop = asyncio.get_event_loop()

    for sig in (
        signal.SIGTERM,
        signal.SIGINT
    ):

        try:

            loop.add_signal_handler(
                sig,
                signal_handler,
                sig,
                None
            )

        except NotImplementedError:

            # Windows doesn't support
            # add_signal_handler
            pass

    # --------------------------------------------------------
    # Start bot
    # --------------------------------------------------------

    try:

        await startup()

        # ----------------------------------------------------
        # Start Render HTTP health server
        # ----------------------------------------------------

        await health_server()

        # ----------------------------------------------------
        # Keep bot running
        # ----------------------------------------------------

        await shutdown_event.wait()

    except Exception as e:

        logger.error(
            f"❌ Fatal error: {e}",
            exc_info=True
        )

    finally:

        await shutdown()


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        pass

    except Exception as e:

        logger.error(
            f"❌ Fatal error: {e}",
            exc_info=True
        )

        sys.exit(1)
