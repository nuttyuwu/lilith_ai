"""
Muted colour for the chat REPL (ANSI) and the curses screens (colour pairs).

Nothing in here may raise -- a terminal that cannot colour text just gets
plain text back, never a crash. Colour is only ever emitted when all of
these hold:

  * NO_COLOR is unset (or FORCE_COLOR is set, which wins outright).
  * TERM is not "dumb".
  * The stream being written to is a real terminal, not a pipe or redirect.
  * On Windows, ENABLE_VIRTUAL_TERMINAL_PROCESSING is actually on -- without
    it, conhost prints escape codes as literal text instead of colouring
    anything. Windows Terminal has it on by default; conhost does not.

256-colour codes are only sent when the terminal says it understands them;
otherwise every colour degrades to its basic-8 equivalent.

``curses.wrapper`` restores the console mode it captured at ``initscr()``,
which on Windows clears the VT flag we set. Call ``reset()`` after any curses
screen exits so the next ``code()`` re-probes instead of trusting a stale
cache and emitting escape codes into a console that no longer honours them.
"""

from __future__ import annotations

import os
import sys

from modules import compat

RESET = "\x1b[0m"

# name -> (256-colour index, basic-8 SGR code). Muted and low-saturation on
# purpose -- this is a quiet companion, not a dashboard. The fallbacks stay
# inside 30-37: the bright range (90-97) is an aixterm extension that the
# 8-colour terminals this column exists for do not understand.
PALETTE: dict[str, tuple[int, int]] = {
    "lilith": (218, 35),   # soft pink / magenta -- her dialogue
    "narration": (176, 35),  # dimmer orchid -- her stage directions
    "you": (109, 36),      # slate blue / cyan
    "muted": (244, 37),    # grey / white
    "problem": (167, 31),  # muted red / red
}

# SGR 2. Where colour says who is speaking, faint says how loudly -- it is
# what actually reads as "soft", and nothing was using it.
FAINT = "\x1b[2m"

# Curses roles, kept separate from the ANSI palette because a role needs to
# say what it does on a monochrome terminal too (constraint: never call
# color_pair() directly -- fall back to A_REVERSE/A_BOLD/A_DIM).
#
#   role -> (palette colour, monochrome-only attribute, always-on attribute)
#
# The third column is what keeps the aesthetic quiet: "resting" rows stay dim
# even in colour, while "active" gets the colour *instead of* bold rather than
# on top of it, so the selected row reads as warmer, not louder.
CURSES_ROLES: dict[str, tuple[str, str, str]] = {
    "title": ("lilith", "A_BOLD", "A_BOLD"),
    "subtitle": ("muted", "A_DIM", "A_DIM"),
    "resting": ("muted", "A_DIM", "A_DIM"),
    "active": ("lilith", "A_BOLD", ""),
    "hint": ("muted", "A_DIM", "A_DIM"),
    "problem": ("problem", "A_REVERSE", ""),
}

_has_256: bool | None = None
_vt_ok: bool | None = None

_curses_ready = False
_curses_colour = False
_pairs: dict[str, int] = {}


def reset() -> None:
    """Forget every cached capability probe.

    Call this after a curses screen exits: endwin() restores the console mode
    from before initscr(), which on Windows drops the VT flag, and it also
    invalidates any colour pairs we allocated.
    """
    global _has_256, _vt_ok, _curses_ready, _curses_colour
    _has_256 = None
    _vt_ok = None
    _curses_ready = False
    _curses_colour = False
    _pairs.clear()


# --------------------------------------------------------------------------
# Capability probes
# --------------------------------------------------------------------------

def _colour_allowed() -> bool:
    """Environment-level yes/no, before any per-stream check."""
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return os.environ.get("TERM", "").lower() != "dumb"


def _stream_ok(stream) -> bool:
    if os.environ.get("FORCE_COLOR"):
        return True
    if not _colour_allowed():
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _supports_256() -> bool:
    global _has_256
    if _has_256 is not None:
        return _has_256
    if os.environ.get("COLORTERM") in ("truecolor", "24bit"):
        _has_256 = True
    elif "256color" in os.environ.get("TERM", ""):
        _has_256 = True
    elif compat.IS_WINDOWS:
        # A console that ACCEPTED ENABLE_VIRTUAL_TERMINAL_PROCESSING is a
        # Windows 10+ VT console, and VT support there has always included
        # 256-colour SGR -- so the flag we already set is the real signal.
        # WT_SESSION/TERM_PROGRAM are kept only for terminals that render
        # ANSI without a Win32 console to configure (mintty, VS Code).
        # Testing those two alone was wrong: a plain PowerShell window in
        # conhost sets neither, yet renders 256 colours perfectly.
        _has_256 = bool(
            enable_windows_vt()
            or os.environ.get("WT_SESSION")
            or os.environ.get("TERM_PROGRAM")
        )
    else:
        # A bare TERM=xterm or TERM=vt100 is 8/16 colour. Only claim 256 when
        # the terminal actually said so above.
        _has_256 = os.environ.get("TERM", "").endswith(("-256color", "256color"))
    return _has_256


def enable_windows_vt() -> bool:
    """Turn on ENABLE_VIRTUAL_TERMINAL_PROCESSING so ANSI codes render.

    Safe to call repeatedly, off Windows, or when stdout is redirected -- it
    just reports False. The result is cached until reset().
    """
    global _vt_ok
    if _vt_ok is not None:
        return _vt_ok
    if not compat.IS_WINDOWS:
        _vt_ok = True
        return _vt_ok

    _vt_ok = False
    try:
        import ctypes

        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32 = ctypes.windll.kernel32
        # stdout (-11) and stderr (-12): problem() writes to stderr.
        for std_handle in (-11, -12):
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue  # redirected to a file/pipe; not a console handle
            if kernel32.SetConsoleMode(
                handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            ):
                _vt_ok = True
    except Exception:
        _vt_ok = False
    return _vt_ok


# --------------------------------------------------------------------------
# ANSI
# --------------------------------------------------------------------------

def code(name: str, stream=None) -> str:
    """The ANSI SGR prefix for a palette colour, or "" when colour is off."""
    try:
        target = stream if stream is not None else sys.stdout
        if name not in PALETTE or not _stream_ok(target):
            return ""
        # On Windows an escape code is worse than no colour: without VT it
        # prints as a literal "<-[38;5;181m". FORCE_COLOR still wins -- under
        # mintty/Git Bash there is no Win32 console to set the flag on, yet
        # ANSI renders perfectly, so an explicit request must not be refused.
        if (compat.IS_WINDOWS and not enable_windows_vt()
                and not os.environ.get("FORCE_COLOR")):
            return ""
        rich, basic = PALETTE[name]
        return f"\x1b[38;5;{rich}m" if _supports_256() else f"\x1b[{basic}m"
    except Exception:
        return ""


def paint(text: str, name: str, stream=None, faint: bool = False) -> str:
    """Wrap text in a palette colour, or return it unchanged when colour is off."""
    prefix = code(name, stream)
    if not prefix:
        return text
    if faint:
        prefix += FAINT
    return f"{prefix}{text}{RESET}"


def prompt_code(name: str, stream=None) -> tuple[str, str]:
    """Colour codes for an input() prompt, bracketed for readline.

    GNU readline counts every byte of the prompt as an occupied column unless
    non-printing runs sit between \\x01 and \\x02. Without them it thinks a
    5-column "You: " is 15 wide, and long lines, backspace past column 0 and
    history recall all leave the cursor in the wrong place.
    """
    prefix = code(name, stream)
    if not prefix:
        return "", ""
    return f"\x01{prefix}\x02", f"\x01{RESET}\x02"


# --------------------------------------------------------------------------
# curses
# --------------------------------------------------------------------------

def init_curses(curses) -> bool:
    """Allocate one colour pair per palette entry. Never raises.

    Returns True when colour is usable. Called lazily by attr(), so callers
    only ever need attr(); it must run after initscr(), which is guaranteed
    because drawing only happens inside curses.wrapper.
    """
    global _curses_ready, _curses_colour
    if _curses_ready:
        return _curses_colour

    _curses_ready = True
    _curses_colour = False
    if not _colour_allowed():
        return False

    try:
        curses.start_color()
        if not curses.has_colors():
            return False

        # Let the terminal's own background show through instead of painting
        # a black block behind every cell -- this is most of the "soft" look.
        # curses.wrapper calls start_color() but never this.
        background = -1
        try:
            curses.use_default_colors()
        except Exception:
            background = curses.COLOR_BLACK

        rich_ok = getattr(curses, "COLORS", 8) >= 256
        for index, (name, (rich, basic)) in enumerate(PALETTE.items(), start=1):
            # Basic-8 SGR codes are 30..37; curses colour constants are 0..7.
            colour = rich if rich_ok else max(0, min(7, basic - 30))
            curses.init_pair(index, colour, background)
            _pairs[name] = index
        _curses_colour = True
    except Exception:
        _curses_colour = False
    return _curses_colour


def attr(curses, role: str) -> int:
    """Curses attributes for a named role. Never raises, never returns colour
    on a monochrome terminal -- callers must never touch color_pair directly."""
    try:
        colour_name, mono_attr, always_attr = CURSES_ROLES.get(
            role, ("muted", "A_DIM", "A_DIM")
        )
        if init_curses(curses) and colour_name in _pairs:
            result = curses.color_pair(_pairs[colour_name])
            if always_attr:
                result |= getattr(curses, always_attr, 0)
            return result
        return getattr(curses, mono_attr, 0)
    except Exception:
        return 0
