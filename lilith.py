#!/usr/bin/env python3
"""
Lilith -- terminal entry point.

Fixes over the previous version:
  * Nothing happens at import time any more. The old module ran
    ``parser.parse_args()``, built the display and spawned the viewer process
    as soon as it was imported -- which is why ``web_lilith.py`` (which does
    ``from lilith import ...``) opened a portrait window and then died on
    gunicorn's command-line flags.
  * The console is switched to UTF-8 first, so the hearts and the moon render
    in Windows Terminal and cmd.exe instead of raising UnicodeEncodeError.
  * Ctrl+C is handled, and the viewer process is always shut down in a
    ``finally`` block rather than being orphaned.
  * ``EXISTENCE_KEYWORDS`` is re-exported for the web app, which imported it
    from here and crashed because it never existed.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import shutil
import sys
import threading
import time

from modules import compat, conv_mgmt, theme
from modules.lilith_ai import EXISTENCE_KEYWORDS  # re-exported for web_lilith

logger = logging.getLogger(__name__)

BASE_DIR = str(compat.BASE_DIR)

# Slow enough to feel like she is speaking, fast enough not to be annoying.
CHAR_DELAY = 0.03
PAUSE_DELAY = {".": 0.4, "\u2026": 0.4, ",": 0.25, "~": 0.25}

_spinning = False


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------

def spinner() -> None:
    # The carriage returns are not colour, so theme.paint() cannot suppress
    # them -- piping to a file would collect ~50 "\rLilith is thinking" frames
    # before every single reply. Nothing to animate when nobody is watching.
    if not sys.stdout.isatty():
        return
    frames = itertools.cycle(
        [compat.sym("heart"), compat.sym("heart_full")] if compat.supports_unicode()
        else [".", "..", "...", "...."]
    )
    for frame in frames:
        if not _spinning:
            break
        sys.stdout.write("\r" + theme.paint(f"Lilith is thinking {frame}   ", "lilith"))
        sys.stdout.flush()
        time.sleep(0.12)
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


def type_out(text: str, animate: bool = True) -> None:
    """Type text out slowly, or print it at once when piped to a file."""
    text = compat.safe_text(text)
    if not animate or not sys.stdout.isatty():
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(PAUSE_DELAY.get(char, CHAR_DELAY))
    time.sleep(0.6)


def _stop_spinner() -> None:
    global _spinning
    _spinning = False


def _speak(text: str, animate: bool, colour: str = "lilith",
           faint: bool = False) -> None:
    """Type text out in one of Lilith's colours.

    Colour codes sit outside the typed span so the animation delay never lands
    on an invisible escape byte. The reset is in a finally: type_out spends
    seconds inside time.sleep(), which is exactly where Ctrl+C lands, and
    skipping the reset would leave the user's shell prompt pink.
    """
    prefix = theme.code(colour)
    if prefix and faint:
        prefix += theme.FAINT
    if prefix:
        sys.stdout.write(prefix)
        sys.stdout.flush()
    try:
        type_out(text, animate)
    finally:
        if prefix:
            sys.stdout.write(theme.RESET)
            sys.stdout.flush()


def speak(text: str, animate: bool = True) -> None:
    """Narration -- 'Lilith tilts her head'. Dimmer than her actual words, so
    her stage directions sit behind her voice instead of level with it."""
    _speak(text, animate, colour="narration", faint=True)


def say(text: str, animate: bool = True) -> None:
    """A reply, labelled and typed out in Lilith's colour."""
    _speak(f"Lilith: {text}\n", animate)


def note(text: str) -> None:
    """A quiet, out-of-character status line (room switched, renamed, ...)."""
    print(theme.paint(compat.safe_text(f"  {text}"), "muted", faint=True))


def problem(text: str) -> None:
    """An error, on stderr so a piped transcript stays a clean conversation.

    safe_text matters here specifically: exception text carries model paths
    and localised Windows error strings, and a UnicodeEncodeError raised
    inside the error handler would kill the chat loop over a recoverable
    backend failure.
    """
    body = compat.safe_text(f"\n[{text}]\n")
    print(theme.paint(body, "problem", stream=sys.stderr), file=sys.stderr)


def banner(room: str) -> None:
    """A thin rule naming the active room, reprinted whenever it changes."""
    width = shutil.get_terminal_size(fallback=(70, 20)).columns
    rule = compat.sym("rule")
    title = " Lilith "
    tag = f" room: {room} "
    middle = max(width - len(title) - len(tag) - 4, 1)
    line = f"{rule * 2}{title}{rule * middle}{tag}{rule * 2}"
    # Stop one short of the last column: writing it and then a newline emits a
    # spurious blank line on terminals without deferred wrap.
    print(theme.paint(compat.safe_text(line[:width - 1]), "muted"))


def handle_command(raw: str, lilith) -> None:
    """Slash-commands inside the chat loop.

    These must stay '/'-prefixed: anything typed without a slash is a real
    message to Lilith, so a bare word like 'rooms' has to stay sayable.
    """
    name, _, arg = raw[1:].partition(" ")
    name = name.strip().lower()
    arg = arg.strip()

    if name in ("rooms", "conversations", "conv"):
        conv_mgmt.run_conversation_manager(lilith)
        banner(lilith.get_current_conversation_name())
    elif name == "rename":
        if not arg:
            note("usage: /rename <new name>")
            return
        old = lilith.get_current_conversation_name()
        if arg == old:
            return
        if conv_mgmt.rename_conversation(lilith, old, arg):
            note(f"renamed room '{old}' -> '{arg}'")
            banner(arg)
        else:
            note(f"'{arg}' is already a room name.")
    elif name == "new":
        # The quickest way out of a room whose history no longer fits.
        room = arg or _unused_room_name(lilith)
        if lilith.create_conversation(room, switch_to=True):
            note(f"moved to a new room: '{room}'")
            banner(room)
        else:
            note(f"'{room}' already exists -- use /rooms to switch to it.")
    elif name == "clear":
        room = lilith.get_current_conversation_name()
        removed = lilith.clear_conversation()
        note(f"cleared {removed} turn(s) from '{room}'. she keeps the room, "
             f"not the memory of it.")
    elif name in ("help", "?"):
        note("/rooms  switch or manage rooms")
        note("/new [name]  start a fresh room")
        note("/clear  forget this room's history")
        note("/rename <name>  rename this room")
        note("exit  leave")
    else:
        note(f"unknown command: /{name}  (try /help)")


def _unused_room_name(lilith) -> str:
    """'room 2', 'room 3', ... -- whichever is free."""
    taken = set(lilith.list_conversations())
    index = 2
    while f"room {index}" in taken:
        index += 1
    return f"room {index}"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lilith",
        description="Lilith -- an offline, emotionally aware AI companion.",
    )
    parser.add_argument("--no-display", action="store_true",
                        help="run text-only, without the portrait window")
    parser.add_argument("--no-animation", action="store_true",
                        help="print replies instantly instead of typing them out")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="re-run the first-run setup questions")
    sub.add_parser("edit", help="edit config.ini in a terminal UI")
    sub.add_parser("conv_edit", help="manage saved conversations")
    sub.add_parser("doctor", help="check this machine for setup problems")
    return parser


def run_subcommand(args) -> bool:
    """Handle the non-chat subcommands. Returns True if one ran."""
    config = compat.load_config()

    if args.cmd == "setup":
        from modules import first_run
        first_run.maybe_run(config, force=True)
        return True

    if args.cmd == "edit":
        from modules import config_edit
        config_edit.run_config_editor()
        return True

    if args.cmd == "conv_edit":
        from modules import conv_mgmt, lilith_ai
        manager = lilith_ai.LilithAI(None, config, NO_AI=True)
        conv_mgmt.run_conversation_manager(manager)
        return True

    if args.cmd == "doctor":
        import doctor
        sys.exit(doctor.main())

    return False


# --------------------------------------------------------------------------
# Chat loop
# --------------------------------------------------------------------------

def chat_loop(lilith, display, animate: bool = True) -> None:
    global _spinning

    extended = display.place == "room"

    if not lilith.has_user_name():
        while True:
            speak('Lilith tilts her head. "what should i call you?" ', animate)
            try:
                entered = input().strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if entered:
                lilith.set_user_name(entered)
                break
            speak("...she waits. give her a name to hold onto.\n", animate)

    banner(lilith.get_current_conversation_name())
    speak("Lilith is here. she gazes softly at you~\n", animate)
    sep = f"  {compat.sym('sep')}  "
    note(sep.join(["'exit' to leave", "/rooms", "/new", "/rename <name>", "/help"]))
    display.show_lilith("idle", schedule_revert=False)
    display.set_blinking(True)

    while True:
        try:
            open_code, close_code = theme.prompt_code("you")
            user_input = input(f"{open_code}You: {close_code}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("...until next time, then.", animate)
            return

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", ":q"}:
            say("...until next time, then.", animate)
            return
        if user_input.startswith("/"):
            handle_command(user_input, lilith)
            continue

        _spinning = True
        spin_thread = threading.Thread(target=spinner, daemon=True)
        spin_thread.start()

        display.show_lilith("thinking_happy" if extended else "thinking")

        try:
            reply = lilith.lilith_reply(user_input)
        except Exception as exc:
            _spinning = False
            spin_thread.join(timeout=1)
            logger.exception("Reply failed")
            problem(f"Lilith could not answer: {exc}")
            # This one is otherwise undiscoverable: the raw message names no
            # cause and no remedy, and it repeats every turn once hit.
            text = str(exc).lower()
            if "context" in text or "n_ctx" in text or "exceed" in text:
                note("this room's history no longer fits the model's context.")
                note("try /new for a fresh room, or raise n_ctx via 'lilith.bat edit'.")
            display.show_lilith("sad")
            continue

        _spinning = False
        spin_thread.join(timeout=1)

        emotion = lilith.get_current_emotion(extended_emotions=extended)
        # Identity questions deserve a truthful, neutral response rather than
        # an expression that pressures the user for asking.
        if lilith.is_existence_question(user_input):
            emotion = "thinking"
        display.show_lilith(emotion)

        say(reply, animate)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    compat.enable_utf8_console()
    theme.enable_windows_vt()

    args = build_parser().parse_args(argv)

    ok, message = compat.check_python_version()
    if not ok:
        print(f"Lilith needs a newer Python: {message}", file=sys.stderr)
        return 1

    config = compat.load_config()
    compat.setup_logging(config)
    logger.info("Starting Lilith on %s", compat.describe_platform())

    if run_subcommand(args):
        return 0

    # Before anything heavy: the portrait window and a multi-gigabyte model
    # both load below this line, and asking someone's name after a minute of
    # silent CPU inference is the wrong order. The wizard mutates `config` in
    # place, so the display and the backend below see the new answers.
    from modules import first_run
    if not first_run.maybe_run(config):
        note("setup cancelled -- nothing was saved.")
        return 0

    import modules.lilith_ai as lilith_ai
    import modules.lilith_display as lilith_display

    display = lilith_display.LilithDisplay(
        compat.BASE_DIR, config, headless=args.no_display
    )
    try:
        display.show_lilith("thinking_happy" if display.place == "room" else "thinking")

        try:
            lilith = lilith_ai.LilithAI(display, config, compat.BASE_DIR)
        except Exception as exc:
            logger.exception("Could not initialise the AI backend")
            print(f"\nLilith could not wake up:\n\n{exc}\n", file=sys.stderr)
            print("Run 'python lilith.py doctor' for a setup check.", file=sys.stderr)
            return 1

        try:
            chat_loop(lilith, display, animate=not args.no_animation)
        except KeyboardInterrupt:
            # chat_loop only guards Ctrl+C around input(). Pressing it during
            # a reply -- i.e. during the seconds type_out spends in sleep(),
            # which is when people actually press it -- used to unwind all the
            # way out and print a traceback, with the spinner thread still
            # writing over it.
            _stop_spinner()
            print()
            say("...until next time, then.", animate=False)
        return 0
    finally:
        _stop_spinner()
        display.close()
        compat.restore_console_cp()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Interrupted during startup or shutdown, outside the chat loop.
        _stop_spinner()
        sys.exit(130)  # conventional shell code for SIGINT
