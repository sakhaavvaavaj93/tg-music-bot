#!/usr/bin/env python3

import asyncio
import logging
import sys
import signal
import os
import importlib.util
from pathlib import Path

from aiohttp import web

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

print("🚨🚨🚨 MAIN.PY DEV24 VERSION IS RUNNING 🚨🚨🚨", flush=True)
print(f"🚨 MAIN FILE: {__file__}", flush=True)

spec = importlib.util.find_spec("optional_deps")
print(
    "🚨 OPTIONAL_DEPS FILE:",
    spec.origin if spec else "NOT FOUND",
    flush=True
)

from config import config, validate_config
from database import db
from player import MusicPlayer

from optional_deps import (
    VOICE_CHAT_AVAILABLE,
    check_voice_chat_support,
    get_platform_info,
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
        logging.INFO,
    ),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(config.log_file),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


# ============================================================
# PLATFORM
# ============================================================

platform_info = get_platform_info()

logger.info("=== Platform Info ===")

for key, value in platform_info.items():
    logger.info(f"  {key}: {value}")

logger.info("=====================")


# ============================================================
# CONFIG
# ============================================================

errors = validate_config()

if errors:
    logger.error("Configuration errors:")

    for error in errors:
        logger.error(f"  - {error}")

    sys.exit(1)


# ============================================================
# VOICE CHAT
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
    bot_token=config.bot_token,
)


# ============================================================
# GROUP CALL
# ============================================================

group_call = None

if VOICE_CHAT_AVAILABLE:

    try:

        from pytgcalls import GroupCallFactory

        group_call = (
            GroupCallFactory(app)
            .get_file_group_call(
                play_on_repeat=False
            )
        )

        logger.info(
            "✅ GroupCallFactory initialized successfully"
        )

        logger.info(
            "🎙️ GroupCallFile created successfully"
        )

    except Exception:

        logger.error(
            "❌ Failed to initialize GroupCallFactory",
            exc_info=True,
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
# SHUTDOWN STATE
# ============================================================

shutdown_event = asyncio.Event()

_shutdown_started = False

_health_runner = None


# ============================================================
# HEALTH SERVER
# ============================================================

async def health_server():

    async def health(request):

        return web.Response(
            text="Telegram Music Bot is running",
            status=200,
        )

    web_app = web.Application()

    web_app.router.add_get("/", health)

    web_app.router.add_get("/health", health)

    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    runner = web.AppRunner(web_app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port,
    )

    await site.start()

    logger.info(
        f"🌐 Health server started on port {port}"
    )

    return runner


# ============================================================
# STARTUP
# ============================================================


async def startup():

    global _health_runner

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
    # TEMPORARY TELEGRAM UPDATE TEST
    # IMPORTANT: register BEFORE app.start()
    # --------------------------------------------------------

    @app.on_message()
    async def debug_all_messages(client, message):

        logger.info(
            f"📨 DEBUG UPDATE RECEIVED | "
            f"chat_id={message.chat.id if message.chat else None} | "
            f"text={message.text!r}"
        )

    logger.info(
        "🧪 Telegram debug update handler registered"
    )

    # --------------------------------------------------------
    # PYROGRAM
    # --------------------------------------------------------

    await app.start()

    logger.info(
        "✅ Pyrogram client started"
    )

    # --------------------------------------------------------
    # BOT INFORMATION
    # --------------------------------------------------------

    me = await app.get_me()

    logger.info(
        f"🤖 Bot: @{me.username} ({me.first_name})"
    )

    # --------------------------------------------------------
    # GROUP CALL
    # --------------------------------------------------------

    if group_call:

        logger.info(
            "🎙️ GroupCallFile ready."
        )

        logger.info(
            "🎙️ It will join a Voice Chat when /play is used."
        )

    else:

        logger.info(
            "ℹ️ GroupCall unavailable."
        )

    # --------------------------------------------------------
    # REGISTER HANDLERS
    # --------------------------------------------------------

    set_bot_instances(
        app,
        group_call,
        player,
        shutdown_event,
    )

    logger.info(
        "✅ Handlers registered"
    )

    # --------------------------------------------------------
    # ADMIN INFORMATION
    # --------------------------------------------------------

    logger.info(
        "📋 Admin IDs: "
        f"{config.admin_ids if config.admin_ids else 'All users'}"
    )

    # --------------------------------------------------------
    # HEALTH SERVER
    # --------------------------------------------------------

    _health_runner = await health_server()

    # --------------------------------------------------------
    # READY
    # --------------------------------------------------------

    logger.info(
        "🎵 Bot is ready!"
    )

    logger.info(
        "🎵 Send /start to the bot or /play <song> in a group."
    )

    logger.info(
        "✅ Bot is now running."
    )


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():

    global _shutdown_started
    global _health_runner

    if _shutdown_started:

        logger.info(
            "ℹ️ Shutdown already in progress."
        )

        return

    _shutdown_started = True

    logger.info(
        "🛑 Shutting down..."
    )

    # --------------------------------------------------------
    # HEALTH SERVER
    # --------------------------------------------------------

    try:

        if _health_runner:

            await _health_runner.cleanup()

            _health_runner = None

            logger.info(
                "✅ Health server stopped"
            )

    except Exception as e:

        logger.warning(
            f"Error stopping health server: {e}"
        )

    # --------------------------------------------------------
    # GROUP CALL
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
    # PYROGRAM
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

def signal_handler(signum):

    logger.info(
        f"Received signal {signum}"
    )

    shutdown_event.set()


# ============================================================
# MAIN
# ============================================================

async def main():

    loop = asyncio.get_running_loop()

    # --------------------------------------------------------
    # SIGNALS
    # --------------------------------------------------------

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):

        try:

            loop.add_signal_handler(
                sig,
                signal_handler,
                sig,
            )

            logger.info(
                f"✅ Signal handler installed for {sig.name}"
            )

        except (
            NotImplementedError,
            RuntimeError,
        ) as e:

            logger.warning(
                f"Could not install handler for {sig.name}: {e}"
            )

    startup_success = False

    try:

        await startup()

        startup_success = True

        # Keep process alive
        await shutdown_event.wait()

    except asyncio.CancelledError:

        logger.info(
            "Main task cancelled."
        )

    except Exception as e:

        logger.error(
            f"❌ Fatal error: {e}",
            exc_info=True,
        )

    finally:

        if startup_success or app.is_connected:

            await shutdown()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        pass

    except Exception as e:

        logger.error(
            f"❌ Fatal error: {e}",
            exc_info=True,
        )

        sys.exit(1)
