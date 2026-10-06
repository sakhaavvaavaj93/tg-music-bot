"""
Optional dependencies handler for Telegram Music Bot.

Compatible with:
    pytgcalls==3.0.0.dev24
    tgcalls==3.0.0.dev6

Uses the dev24 GroupCallFactory / GroupCallFile API.
"""

import sys
import platform


# ============================================================
# DEBUG INFORMATION
# ============================================================

print(
    "🚨🚨🚨 OPTIONAL_DEPS DEV24 VERSION IS RUNNING 🚨🚨🚨",
    flush=True
)

print(
    "🚨 Python:",
    sys.version,
    flush=True
)

print(
    "🚨 File:",
    __file__,
    flush=True
)


# ============================================================
# PLATFORM DETECTION
# ============================================================

IS_ANDROID = (
    sys.platform == "android"
    or "android" in platform.platform().lower()
)

IS_TERMUX = (
    "com.termux" in platform.platform().lower()
    or "TERMUX" in platform.platform().upper()
)

IS_LINUX = (
    sys.platform.startswith("linux")
    and not IS_ANDROID
)

IS_WINDOWS = sys.platform == "win32"

IS_MACOS = sys.platform == "darwin"


print(
    "🔍 Platform:",
    platform.platform(),
    flush=True
)

print(
    "🔍 Machine:",
    platform.machine(),
    flush=True
)

print(
    "🔍 IS_LINUX:",
    IS_LINUX,
    flush=True
)

print(
    "🔍 IS_ANDROID:",
    IS_ANDROID,
    flush=True
)


# ============================================================
# DEFAULT VOICE CHAT STATUS
# ============================================================

VOICE_CHAT_AVAILABLE = not IS_ANDROID

print(
    "🔍 DEBUG 1 - Initial VOICE_CHAT_AVAILABLE:",
    VOICE_CHAT_AVAILABLE,
    flush=True
)


# ============================================================
# DEV24 API OBJECTS
# ============================================================

GroupCallFactory = None
GroupCallFile = None

# Compatibility placeholders
PyTgCalls = None
Update = None
AudioVideoPiped = None
AudioPiped = None
NoActiveGroupCall = None
GroupCallNotFound = None


# ============================================================
# PYTGCalls DEV24 IMPORT
# ============================================================

if VOICE_CHAT_AVAILABLE:

    try:

        print(
            "🔍 Attempting PyTgCalls dev24 imports...",
            flush=True
        )

        # ----------------------------------------------------
        # Main dev24 API
        # ----------------------------------------------------

        from pytgcalls import GroupCallFactory as _GroupCallFactory

        GroupCallFactory = _GroupCallFactory

        print(
            "✅ GroupCallFactory imported successfully!",
            flush=True
        )


        # ----------------------------------------------------
        # GroupCallFile
        # ----------------------------------------------------

        try:

            from pytgcalls import GroupCallFile as _GroupCallFile

            GroupCallFile = _GroupCallFile

            print(
                "✅ GroupCallFile imported successfully!",
                flush=True
            )

        except ImportError as e:

            print(
                "⚠️ GroupCallFile direct import failed:",
                repr(e),
                flush=True
            )


        # ----------------------------------------------------
        # Check package version
        # ----------------------------------------------------

        try:

            import pytgcalls

            version = getattr(
                pytgcalls,
                "__version__",
                "unknown"
            )

            print(
                "✅ pytgcalls version:",
                version,
                flush=True
            )

        except Exception:

            print(
                "⚠️ Could not determine pytgcalls version",
                flush=True
            )


        print(
            "🎉 PyTgCalls dev24 API is AVAILABLE!",
            flush=True
        )


    except Exception as e:

        print("=" * 70, flush=True)

        print(
            "❌ PYTGCalls DEV24 IMPORT FAILED",
            flush=True
        )

        print(
            "❌ Error type:",
            type(e).__name__,
            flush=True
        )

        print(
            "❌ Error:",
            repr(e),
            flush=True
        )

        print(
            "❌ Platform:",
            platform.platform(),
            flush=True
        )

        print(
            "❌ Python:",
            sys.version,
            flush=True
        )

        print("=" * 70, flush=True)

        import traceback

        traceback.print_exc()

        VOICE_CHAT_AVAILABLE = False

        GroupCallFactory = None
        GroupCallFile = None


else:

    print(
        "ℹ️ Android detected - voice chat disabled",
        flush=True
    )


# ============================================================
# FINAL VOICE STATUS
# ============================================================

print(
    "🔍 DEBUG 2 - Final VOICE_CHAT_AVAILABLE:",
    VOICE_CHAT_AVAILABLE,
    flush=True
)

print(
    "🔍 DEBUG 3 - GroupCallFactory:",
    GroupCallFactory,
    flush=True
)

print(
    "🔍 DEBUG 4 - GroupCallFile:",
    GroupCallFile,
    flush=True
)


# ============================================================
# PSUTIL
# ============================================================

psutil = None
HAS_PSUTIL = False

if not IS_ANDROID:

    try:

        import psutil as _psutil

        psutil = _psutil
        HAS_PSUTIL = True

        print(
            "✅ psutil available",
            flush=True
        )

    except ImportError:

        print(
            "⚠️ psutil not installed",
            flush=True
        )


# ============================================================
# VOICE CHAT SUPPORT CHECK
# ============================================================

def check_voice_chat_support() -> tuple[bool, str]:
    """
    Check whether Telegram voice chat is supported.
    """

    if IS_ANDROID:

        if IS_TERMUX:

            return (
                False,
                "Voice chat is not supported on Termux (Android). "
                "Run the bot on Linux/Windows/macOS."
            )

        return (
            False,
            "Voice chat is not supported on Android."
        )


    if not VOICE_CHAT_AVAILABLE:

        return (
            False,
            "PyTgCalls dev24 could not be loaded."
        )


    if GroupCallFactory is None:

        return (
            False,
            "GroupCallFactory is unavailable."
        )


    return (
        True,
        "Voice chat is supported on this platform."
    )


# ============================================================
# PLATFORM INFORMATION
# ============================================================

def get_platform_info() -> dict:

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

        "group_call_factory": (
            GroupCallFactory is not None
        ),

        "group_call_file": (
            GroupCallFile is not None
        ),

        "has_psutil": HAS_PSUTIL,
    }


    # --------------------------------------------------------
    # PyTgCalls version
    # --------------------------------------------------------

    if VOICE_CHAT_AVAILABLE:

        try:

            import pytgcalls

            info["pytgcalls_version"] = getattr(
                pytgcalls,
                "__version__",
                "unknown"
            )

        except Exception:

            info["pytgcalls_version"] = "unknown"


    return info


# ============================================================
# PRINT PLATFORM INFO
# ============================================================

def print_platform_info():

    info = get_platform_info()

    print(
        "=== Platform Info ==="
    )

    for key, value in info.items():

        print(
            f"  {key}: {value}"
        )

    print(
        "====================="
    )


# ============================================================
# EXPORTS
# ============================================================

__all__ = [

    # Status
    "VOICE_CHAT_AVAILABLE",

    # Platform
    "IS_ANDROID",
    "IS_TERMUX",
    "IS_LINUX",
    "IS_WINDOWS",
    "IS_MACOS",

    # dev24 API
    "GroupCallFactory",
    "GroupCallFile",

    # Compatibility
    "PyTgCalls",
    "Update",
    "AudioVideoPiped",
    "AudioPiped",
    "NoActiveGroupCall",
    "GroupCallNotFound",

    # Optional dependency
    "psutil",
    "HAS_PSUTIL",

    # Functions
    "check_voice_chat_support",
    "get_platform_info",
    "print_platform_info",
]
