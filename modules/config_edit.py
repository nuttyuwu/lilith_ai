"""
config.ini editor.

Fixes over the previous version:
  * Works on Windows. ``import curses`` at module scope made the whole
    ``edit`` subcommand unusable there; it is now imported through
    ``_tui.load_curses()`` with a plain-text fallback.
  * The config path is resolved from the project root instead of the current
    directory, so ``python lilith.py edit`` works from anywhere.
  * Only writes on an explicit save, and never leaves a half-written file.
    The old version saved on quit from the top menu but silently discarded
    everything if you pressed Ctrl+C.
  * Drawing is bounds-checked, so a short terminal no longer crashes it.
  * Boolean and numeric fields are validated before being stored.
"""

from __future__ import annotations

import math

from modules import _tui, compat, theme

# Fields with a fixed set of valid values, offered as a picker.
SELECT_OPTIONS: dict[tuple[str, str], list[str]] = {
    ("server", "server_ai"): ["ollama", "LM studio", "openai", "hf", "llama"],
    ("ai_config", "ai_model"): ["gemma3", "deepseek-r1", "llama3", "mistral", "qwen3"],
    ("translator", "enable"): ["false", "true"],
    ("translator", "source_lang"): ["en", "ru", "de", "fr", "es", "uk", "zh"],
    ("translator", "target_lang"): ["ru", "en", "de", "fr", "es", "uk", "zh"],
    ("lilith_display", "place"): ["room", "glass"],
    ("lilith_display", "enable"): ["true", "false"],
    ("lilith_display", "always_on_top"): ["true", "false"],
    ("lilith_display", "transparent"): ["false", "true"],
    ("logging", "level"): ["INFO", "DEBUG", "WARNING", "ERROR"],
}

INT_FIELDS = {
    "max_tokens", "max_history_messages", "max_reply_sentences", "revert_delay",
    "port", "n_ctx", "n_threads", "n_batch", "n_gpu_layers", "request_timeout",
    "max_bytes", "backup_count",
}
FLOAT_FIELDS = {
    "temperature", "blink_min_interval", "blink_max_interval", "blink_duration",
    "connect_timeout",
}

# Bounds are intentionally broad: the editor should reject values that are
# structurally unsafe (negative delays, impossible ports, NaN), without
# second-guessing legitimate high-end model configurations.
INT_RANGES: dict[str, tuple[int | None, int | None]] = {
    "max_tokens": (1, None),
    "max_history_messages": (0, None),
    "max_reply_sentences": (0, None),
    "revert_delay": (0, None),
    "port": (1, 65_535),
    "n_ctx": (1, None),
    "n_threads": (0, None),
    "n_batch": (1, None),
    "n_gpu_layers": (0, None),
    "request_timeout": (1, None),
    "max_bytes": (1, None),
    "backup_count": (0, None),
}
FLOAT_RANGES: dict[str, tuple[float | None, float | None]] = {
    "temperature": (0.0, 2.0),
    "blink_min_interval": (0.0, None),
    "blink_max_interval": (0.0, None),
    "blink_duration": (0.0, None),
    "connect_timeout": (0.001, None),
}


def _range_error(
    key: str, value: int | float,
    bounds: tuple[int | float | None, int | float | None],
) -> str:
    minimum, maximum = bounds
    if minimum is not None and value < minimum:
        return f"{key} must be at least {minimum:g}"
    if maximum is not None and value > maximum:
        return f"{key} must be at most {maximum:g}"
    return ""


def validate(key: str, value: str) -> tuple[bool, str]:
    """Return (ok, message) so a typo cannot make config.ini unloadable."""
    if key in INT_FIELDS:
        try:
            number = int(value)
        except ValueError:
            return False, f"{key} must be a whole number"
        message = _range_error(key, number, INT_RANGES[key])
        if message:
            return False, message
    elif key in FLOAT_FIELDS:
        try:
            number = float(value)
        except ValueError:
            return False, f"{key} must be a number"
        if not math.isfinite(number):
            return False, f"{key} must be a finite number"
        message = _range_error(key, number, FLOAT_RANGES[key])
        if message:
            return False, message
    return True, ""


# --------------------------------------------------------------------------
# curses interface
# --------------------------------------------------------------------------

def _section_screen(stdscr, curses, config, section: str) -> bool:
    """Edit one section. Returns True only if a value actually changed."""
    keys = list(config[section].keys())
    selected = 0
    changed = False

    while True:
        rows = [f"{key} = {config[section][key]}" for key in keys]
        _tui.draw_list(
            stdscr, curses, section, rows, selected,
            footer=_tui.hint_line("enter edit", "q back"),
        )
        try:
            key_press = stdscr.getch()
        except KeyboardInterrupt:
            return changed

        if key_press in (curses.KEY_UP, ord("k")) and selected > 0:
            selected -= 1
        elif key_press in (curses.KEY_DOWN, ord("j")) and selected < len(keys) - 1:
            selected += 1
        elif key_press in (curses.KEY_ENTER, 10, 13):
            name = keys[selected]
            current = config[section][name]

            if (section, name) in SELECT_OPTIONS:
                options = SELECT_OPTIONS[(section, name)]
                choice = options.index(current) if current in options else 0
                while True:
                    _tui.draw_list(
                        stdscr, curses, name, options, choice,
                        subtitle=section,
                        footer=_tui.hint_line("enter choose", "q cancel"),
                    )
                    try:
                        press = stdscr.getch()
                    except KeyboardInterrupt:
                        # The other two getch() sites guard this; without it
                        # here, Ctrl+C in a dropdown escapes even the
                        # except Exception in run_config_editor, because
                        # KeyboardInterrupt is a BaseException.
                        break
                    if press in (curses.KEY_UP, ord("k")) and choice > 0:
                        choice -= 1
                    elif press in (curses.KEY_DOWN, ord("j")) and choice < len(options) - 1:
                        choice += 1
                    elif press in (curses.KEY_ENTER, 10, 13):
                        if options[choice] != current:
                            config.set(section, name, options[choice])
                            changed = True
                        break
                    elif press in (27, ord("q")):
                        break
            else:
                value = _tui.prompt(stdscr, curses, f"[{section}] {name}", current)
                if value:
                    ok, message = validate(name, value)
                    if ok:
                        if value != current:
                            config.set(section, name, value)
                            changed = True
                    else:
                        _tui.notice(stdscr, curses, message)
        elif key_press in (27, ord("q")):
            return changed


def _main_screen(stdscr, curses, config) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    sections = config.sections()
    selected = 0
    dirty = False

    while True:
        _tui.draw_list(
            stdscr, curses, "Lilith configuration", sections, selected,
            subtitle=_tui.shorten_path(compat.CONFIG_PATH)
            + ("   unsaved" if dirty else ""),
            footer=_tui.hint_line("enter open", "s save", "q quit"),
        )
        try:
            press = stdscr.getch()
        except KeyboardInterrupt:
            return

        if press in (curses.KEY_UP, ord("k")) and selected > 0:
            selected -= 1
        elif press in (curses.KEY_DOWN, ord("j")) and selected < len(sections) - 1:
            selected += 1
        elif press in (curses.KEY_ENTER, 10, 13):
            # Only mark dirty if something actually changed -- merely looking
            # at a section used to trigger "Save changes before quitting?".
            if _section_screen(stdscr, curses, config, sections[selected]):
                dirty = True
        elif press in (ord("s"), ord("S")):
            compat.save_config(config)
            _tui.notice(stdscr, curses, "Saved.")
            dirty = False
        elif press in (27, ord("q")):
            if dirty and _tui.confirm(stdscr, curses, "Save changes before quitting?"):
                compat.save_config(config)
            return


# --------------------------------------------------------------------------
# plain-text fallback
# --------------------------------------------------------------------------

def _plain_editor(config=None) -> None:
    # Accepts the in-progress config so a mid-session curses failure hands the
    # user's unsaved edits to the fallback editor instead of silently
    # reloading from disk and discarding them.
    config = config if config is not None else compat.load_config()
    print(f"\nLilith configuration -- {compat.CONFIG_PATH}")
    print("(no curses available, using the simple editor)")

    while True:
        sections = config.sections()
        choice = _tui.ask_choice("Sections:", sections + ["** save and exit **"])
        if choice is None:
            print("Nothing saved.")
            return
        if choice == len(sections):
            compat.save_config(config)
            print("Saved.")
            return

        section = sections[choice]
        while True:
            keys = list(config[section].keys())
            labels = [f"{key} = {config[section][key]}" for key in keys]
            index = _tui.ask_choice(f"[{section}]", labels)
            if index is None:
                break
            name = keys[index]
            options = SELECT_OPTIONS.get((section, name))
            if options:
                picked = _tui.ask_choice(f"{name}:", options)
                if picked is not None:
                    config.set(section, name, options[picked])
            else:
                try:
                    value = input(
                        f"{name} [{config[section][name]}] = "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if value:
                    ok, message = validate(name, value)
                    print(f"  {message}" if not ok else "")
                    if ok:
                        config.set(section, name, value)


def run_config_editor() -> None:
    curses = _tui.load_curses()
    if curses is None:
        print(_tui.curses_install_hint())
        print()
        _plain_editor()
        return
    # Owned out here so unsaved edits survive a curses failure mid-session.
    config = compat.load_config()
    try:
        curses.wrapper(lambda stdscr: _main_screen(stdscr, curses, config))
    except Exception as exc:
        print(f"Terminal UI failed ({exc}); falling back to the simple editor.")
        print("Your unsaved changes have been carried over.")
        _plain_editor(config)
    finally:
        # endwin() restores the console mode from before initscr(), which on
        # Windows drops the VT flag, and invalidates our colour pairs.
        theme.reset()
