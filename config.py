import os
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from optional_deps import (
    IS_ANDROID,
    IS_TERMUX,
    VOICE_CHAT_AVAILABLE,
)


class Config:
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    bot_token: str = os.getenv("BOT_TOKEN", "")

    session_name: str = os.getenv("SESSION_NAME", "music_bot")
    pytgcalls_session: str = os.getenv(
        "PYTGCALLS_SESSION",
        "pytgcalls_session"
    )

    db_path: str = os.getenv(
        "DB_PATH",
        "data/music_bot.db"
    )

    downloads_dir: str = os.getenv(
        "DOWNLOADS_DIR",
        "downloads"
    )

    admin_ids: List[int] = [
        int(x)
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip()
    ]

    command_prefix: str = os.getenv("COMMAND_PREFIX", "/")

    max_queue_size: int = int(
        os.getenv("MAX_QUEUE_SIZE", "50")
    )

    default_volume: int = int(
        os.getenv("DEFAULT_VOLUME", "100")
    )

    auto_leave_timeout: int = int(
        os.getenv("AUTO_LEAVE_TIMEOUT", "300")
    )

    ytdl_format: str = os.getenv(
        "YTDL_FORMAT",
        "bestaudio/best"
    )

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    log_file: str = os.getenv(
        "LOG_FILE",
        "logs/music_bot.log"
    )

    enable_voice_chat: bool = os.getenv(
        "ENABLE_VOICE_CHAT",
        "true" if VOICE_CHAT_AVAILABLE else "false"
    ).lower() == "true"


Path(Config().downloads_dir).mkdir(
    parents=True,
    exist_ok=True
)

Path(Config().db_path).parent.mkdir(
    parents=True,
    exist_ok=True
)

Path(Config().log_file).parent.mkdir(
    parents=True,
    exist_ok=True
)

config = Config()


def validate_config() -> List[str]:
    errors = []

    if config.api_id == 0:
        errors.append("API_ID is required")

    if not config.api_hash:
        errors.append("API_HASH is required")

    if not config.bot_token:
        errors.append("BOT_TOKEN is required")

    if config.default_volume < 0 or config.default_volume > 200:
        errors.append(
            "DEFAULT_VOLUME must be between 0 and 200"
        )

    if (
        config.enable_voice_chat
        and not VOICE_CHAT_AVAILABLE
    ):
        errors.append(
            "Voice chat dependencies are unavailable"
        )

    return errors
