"""
Shared terminal-UI helpers.

``curses`` is not part of the Python standard library on Windows. The two TUI
screens (config editor, conversation manager) therefore need three things that
did not exist before:

  1. A clear message pointing at ``pip install windows-curses`` instead of a
     bare ``ModuleNotFoundError: No module named '_curses'``.
  2. A plain-text fallback so both screens still work when curses is genuinely
     unavailable (Windows without the shim, a dumb terminal, a CI job).
  3. Bounds-checked drawing. ``stdscr.addstr`` raises ``curses.error`` when
     asked to write past the last row or column, so the old code crashed on a
     short terminal or when a conversation list grew past the window height.
"""

from __future__ import annotations

import sys

from modules import compat, theme


def load_curses():
    """Import curses, or return None with an explanation printed once."""
    try:
        import curses

        return curses
    except ImportError:
        return None


def curses_install_hint() -> str:
    if sys.platform == "nt" or sys.platform.startswith("win"):
        return (
            "The terminal UI needs the 'windows-curses' package on Windows:\n"
            "    python -m pip install windows-curses"
        )
    return (
        "The terminal UI needs Python's curses module.\n"
        "On Debian/Ubuntu it lives in the base python3 package; if it is "
        "missing, install python3-full."
    )


def safe_addstr(stdscr, y: int, x: int, text: str, attr: int = 0, margin: int = 0) -> None:
    """Write text, clipped to the window, never raising.

    Also degrades non-ASCII characters when the terminal encoding cannot
    represent them, which is the normal case in a legacy Windows console.

    ``margin`` reserves extra columns on the right beyond the usual one-cell
    safety buffer, so a caller drawing something else in that space (e.g. a
    scroll indicator) never collides with clipped text.
    """
    try:
        height, width = stdscr.getmaxyx()
    except Exception:
        return
    if y < 0 or y >= height or x < 0 or x >= width:
        return

    text = str(text).replace("\n", " ").replace("\t", "    ")
    # Leave the last cell alone: writing to it scrolls the window on some terminals.
    available = width - x - 1 - margin
    if available <= 0:
        return
    text = text[:available]

    try:
        stdscr.addstr(y, x, text, attr)
    except Exception:
        try:
            fallback = text.encode("ascii", "replace").decode("ascii")
            stdscr.addstr(y, x, fallback, attr)
        except Exception:
            pass


def hint_line(*hints: str) -> str:
    """Join key hints with a soft separator.

    Deliberately short. The old footers ran to 63 characters of pipe-delimited
    chrome pinned to the bottom of every frame, which reads as a dashboard;
    the arrow keys need no explaining, so only the non-obvious keys are shown.
    """
    return f"  {compat.curses_sym('sep')}  ".join(h for h in hints if h)


def shorten_path(path: str, limit: int = 44) -> str:
    """Middle-elide a long path: C:\\Users\\...\\config.ini."""
    text = str(path)
    if len(text) <= limit:
        return text
    tail = text[-(limit - 4):]
    return f"...{tail}" if not tail.startswith(("\\", "/")) else f"..{tail}"


def draw_list(stdscr, curses, title: str, items: list[str], selected: int,
              footer: str = "", subtitle: str = "") -> None:
    """Render a scrolling selection list that fits any window size."""
    stdscr.erase()
    height, width = stdscr.getmaxyx()

    # Negative space. On a roomy terminal the content is inset from the top
    # and left so the screen breathes; on a short one the padding is the first
    # thing surrendered, because fitting the list matters more than the mood.
    pad_top = 1 if height >= 14 else 0
    left = 4 if width >= 48 else 2
    text_left = left + 2

    safe_addstr(stdscr, pad_top, left, title, theme.attr(curses, "title"))
    top = pad_top + 2
    if subtitle:
        safe_addstr(stdscr, pad_top + 1, left, subtitle,
                    theme.attr(curses, "subtitle"))
        top = pad_top + 3

    # Reserve the footer row, plus a blank line above it when there is room.
    footer_gap = 1 if height >= 14 else 0
    visible = max(1, height - top - 1 - footer_gap)
    # Scroll so the selected row is always on screen.
    first = 0
    if len(items) > visible:
        first = min(max(0, selected - visible // 2), len(items) - visible)

    # A full-row inverted bar reads as a dashboard, not a quiet interface.
    # The selection is shown by a marker and a warmer colour; the rows around
    # it recede instead. Drawing the unselected rows at rest and the selected
    # one at normal weight keeps the screen quiet -- the older version had it
    # backwards, with every row at full intensity and the selection brighter
    # still, so the whole list shouted.
    scrollable = len(items) > visible
    gutter = 2 if scrollable else 0  # keeps long item text off the scroll hint
    # curses_sym, not sym: sym() asks sys.stdout, which enable_utf8_console has
    # already forced to UTF-8, while curses draws through the locale encoding.
    marker = compat.curses_sym("select_marker")
    resting = theme.attr(curses, "resting")
    active = theme.attr(curses, "active")

    for offset, item in enumerate(items[first:first + visible]):
        index = first + offset
        row = top + offset
        if index == selected:
            safe_addstr(stdscr, row, left, marker, active)
            safe_addstr(stdscr, row, text_left, item, active, margin=gutter)
        else:
            safe_addstr(stdscr, row, text_left, item, resting, margin=gutter)

    if scrollable:
        hint = theme.attr(curses, "hint")
        up = compat.curses_sym("scroll_up")
        down = compat.curses_sym("scroll_down")
        safe_addstr(stdscr, top, width - 3, up if first else " ", hint)
        safe_addstr(stdscr, top + visible - 1, width - 3,
                    down if first + visible < len(items) else " ", hint)

    if footer:
        safe_addstr(stdscr, height - 1, left, footer, theme.attr(curses, "hint"))
    stdscr.noutrefresh()
    curses.doupdate()


def prompt(stdscr, curses, title: str, current: str = "") -> str:
    """Read a line of text inside a curses screen."""
    stdscr.erase()
    safe_addstr(stdscr, 1, 2, title, theme.attr(curses, "title"))
    if current:
        safe_addstr(stdscr, 3, 2, f"Current: {current}",
                    theme.attr(curses, "subtitle"))
    safe_addstr(stdscr, 5, 2, "New value (blank = keep): ",
                theme.attr(curses, "hint"))
    stdscr.refresh()

    curses.echo()
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    try:
        height, width = stdscr.getmaxyx()
        raw = stdscr.getstr(6, 2, max(8, width - 6))
        value = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        value = ""
    finally:
        curses.noecho()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
    return value


def notice(stdscr, curses, text: str) -> None:
    """Show a message and wait for any key.

    Separate from confirm() because confirm() always draws "y = yes  n = no",
    which is nonsense under a message that says "Press any key" -- and that is
    how it was being used for every acknowledgement in both screens.
    """
    stdscr.erase()
    safe_addstr(stdscr, 2, 2, text, theme.attr(curses, "title"))
    safe_addstr(stdscr, 4, 2, "press any key", theme.attr(curses, "hint"))
    stdscr.refresh()
    try:
        stdscr.getch()
    except Exception:
        pass


def confirm(stdscr, curses, text: str) -> bool:
    stdscr.erase()
    safe_addstr(stdscr, 2, 2, text, theme.attr(curses, "title"))
    safe_addstr(stdscr, 4, 2, "y = yes    n = no", theme.attr(curses, "hint"))
    stdscr.refresh()
    try:
        return stdscr.getch() in (ord("y"), ord("Y"))
    except Exception:
        return False


# -- plain-text fallback ---------------------------------------------------

def ask_choice(title: str, options: list[str], allow_blank: bool = True) -> int | None:
    """Numbered menu for terminals with no curses at all."""
    print(f"\n{title}")
    for index, option in enumerate(options, start=1):
        print(f"  {index:>2}. {option}")
    suffix = " (blank to go back)" if allow_blank else ""
    while True:
        try:
            raw = input(f"Choose 1-{len(options)}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw and allow_blank:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print("  ...that is not one of the options.")
