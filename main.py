#!/usr/bin/env python3
"""
Telegram Music Bot - Main Entry Point

PyTgCalls 3.0.0.dev24 compatible version.
Uses GroupCallFactory / GroupCallFile API.
"""

import asyncio
import logging
import sys
import signal
import os
import importlib.util
from pathlib import Path

from aiohttp import web

# ============================================================
# PROJECT PATH
# ============================================================

sys.path.insert(0, str(Path(__file__).parent))


# ============================================================
# IMPORTS
# ============================================================

from config import config, validate_config
from database import db
from player import downloader, MusicPlayer

print("🚨🚨🚨 MAIN.PY DEV24 VERSION IS RUNNING 🚨🚨🚨", flush=True)
print("🚨 MAIN FILE:", __file__, flush=True)

spec = importlib.util.find_spec("optional_deps")

print(
    "🚨 OPTIONAL_DEPS FILE:",
    spec.origin if spec else "NOT FOUND",
    flush=True
)


from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    check_voice_chat_support,
    get_platform_info
)

from handlers import set_bot_instances
from pyrogram import Client


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(
        logging,
        config.log_level.upper(),
        logging.INFO
    ),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


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
# GROUP CALL
# ============================================================

group_call = None

if VOICE_CHAT_AVAILABLE:

    try:

        # PyTgCalls dev24 API
        from pytgcalls import GroupCallFactory

        group_call = GroupCallFactory(
            app
        ).get_file_group_call()

        logger.info(
            "✅ GroupCallFactory initialized successfully"
        )

    except Exception as e:

        logger.error(
            "❌ Failed to initialize GroupCallFactory",
            exc_info=True
        )

        group_call = None

else:

    logger.info(
        "ℹ️ GroupCall skipped - voice chat unavailable"
    )


# ============================================================
# MUSIC PLAYER
# ============================================================

player = MusicPlayer(group_call)


# ============================================================
# SHUTDOWN EVENT
# ============================================================

shutdown_event = asyncio.Event()


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

async def health_server():

    async def health(request):

        return web.Response(
            text="Telegram Music Bot is running"
        )

    web_app = web.Application()

    web_app.router.add_get(
        "/",
        health
    )

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

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

    logger.info(
        "🚀 Starting Telegram Music Bot..."
    )


    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    await db.init()

    logger.info(
        "✅ Database initialized"
    )


    # --------------------------------------------------------
    # PYROGRAM
    # --------------------------------------------------------

    await app.start()

    logger.info(
        "✅ Pyrogram client started"
    )


    # --------------------------------------------------------
    # GROUP CALL
    # --------------------------------------------------------

    if group_call:

        try:

            await group_call.start()

            logger.info(
                "✅ GroupCall started"
            )

        except Exception as e:

            logger.error(
                "❌ GroupCall start failed",
                exc_info=True
            )

    else:

        logger.info(
            "ℹ️ GroupCall skipped"
        )


    # --------------------------------------------------------
    # REGISTER BOT INSTANCES
    # --------------------------------------------------------

    set_bot_instances(
        app,
        group_call,
        player,
        shutdown_event
    )


    # --------------------------------------------------------
    # BOT INFORMATION
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
    # READY
    # --------------------------------------------------------

    if group_call:

        logger.info(
            "🎵 Bot is ready!"
        )

        logger.info(
            "🎵 Send /play <song> in a group to start."
        )

    else:

        logger.info(
            "🎵 Bot is running in limited mode."
        )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():

    logger.info(
        "🛑 Shutting down..."
    )

    shutdown_event.set()


    # --------------------------------------------------------
    # STOP GROUP CALL
    # --------------------------------------------------------

    try:

        if group_call:

            await group_call.stop()

            logger.info(
                "✅ GroupCall stopped"
            )

    except Exception as e:

        logger.warning(
            f"Error stopping GroupCall: {e}"
        )


    # --------------------------------------------------------
    # STOP PYROGRAM
    # --------------------------------------------------------

    try:

        if app.is_connected:

            await app.stop()

            logger.info(
                "✅ Pyrogram stopped"
            )

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

def signal_handler(
    signum,
    frame
):

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

    loop = asyncio.get_event_loop()


    # --------------------------------------------------------
    # SIGNALS
    # --------------------------------------------------------

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

            pass


    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    try:

        await startup()

        await health_server()

        logger.info(
            "✅ Bot is now running."
        )

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
