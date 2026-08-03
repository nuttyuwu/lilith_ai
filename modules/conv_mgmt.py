"""
Conversation manager.

Fixes over the previous version:
  * Runs on Windows (see modules/_tui.py -- curses is not in the stdlib there).
  * A plain-text fallback for terminals without curses.
  * Bounds-checked, scrolling list: the old version wrote one row per
    conversation with no regard for the window height, so it crashed with
    ``curses.error`` once you had more conversations than terminal rows.
  * Labels are English now. They were Russian while every other screen was
    English, and Cyrillic through curses in a legacy Windows console is
    exactly the combination that renders as garbage. If you prefer the
    Russian text, only the strings in this file need changing.
"""

from __future__ import annotations

from modules import _tui, compat, theme


def rename_conversation(manager, old: str, new: str) -> bool:
    """Rename by copying the history across, then dropping the old key.

    Standalone so the chat REPL's ``/rename`` command can reuse it without
    going through the curses screen.
    """
    # Every equivalent method on LilithAI mutates memory under this lock; this
    # one reached in from outside without it, so a rename could interleave with
    # a reply being appended on the chat thread.
    lock = getattr(manager, "_lock", None)
    if lock is None:
        return _rename_locked(manager, old, new)
    with lock:
        return _rename_locked(manager, old, new)


def _rename_locked(manager, old: str, new: str) -> bool:
    memory = manager.memory
    conversations = memory.get("conversations", {})
    if new in conversations:
        return False
    conversations[new] = conversations.pop(old, [])
    if memory.get("current_conversation") == old:
        memory["current_conversation"] = new
    manager.Lilith_mem.save_memory(memory)
    return True


class ConversationTUI:
    def __init__(self, manager):
        self.manager = manager
        self.selected = 0

    def run(self, stdscr, curses) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        while True:
            conversations = self.manager.list_conversations()
            current = self.manager.get_current_conversation_name()

            self.selected = (
                max(0, min(self.selected, len(conversations) - 1))
                if conversations else 0
            )

            dot = compat.curses_sym("active_room")
            rows = [
                f"{dot if name == current else ' '} {name}"
                for name in conversations
            ]
            _tui.draw_list(
                stdscr, curses, "Rooms", rows, self.selected,
                subtitle=current or "-",
                footer=_tui.hint_line("enter switch", "c new", "r rename",
                                      "d delete", "q quit"),
            )

            try:
                press = stdscr.getch()
            except KeyboardInterrupt:
                return

            if press in (curses.KEY_UP, ord("k")) and self.selected > 0:
                self.selected -= 1
            elif press in (curses.KEY_DOWN, ord("j")) and self.selected < len(conversations) - 1:
                self.selected += 1
            elif press in (curses.KEY_ENTER, 10, 13) and conversations:
                self.manager.switch_conversation(conversations[self.selected])
            elif press in (ord("c"), ord("C")):
                name = _tui.prompt(stdscr, curses, "Name for the new conversation:")
                if name and not self.manager.create_conversation(name, switch_to=True):
                    _tui.notice(stdscr, curses, f"'{name}' already exists.")
            elif press in (ord("r"), ord("R")) and conversations:
                old = conversations[self.selected]
                new = _tui.prompt(stdscr, curses, f"Rename '{old}' to:", old)
                if new and new != old:
                    self._rename(old, new, stdscr, curses)
            elif press in (ord("d"), ord("D")) and conversations:
                name = conversations[self.selected]
                if _tui.confirm(stdscr, curses, f"Delete conversation '{name}'?"):
                    if not self.manager.delete_conversation(name):
                        _tui.notice(stdscr, curses, "Cannot delete the last conversation.")
            elif press in (27, ord("q")):
                return

    def _rename(self, old: str, new: str, stdscr=None, curses=None) -> bool:
        ok = rename_conversation(self.manager, old, new)
        if not ok and stdscr is not None:
            _tui.notice(stdscr, curses, f"'{new}' already exists.")
        return ok


def _plain_manager(manager) -> None:
    print("\nConversation manager (simple mode)")
    while True:
        conversations = manager.list_conversations()
        current = manager.get_current_conversation_name()
        labels = [f"{'*' if n == current else ' '} {n}" for n in conversations]
        actions = labels + ["** new conversation **", "** delete one **", "** quit **"]

        choice = _tui.ask_choice(f"Active: {current}", actions, allow_blank=False)
        if choice is None or choice == len(actions) - 1:
            return

        if choice == len(conversations):
            try:
                name = input("Name: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if name and not manager.create_conversation(name, switch_to=True):
                print("  That name is taken.")
        elif choice == len(conversations) + 1:
            index = _tui.ask_choice("Delete which?", conversations)
            if index is not None:
                if not manager.delete_conversation(conversations[index]):
                    print("  Cannot delete the last conversation.")
        else:
            manager.switch_conversation(conversations[choice])
            print(f"  Switched to {conversations[choice]}.")


def run_conversation_manager(manager) -> None:
    curses = _tui.load_curses()
    if curses is None:
        print(_tui.curses_install_hint())
        _plain_manager(manager)
        return
    tui = ConversationTUI(manager)
    try:
        curses.wrapper(lambda stdscr: tui.run(stdscr, curses))
    except Exception as exc:
        print(f"Terminal UI failed ({exc}); falling back to simple mode.")
        _plain_manager(manager)
    finally:
        # endwin() drops the Windows VT flag and invalidates our colour pairs.
        theme.reset()
