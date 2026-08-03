"""
Persona and memory persistence.

Fixes over the previous version:
  * Saves are atomic (temp file + os.replace). The old code truncated
    memory.json before writing, so a crash or Ctrl+C mid-save wiped every
    conversation. This bites harder on Windows, where antivirus scanners
    routinely hold a lock on a file mid-write.
  * A corrupt memory.json is backed up instead of silently discarded.
  * A cross-process lock plus three-way merge preserves concurrent appends to
    the same conversation instead of letting the last full-file writer win.
  * ``load_memory`` no longer injects the legacy ``conversation`` key, which
    made the migration path in LilithAI re-run and log a warning on every
    single start.
  * Paths resolve against the project root, not the current directory.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from importlib import import_module
from pathlib import Path

from modules import compat

logger = logging.getLogger(__name__)

_MISSING = object()
_FILE_LOCK_TIMEOUT = 10.0
_FILE_LOCK_POLL = 0.025
_LOCKS_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


def _process_lock(path: Path) -> threading.RLock:
    """Return the in-process half of the lock for *path*.

    OS file locks coordinate processes, but their same-process semantics vary
    by platform.  This registry also serialises separate ``LilithMemory``
    instances living in one Python process (the web app and helper tools can
    otherwise create exactly that arrangement in tests or embedded use).
    """
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


def _same(left, right) -> bool:
    if left is _MISSING or right is _MISSING:
        return left is right
    return left == right


def _copy(value):
    return _MISSING if value is _MISSING else deepcopy(value)


def _merge_values(base, ours, theirs, path: tuple[str, ...] = ()):
    """Three-way merge JSON values, preserving concurrent history appends."""
    if _same(ours, theirs):
        return _copy(ours)

    # The active room is process-local UI state while the process is running.
    # Adopting another process's persisted selection during an unrelated save
    # would silently route this process's *next* reply into the wrong room.
    if path == ("current_conversation",):
        return _copy(theirs if ours is _MISSING else ours)

    if _same(ours, base):
        return _copy(theirs)
    if _same(theirs, base):
        return _copy(ours)

    # Mappings merge per key.  This also combines rooms created concurrently.
    if isinstance(ours, dict) and isinstance(theirs, dict):
        base_dict = base if isinstance(base, dict) else {}
        merged = {}
        keys = list(theirs)
        keys.extend(key for key in ours if key not in theirs)
        keys.extend(key for key in base_dict if key not in theirs and key not in ours)
        for key in keys:
            value = _merge_values(
                base_dict.get(key, _MISSING),
                ours.get(key, _MISSING),
                theirs.get(key, _MISSING),
                path + (str(key),),
            )
            if value is not _MISSING:
                merged[key] = value

        # Keep the selection valid if another process deleted the locally
        # active room and there was no concurrent local edit worth retaining.
        conversations = merged.get("conversations") if not path else None
        if isinstance(conversations, dict) and conversations:
            if merged.get("current_conversation") not in conversations:
                candidates = []
                for source in (ours, theirs, base_dict):
                    candidate = source.get("current_conversation")
                    if candidate in conversations:
                        candidates.append(candidate)
                merged["current_conversation"] = (
                    candidates[0] if candidates else next(iter(conversations))
                )
        return merged

    # Conversation histories are append-only during normal chat.  Both
    # suffixes can therefore be retained without adding private schema fields
    # to each turn.  The already-committed disk suffix comes first.
    base_list = [] if base is _MISSING else base
    if (len(path) >= 2 and path[0] == "conversations"
            and isinstance(base_list, list)
            and isinstance(ours, list) and isinstance(theirs, list)
            and ours[:len(base_list)] == base_list
            and theirs[:len(base_list)] == base_list):
        return deepcopy(
            base_list + theirs[len(base_list):] + ours[len(base_list):]
        )

    # A clear racing an append should fail in the data-preserving direction:
    # keep the appended history.  A later clear can then be retried explicitly.
    if len(path) >= 2 and path[0] == "conversations":
        if ours == [] and isinstance(base, list) and isinstance(theirs, list):
            if theirs[:len(base)] == base:
                return deepcopy(theirs)
        if theirs == [] and isinstance(base, list) and isinstance(ours, list):
            if ours[:len(base)] == base:
                return deepcopy(ours)

    # A deletion racing a real edit also fails towards retaining data.  For
    # conflicting scalar metadata, the process performing this save wins.
    if ours is _MISSING:
        return _copy(theirs)
    if theirs is _MISSING:
        return _copy(ours)
    return _copy(ours)


class LilithMemory:
    def __init__(self, base_dir=None, config=None, def_user_name: str = ""):
        config = config if config is not None else compat.load_config()
        self.config = config
        self.base_dir = Path(base_dir) if base_dir else compat.BASE_DIR

        self.PERSONA_FILE = compat.project_path(config["ai_config"]["persona"])
        self.MEMORY_FILE = compat.project_path(config["ai_config"]["memory"])
        self.DEFAULT_USER_NAME = def_user_name
        self._lock = threading.RLock()
        # (mtime_ns, size) of memory.json as of our last read or write. The
        # merge uses the exact baseline below; the stamp remains useful for
        # diagnostics and compatibility with older callers inspecting it.
        self._stamp: tuple[int, int] | None = None
        # Exact snapshot returned by load_memory (or last committed by us).
        # This is the common ancestor for conflict-aware three-way merges.
        self._baseline: dict | None = None

    # -- persona ----------------------------------------------------------

    _FALLBACK_PERSONA = (
        "You portray Lilith in fictional adult AI roleplay. You are not a "
        "person, sentient, inside the user's mind, or mental-health care. "
        "Remain honest about those boundaries and speak softly and briefly."
    )

    def load_persona(self) -> str:
        try:
            # utf-8-sig, matching load_config: a BOM added by Notepad would
            # otherwise become a literal ﻿ as the first character of the
            # system prompt.
            return self.PERSONA_FILE.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            logger.error("Persona file missing: %s", self.PERSONA_FILE)
            return self._FALLBACK_PERSONA
        except UnicodeDecodeError:
            # Someone re-saved the persona in a legacy Windows code page.
            logger.warning("Persona is not UTF-8; retrying with cp1251")
            try:
                return self.PERSONA_FILE.read_text(encoding="cp1251", errors="replace")
            except OSError as exc:
                logger.error("Could not read the persona: %s", exc)
                return self._FALLBACK_PERSONA
        except OSError as exc:
            # PermissionError, IsADirectoryError -- previously escaped as a
            # traceback out of LilithAI.__init__.
            logger.error("Could not read the persona: %s", exc)
            return self._FALLBACK_PERSONA

    # -- memory -----------------------------------------------------------

    def _blank(self) -> dict:
        return {
            "meta": {"user_name": self.DEFAULT_USER_NAME, "user_name_set": False},
            "conversations": {"default": []},
            "current_conversation": "default",
        }

    def load_memory(self) -> dict:
        with self._lock:
            data: dict = {}
            self._stamp = self._disk_stamp()
            if self.MEMORY_FILE.exists():
                try:
                    # utf-8-sig: a BOM from a hand-edit in Notepad is not
                    # corruption. UnicodeDecodeError is caught alongside
                    # JSONDecodeError below -- it subclasses ValueError, not
                    # JSONDecodeError, so it used to escape uncaught and skip
                    # the backup entirely, which is the likeliest way a
                    # memory.json gets mangled on Windows in the first place.
                    data = json.loads(self.MEMORY_FILE.read_text(encoding="utf-8-sig"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    backup = self.MEMORY_FILE.with_name(
                        f"{self.MEMORY_FILE.stem}.corrupt-"
                        f"{datetime.now():%Y%m%d-%H%M%S}.json"
                    )
                    logger.error("memory.json is invalid (%s); backed up to %s", exc, backup)
                    try:
                        shutil.copy2(self.MEMORY_FILE, backup)
                    except OSError:
                        pass
                    data = {}
                except OSError as exc:
                    logger.error("Could not read memory.json: %s", exc)
                    data = {}

            if not isinstance(data, dict):
                data = {}

            # Keep the exact disk shape as the merge ancestor. Defaults added
            # below are local normalization, not an external deletion that a
            # later three-way merge should undo.
            self._baseline = deepcopy(data)
            data.setdefault("meta", {})
            data["meta"].setdefault("user_name_set", False)
            return data

    def _disk_stamp(self) -> tuple[int, int] | None:
        try:
            stat = self.MEMORY_FILE.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def _read_disk(self) -> dict | None:
        try:
            disk = json.loads(self.MEMORY_FILE.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        return disk if isinstance(disk, dict) else None

    @contextmanager
    def _exclusive_file_lock(self):
        """Serialise read/merge/replace across Python processes."""
        lock_path = self.MEMORY_FILE.with_name(self.MEMORY_FILE.name + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        local_lock = _process_lock(lock_path)

        with local_lock, lock_path.open("a+b") as handle:
            # msvcrt locks byte ranges and needs the byte to exist.  Appending
            # one byte is harmless if two first-time processes race here.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)

            if compat.IS_WINDOWS:
                import msvcrt

                deadline = time.monotonic() + _FILE_LOCK_TIMEOUT
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("timed out waiting for memory lock")
                        time.sleep(_FILE_LOCK_POLL)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                # Imported only on POSIX; importing it at module scope breaks
                # every Windows startup before this branch can be selected.
                fcntl = import_module("fcntl")

                deadline = time.monotonic() + _FILE_LOCK_TIMEOUT
                while True:
                    try:
                        fcntl.flock(
                            handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                        )
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("timed out waiting for memory lock")
                        time.sleep(_FILE_LOCK_POLL)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def save_memory(self, memory: dict) -> bool:
        """Merge and atomically write memory.json. Returns False on failure."""
        with self._lock:
            tmp = self.MEMORY_FILE.with_name(self.MEMORY_FILE.name + ".tmp")
            tmp_created = False
            try:
                if not isinstance(memory, dict):
                    raise TypeError("memory must be a JSON object")
                self.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                with self._exclusive_file_lock():
                    disk = self._read_disk()
                    merged = memory
                    if self._baseline is not None and disk is not None:
                        merged = _merge_values(self._baseline, memory, disk)
                        if merged != memory:
                            logger.info(
                                "memory.json changed since load; merged concurrent edits"
                            )

                    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
                        tmp_created = True
                        json.dump(merged, handle, indent=2, ensure_ascii=False)
                        handle.flush()
                        os.fsync(handle.fileno())
                    compat.replace_atomic(tmp, self.MEMORY_FILE)
                    self._stamp = self._disk_stamp()
                    self._baseline = deepcopy(merged)

                # Keep the caller's long-lived snapshot synchronized so its
                # next append starts from the merged history.
                if merged is not memory:
                    memory.clear()
                    memory.update(deepcopy(merged))
                return True
            except (OSError, TypeError, ValueError) as exc:
                logger.error("Failed to save memory: %s", exc)
                if tmp_created:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
                return False

    # -- user name --------------------------------------------------------

    def get_user_name(self, memory: dict, default=None) -> str:
        if default is None:
            default = self.DEFAULT_USER_NAME
        meta = memory.setdefault("meta", {})
        name = meta.get("user_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        meta["user_name"] = default
        meta.setdefault("user_name_set", False)
        return default

    def set_user_name(self, memory: dict, name: str) -> bool:
        memory.setdefault("meta", {})
        memory["meta"]["user_name"] = name.strip()
        memory["meta"]["user_name_set"] = True
        return self.save_memory(memory)
