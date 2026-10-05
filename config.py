#!/usr/bin/env python3
"""
Telegram Music Bot - Example Configuration
Copy this file to config.py and fill in your values.
Or set environment variables (recommended for production).
"""

import os
from pathlib import Path
from typing import List

# Load .env file if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import platform utilities for detection
try:
    from optional_deps import IS_ANDROID, IS_TERMUX, VOICE_CHAT_AVAILABLE
except ImportError:
    # Fallback if optional_deps not available
    import sys
    import platform as pf
    IS_ANDROID = sys.platform == "android" or "android" in pf.platform().lower()
    IS_TERMUX = "com.termux" in pf.platform().lower()
    VOICE_CHAT_AVAILABLE = not IS_ANDROID


class Config:
    # ===== REQUIRED: Telegram API Credentials =====
    # Get from https://my.telegram.org/apps
    api_id: int = int(os.getenv("API_ID", "0"))           # e.g., 1234567
    api_hash: str = os.getenv("API_HASH", "")             # e.g., "abcdef123456..."
    
    # ===== REQUIRED: Bot Token =====
    # Get from @BotFather
    bot_token: str = os.getenv("BOT_TOKEN", "")           # e.g., "123456789:ABC-DEF..."
    
    # ===== Optional Settings =====
    session_name: str = os.getenv("SESSION_NAME", "music_bot")
    pytgcalls_session: str = os.getenv("PYTGCALLS_SESSION", "pytgcalls_session")
    
    # Database & Storage
    db_path: str = os.getenv("DB_PATH", "data/music_bot.db")
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads")
    
    # Admin user IDs (comma-separated) - for admin-only commands
    admin_ids: List[int] = [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ]
    
    # Command prefix
    command_prefix: str = os.getenv("COMMAND_PREFIX", "/")
    
    # Limits
    max_queue_size: int = int(os.getenv("MAX_QUEUE_SIZE", "50"))
    default_volume: int = int(os.getenv("DEFAULT_VOLUME", "100"))   # 0-200
    auto_leave_timeout: int = int(os.getenv("AUTO_LEAVE_TIMEOUT", "300"))  # seconds, 0 = disabled
    
    # yt-dlp format preference
    ytdl_format: str = os.getenv("YTDL_FORMAT", "bestaudio/best")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "logs/music_bot.log")
    
    # ===== Platform-specific Settings =====
    # Voice chat is disabled by default on Android/Termux
    enable_voice_chat: bool = os.getenv("ENABLE_VOICE_CHAT", "true" if VOICE_CHAT_AVAILABLE else "false").lower() == "true"
    
    @property
    def voice_chat_warning(self) -> str:
        if self.enable_voice_chat and not VOICE_CHAT_AVAILABLE:
            return "⚠️ Voice chat enabled but tgcalls/pytgcalls not available on this platform (Android/Termux). Voice features will not work."
        return ""


# Create necessary directories
Path(Config().downloads_dir).mkdir(parents=True, exist_ok=True)
Path(Config().db_path).parent.mkdir(parents=True, exist_ok=True)
Path(Config().log_file).parent.mkdir(parents=True, exist_ok=True)

# Global config instance
config = Config()


def validate_config() -> List[str]:
    """Validate configuration and return list of errors (empty if valid)."""
    errors = []
    
    if config.api_id == 0:
        errors.append("API_ID is required (get from https://my.telegram.org/apps)")
    
    if not config.api_hash:
        errors.append("API_HASH is required (get from https://my.telegram.org/apps)")
    
    if not config.bot_token:
        errors.append("BOT_TOKEN is required (get from @BotFather)")
    
    if config.bot_token and not (config.bot_token.startswith(("1", "2")) and ":" in config.bot_token):
        errors.append("BOT_TOKEN format looks invalid (should be like '123456:ABC-DEF...')")
    
    if config.default_volume < 0 or config.default_volume > 200:
        errors.append("DEFAULT_VOLUME must be between 0 and 200")
    
    if config.enable_voice_chat and not VOICE_CHAT_AVAILABLE:
        errors.append("Voice chat is enabled but tgcalls/pytgcalls are not available on this platform")
    
    return errors


# Backward compatibility (deprecated)
API_ID = config.api_id
API_HASH = config.api_hash
BOT_TOKEN = config.bot_token
SESSION_NAME = config.session_name
DB_PATH = config.db_path
DOWNLOADS_DIR = config.downloads_dir
ADMIN_IDS = config.admin_ids
COMMAND_PREFIX = config.command_prefix
MAX_QUEUE_SIZE = config.max_queue_size
DEFAULT_VOLUME = config.default_volume
AUTO_LEAVE_TIMEOUT = config.auto_leave_timeout
YTDL_FORMAT = config.ytdl_format
LOG_LEVEL = config.log_level
LOG_FILE = config.log_file
