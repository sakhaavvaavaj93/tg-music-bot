
"""
Optional dependencies handler for Telegram Music Bot.

This module gracefully handles missing PyTgCalls/tgcalls on Android/Termux platforms.
All voice chat related imports are wrapped in try/except and feature flags are provided.
"""

import sys
import platform
from typing import Optional, Any

print("🚨🚨🚨 NEW OPTIONAL_DEPS.PY IS RUNNING 🚨🚨🚨", flush=True)
print("🚨 Python:", sys.version, flush=True)
print("🚨 File:", __file__, flush=True)

# Platform detection
IS_ANDROID = sys.platform == "android" or "android" in platform.platform().lower()
IS_TERMUX = "com.termux" in platform.platform().lower() or "TERMUX" in platform.platform().upper()
IS_LINUX = sys.platform.startswith("linux") and not IS_ANDROID
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# Voice chat availability (default to available on non-Android)
VOICE_CHAT_AVAILABLE = not IS_ANDROID
print("🔍 DEBUG 1 - Initial VOICE_CHAT_AVAILABLE:", VOICE_CHAT_AVAILABLE)


class _DummyType:
    """Dummy type that works with typing but raises on actual use."""
    def __init__(self, name: str, error: Exception):
        self._name = name
        self._error = error
    
    def __getattr__(self, item):
        # Only raise when actually used, not during typing inspection
        raise ImportError(
            f"'{self._name}' is not available on this platform. "
            f"Original error: {self._error}"
        )
    
    def __call__(self, *args, **kwargs):
        raise ImportError(
            f"'{self._name}' is not available on this platform. "
            f"Original error: {self._error}"
        )
    
    # Make it work with typing
    def __class_getitem__(cls, item):
        return cls
    
    def __instancecheck__(cls, instance):
        return False
    
    def __subclasscheck__(cls, subclass):
        return False


# Try to import PyTgCalls
PyTgCalls = None
Update = None
AudioVideoPiped = None
AudioPiped = None
NoActiveGroupCall = None
GroupCallNotFound = None

if VOICE_CHAT_AVAILABLE:
    try:
        from pytgcalls import PyTgCalls as _PyTgCalls
        from pytgcalls.types import Update as _Update
        from pytgcalls.types.stream import (
            AudioVideoPiped as _AudioVideoPiped,
            AudioPiped as _AudioPiped
        )
        from pytgcalls.exceptions import (
            NoActiveGroupCall as _NoActiveGroupCall,
            GroupCallNotFound as _GroupCallNotFound
        )

        PyTgCalls = _PyTgCalls
        Update = _Update
        AudioVideoPiped = _AudioVideoPiped
        AudioPiped = _AudioPiped
        NoActiveGroupCall = _NoActiveGroupCall
        GroupCallNotFound = _GroupCallNotFound

        print("✅ PyTgCalls imported successfully!", flush=True)

    except Exception as e:
        print("=" * 60, flush=True)
        print("❌ PYTGCalls IMPORT FAILED", flush=True)
        print("❌ Error type:", type(e).__name__, flush=True)
        print("❌ Error:", repr(e), flush=True)
        print("❌ Platform:", platform.platform(), flush=True)
        print("❌ Python:", sys.version, flush=True)
        print("=" * 60, flush=True)

        import traceback
        traceback.print_exc()

        VOICE_CHAT_AVAILABLE = False

        _missing = _DummyType("pytgcalls", e)

        PyTgCalls = _missing
        Update = _missing
        AudioVideoPiped = _missing
        AudioPiped = _missing
        NoActiveGroupCall = _missing
        GroupCallNotFound = _missing

print(
    "🔍 DEBUG 2 - Final VOICE_CHAT_AVAILABLE:",
    VOICE_CHAT_AVAILABLE,
    flush=True
)

print(
    "🔍 DEBUG 3 - PyTgCalls object:",
    PyTgCalls,
    flush=True
)

# Try to import psutil (optional, for system stats)      
psutil = None
HAS_PSUTIL = False

if not IS_ANDROID:
    try:
        import psutil as _psutil
        psutil = _psutil
        HAS_PSUTIL = True
    except ImportError:
        pass


def check_voice_chat_support() -> tuple[bool, str]:
    """
    Check if voice chat is supported on this platform.
    
    Returns:
        tuple: (is_supported, message)
    """
    if IS_ANDROID:
        if IS_TERMUX:
            return False, (
                "Voice chat is not supported on Termux (Android).\n"
                "The 'tgcalls' native library has no pre-built wheels for Android.\n"
                "To use voice chat features, run this bot on Linux/Windows/macOS."
            )
        else:
            return False, (
                "Voice chat is not supported on Android.\n"
                "The 'tgcalls' native library has no pre-built wheels for Android."
            )
    return True, "Voice chat is supported on this platform."


def get_platform_info() -> dict:
    """Get detailed platform information."""
    info = {
        "system": platform.system(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": sys.version,
        "is_android": IS_ANDROID,
        "is_termux": IS_TERMUX,
        "is_linux": IS_LINUX,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "voice_chat_available": VOICE_CHAT_AVAILABLE,
        "has_psutil": HAS_PSUTIL,
    }
    
    # Add pytgcalls version if available
    if VOICE_CHAT_AVAILABLE:
        try:
            import pytgcalls
            info["pytgcalls_version"] = pytgcalls.__version__
        except Exception:
            info["pytgcalls_version"] = "unknown"
    
    return info


def print_platform_info():
    """Print platform information for debugging."""
    info = get_platform_info()
    print("=== Platform Info ===")
    for key, value in info.items():
        print(f"  {key}: {value}")
    print("=====================")


# Export all
__all__ = [
    "VOICE_CHAT_AVAILABLE",
    "HAS_PSUTIL",
    "IS_ANDROID",
    "IS_TERMUX",
    "IS_LINUX",
    "IS_WINDOWS",
    "IS_MACOS",
    "PyTgCalls",
    "Update",
    "AudioVideoPiped",
    "AudioPiped",
    "NoActiveGroupCall",
    "GroupCallNotFound",
    "psutil",
    "check_voice_chat_support",
    "get_platform_info",
    "print_platform_info",
]
