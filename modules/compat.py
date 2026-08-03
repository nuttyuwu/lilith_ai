"""
Cross-platform foundation shared by every Lilith module.

Everything in here exists so the rest of the codebase never has to ask
"am I on Windows or Linux?" and never has to guess where the project root is.

Key guarantees provided:
  * BASE_DIR is the project root no matter what the current directory is.
  * config.ini is always found, always UTF-8, always has every key.
  * stdout/stderr can print Lilith's emoji on a Windows console.
  * Tk windows are not blurry on a Windows 11 HiDPI display.
  * Log files are UTF-8 and rotate instead of growing forever.
"""

from __future__ import annotations

import configparser
import logging
import logging.handlers
import os
import platform
import socket
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Platform identity
# --------------------------------------------------------------------------

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"

MIN_PYTHON = (3, 10)

# --------------------------------------------------------------------------
# Paths -- resolved from this file, never from the current working directory
# --------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.ini"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.ini"

# Where the GGUF comes from. Lilith never downloads it -- the file is fetched
# by hand and dropped into models/ -- so this URL exists only to be printed at
# the person who has not done that yet. Kept here rather than inline so the
# backend, the doctor and the README cannot drift apart.
MODEL_REVISION = "3b594a5d27c27a841e57e6a6c7938b303df4f099"
MODEL_SHA256 = "60b069b8b24c54b8be2909595dbf27077a260535eb47435fd0702eae77d24dfa"
MODEL_DOWNLOAD_URL = (
    "https://huggingface.co/CMM7590/Lilith_AI_8B/resolve/"
    f"{MODEL_REVISION}/Lilith_AI_8B_Q4_0.gguf?download=true"
)


def project_path(*parts: str | os.PathLike) -> Path:
    """Resolve a path relative to the project root.

    Absolute inputs are returned untouched, so a user who puts an absolute
    ``model_path`` in config.ini still gets what they asked for.
    """
    if not parts:
        return BASE_DIR
    first = Path(parts[0])
    if first.is_absolute():
        return Path(*parts)
    return BASE_DIR.joinpath(*[str(p) for p in parts])


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Every key the application reads, with a safe default. Missing keys in a
# user's config.ini are filled in from here instead of raising KeyError.
CONFIG_DEFAULTS: dict[str, dict[str, str]] = {
    "server": {
        "server_ai": "ollama",
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "for_local_not_needed",
        "ollama_host": "",
        "request_timeout": "120",
    },
    "ai_config": {
        "persona": "lilith_persona.txt",
        "memory": "memory.json",
        "ai_model": "gemma3",
        "temperature": "0.85",
        "max_tokens": "120",
        "model_path": "models",
        # Preferred GGUF filename. Never downloaded -- the file is placed in
        # model_path by hand, and a lone .gguf wins over this if the names
        # disagree. See modules/_llama_iface.find_gguf.
        "local_model": "Lilith_AI_8B_Q4_0.gguf",
        # server_ai = hf only. The llama backend does not read this.
        "hf_repo_id": "CMM7590/Lilith_AI_8B",
        # Optional immutable Hugging Face snapshot. When set, this must be a
        # full 40-character commit SHA; branches and tags are intentionally
        # rejected because they can move.
        "hf_revision": "",
        "max_history_messages": "40",
        # 0 = keep the whole reply. Brevity is a persona instruction now.
        "max_reply_sentences": "0",
        # Tell Lilith the local time and how long they have been away.
        "time_awareness": "true",
        # Log generic-assistant phrasing without replacing the reply.
        "persona_guard": "true",
        "n_ctx": "8192",
        "n_threads": "0",
        "n_batch": "256",
        "n_gpu_layers": "0",
    },
    "lilith_display": {
        "enable": "true",
        "display_path": "modules/viewer.py",
        "revert_delay": "5",
        "blink_min_interval": "4",
        "blink_max_interval": "8",
        "blink_duration": "0.1",
        "assets_path": "assets",
        "default_state": "idle",
        "place": "room",
        "window_geometry": "400x600",
        "window_offset": "",
        "always_on_top": "true",
        "transparent": "false",
    },
    "viewer_socket": {
        "host": "127.0.0.1",
        "port": "8888",
        "connect_timeout": "10",
    },
    "translator": {
        "enable": "false",
        "source_lang": "en",
        "target_lang": "ru",
        "model_name": "facebook/nllb-200-distilled-600M",
    },
    "setup": {
        # Set by the first-run wizard. False here means a fresh clone gets
        # asked the setup questions after accepting the safety disclosure.
        "complete": "false",
    },
    "safety": {
        # Version of the adult fictional-roleplay disclosure accepted during
        # setup. Zero means no current affirmative consent is recorded.
        "consent_version": "0",
    },
    "logging": {
        "level": "INFO",
        "file": "app.log",
        "max_bytes": "1048576",
        "backup_count": "3",
    },
    "web": {
        "host": "127.0.0.1",
        "port": "5000",
        # Empty = same-origin only. "*" would let any site you visit read this
        # Lilith instance, so cross-origin access is opt-in.
        "cors_origins": "",
        # The debug panel ships the entire persona to the browser. Keep it off
        # unless diagnosing a loopback-only development session.
        "debug_panel": "false",
    },
}


def _apply_defaults(config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Add any section/key the app needs but the file does not have."""
    for section, values in CONFIG_DEFAULTS.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, default in values.items():
            if not config.has_option(section, key):
                config.set(section, key, default)
    return config


def load_config(path: str | os.PathLike | None = None) -> configparser.ConfigParser:
    """Load config.ini from the project root regardless of the cwd.

    If config.ini is absent, config.example.ini is copied into place so a
    fresh clone runs without a manual setup step.
    """
    config_path = Path(path) if path is not None else CONFIG_PATH
    config = configparser.ConfigParser(interpolation=None)

    if not config_path.exists() and CONFIG_EXAMPLE_PATH.exists():
        try:
            config_path.write_text(
                CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except OSError:
            pass

    if config_path.exists():
        # utf-8-sig strips the BOM that Windows Notepad likes to add.
        config.read(config_path, encoding="utf-8-sig")

    return _apply_defaults(config)


def save_config(
    config: configparser.ConfigParser, path: str | os.PathLike | None = None
) -> None:
    """Write config.ini atomically and as UTF-8 without a BOM."""
    config_path = Path(path) if path is not None else CONFIG_PATH
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        config.write(handle)
    replace_atomic(tmp, config_path)  # atomic on both NTFS and ext4


# --------------------------------------------------------------------------
# Console
# --------------------------------------------------------------------------

# Lilith speaks in hearts. cmd.exe on a legacy code page does not.
SYMBOLS = {
    "heart": ("\u2661", "<3"),
    "heart_full": ("\u2665", "<3"),
    "moon": ("\U0001f319", "*"),
    "black_heart": ("\U0001f5a4", "<3"),
    "sleep": ("\U0001f4a4", "zzz"),
    "check": ("\u2713", "OK"),
    "cross": ("\u2717", "X"),
    "up_down": ("\u2191\u2193", "Up/Dn"),
    "select_marker": ("\u203a", ">"),
    "rule": ("\u2500", "-"),
    "sep": ("\u00b7", "-"),
    "scroll_up": ("\u2191", "^"),
    "scroll_down": ("\u2193", "v"),
    "active_room": ("\u2022", "*"),
}


def curses_supports_unicode() -> bool:
    """Whether curses -- not sys.stdout -- can render non-ASCII.

    supports_unicode() probes sys.stdout.encoding, which enable_utf8_console()
    has already forced to UTF-8. Curses does not draw through sys.stdout: it
    uses its own locale-derived encoding, so on a cp1252 locale the stdout
    probe says yes while addstr mangles the glyph into '?'. Ask the locale.
    """
    try:
        import locale

        encoding = (locale.getpreferredencoding(False) or "").lower()
        return encoding.replace("-", "") in ("utf8", "utf_8", "cp65001")
    except Exception:
        return False


def curses_sym(name: str) -> str:
    """Like sym(), but gated on what curses can actually draw."""
    fancy, plain = SYMBOLS.get(name, ("", ""))
    return fancy if curses_supports_unicode() else plain

_unicode_ok: bool | None = None
_original_cp: tuple[int, int] | None = None


def restore_console_cp() -> None:
    """Put the console code page back the way we found it.

    Without this, a UTF-8 code page persists in the window after Lilith exits
    and can garble legacy tools run afterwards in the same terminal.
    """
    global _original_cp
    if not IS_WINDOWS or _original_cp is None:
        return
    try:
        import ctypes

        out_cp, in_cp = _original_cp
        ctypes.windll.kernel32.SetConsoleOutputCP(out_cp)
        ctypes.windll.kernel32.SetConsoleCP(in_cp)
    except Exception:
        pass
    finally:
        _original_cp = None


def enable_utf8_console() -> bool:
    """Make stdout/stderr able to carry Lilith's emoji.

    On Windows this also switches the console code page to UTF-8, which is
    what makes ``chcp 65001`` unnecessary from inside Python.
    """
    global _unicode_ok

    if IS_WINDOWS:
        try:
            import ctypes

            # These change the code page for the whole console window, not
            # just this process, and it is never restored -- so leaving a
            # redirected run to do it would silently reconfigure the user's
            # terminal for every later program. Only touch a real console.
            if sys.stdout.isatty():
                kernel32 = ctypes.windll.kernel32
                global _original_cp
                if _original_cp is None:
                    _original_cp = (kernel32.GetConsoleOutputCP(),
                                    kernel32.GetConsoleCP())
                kernel32.SetConsoleOutputCP(65001)
                kernel32.SetConsoleCP(65001)
        except Exception:
            pass

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    _unicode_ok = _probe_unicode()
    return _unicode_ok


def _probe_unicode() -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or ""
    try:
        "\u2661\U0001f319".encode(encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def supports_unicode() -> bool:
    """True when the current console can render the fancy glyphs."""
    global _unicode_ok
    if _unicode_ok is None:
        _unicode_ok = _probe_unicode()
    return _unicode_ok


def sym(name: str) -> str:
    """Return a symbol, downgraded to ASCII on consoles that cannot show it."""
    fancy, plain = SYMBOLS.get(name, ("", ""))
    return fancy if supports_unicode() else plain


# Typographic characters a model reaches for constantly, and their ASCII
# equivalents. Without this they become "?" on a legacy console -- which also
# silently killed Lilith's trailing-off pause, because lilith.py keys its
# per-character delay on U+2026 and never saw one.
_ASCII_EQUIVALENTS = str.maketrans({
    "…": "...",   # horizontal ellipsis
    "—": "--",    # em dash
    "–": "-",     # en dash
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    " ": " ",     # non-breaking space
})


def safe_text(text: str) -> str:
    """Strip characters the console cannot encode, rather than crashing."""
    if supports_unicode():
        return text
    text = text.translate(_ASCII_EQUIVALENTS)
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


# --------------------------------------------------------------------------
# HiDPI (Windows 11 scales displays by default; Tk needs to be told)
# --------------------------------------------------------------------------


def enable_dpi_awareness() -> float:
    """Opt into per-monitor DPI awareness and return the scale factor.

    Without this a 400x600 Tk window on a 150%-scaled Windows 11 display is
    both blurry and the wrong physical size.

    Three APIs are tried oldest-last, because each needs a newer Windows than
    the one before it. Crucially, none of them raise on failure -- they return
    a status code -- so every call is checked. An earlier version of this
    function passed the raw int -4 to SetProcessDpiAwarenessContext, which
    expects a pointer-sized handle: on 64-bit it silently returned FALSE
    without raising, so the fallbacks never ran and DPI awareness was never
    actually enabled.
    """
    if not IS_WINDOWS:
        return 1.0

    try:
        import ctypes

        user32 = ctypes.windll.user32
        aware = False

        # 1. Per-monitor v2 (Windows 10 1703+). Correct when the window is
        #    dragged between monitors with different scaling.
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        try:
            user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
            user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            aware = bool(user32.SetProcessDpiAwarenessContext(
                ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            ))
        except (AttributeError, OSError):
            aware = False

        # 2. Windows 8.1+. Returns an HRESULT; E_ACCESSDENIED means awareness
        #    was already set, which is success for our purposes.
        if not aware:
            S_OK, E_ACCESSDENIED = 0, -2147024891
            try:
                result = ctypes.windll.shcore.SetProcessDpiAwareness(1)
                aware = result in (S_OK, E_ACCESSDENIED)
            except (AttributeError, OSError):
                pass

        # 3. Vista+. System-DPI aware only, but better than nothing.
        if not aware:
            try:
                aware = bool(user32.SetProcessDPIAware())
            except (AttributeError, OSError):
                pass

        if not aware:
            logging.getLogger(__name__).debug("Could not enable DPI awareness")

        # GetDpiForSystem needs Windows 10 1607; fall back to device caps.
        try:
            user32.GetDpiForSystem.restype = ctypes.c_uint
            dpi = int(user32.GetDpiForSystem())
        except (AttributeError, OSError):
            LOGPIXELSX = 88
            hdc = user32.GetDC(0)
            try:
                dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX))
            finally:
                user32.ReleaseDC(0, hdc)

        if not 48 <= dpi <= 960:  # 50% .. 1000%; anything else is nonsense
            return 1.0
        return dpi / 96.0
    except Exception:
        return 1.0


def gui_python() -> str:
    """Interpreter to launch a GUI child process with.

    On Windows, ``python.exe`` is a console application, so spawning the
    viewer with it flashes a console window even with CREATE_NO_WINDOW in
    some terminals. ``pythonw.exe`` sits beside it and has no console at all,
    which is the idiomatic way to launch a Tk child.
    """
    if not IS_WINDOWS:
        return sys.executable
    exe = Path(sys.executable)
    if exe.stem.lower().startswith("pythonw"):
        return sys.executable
    candidate = exe.with_name(exe.name.replace("python", "pythonw", 1))
    return str(candidate) if candidate.exists() else sys.executable


def replace_atomic(source: Path, destination: Path, attempts: int = 5) -> None:
    """os.replace, retried briefly.

    On Windows an antivirus scanner or the search indexer can hold a
    transient lock on a file it has just seen written, which makes os.replace
    fail with PermissionError. On Linux this loop never runs a second time.
    """
    import time as _time

    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            _time.sleep(0.05 * (attempt + 1))


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------


def setup_logging(config: configparser.ConfigParser | None = None) -> Path:
    """Configure rotating UTF-8 logging into the project root.

    UTF-8 matters here: the persona, the Russian TUI strings and the emoji
    all end up in log records, and the Windows default (cp1251/cp1252)
    cannot encode them.
    """
    config = config if config is not None else load_config()
    section = config["logging"]

    log_path = project_path(section.get("file", "app.log"))
    level = getattr(logging, section.get("level", "INFO").upper(), logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=section.getint("max_bytes", fallback=1_048_576),
        backupCount=section.getint("backup_count", fallback=3),
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(level)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)

    return log_path


# --------------------------------------------------------------------------
# Networking helpers
# --------------------------------------------------------------------------


def port_in_use(host: str, port: int, timeout: float = 0.35) -> bool:
    """True when something already accepts connections on host:port.

    Needed because SO_REUSEADDR means the opposite thing on Windows: two
    processes really can bind the same port, so the viewer must check first
    instead of relying on bind() to fail.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------


def check_python_version() -> tuple[bool, str]:
    ok = sys.version_info >= MIN_PYTHON
    want = ".".join(str(part) for part in MIN_PYTHON)
    have = platform.python_version()
    return ok, f"Python {have} (need {want}+)"


def describe_platform() -> str:
    return (
        f"{platform.system()} {platform.release()} "
        f"({platform.machine()}), Python {platform.python_version()}"
    )
