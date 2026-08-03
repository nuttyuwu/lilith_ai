#!/usr/bin/env python3
"""
Recompiles Python files on change, for instant syntax feedback while editing.

Fixes over the previous version: it watched a hardcoded two-file list, one of
which ('viewer.py') is at modules/viewer.py, so that entry never matched
anything. It now walks the project tree, skips virtualenvs and caches, and
reports a clean pass/fail summary.
"""

from __future__ import annotations

import py_compile
import sys
import time
from datetime import datetime
from pathlib import Path

from modules import compat

SKIP_DIRS = {"__pycache__", ".git", "venv", ".venv", "env", "models",
             "public", "node_modules", "llama.cpp"}


def python_files() -> list[Path]:
    return [
        path for path in compat.BASE_DIR.rglob("*.py")
        if not any(part in SKIP_DIRS for part in path.parts)
    ]


def compile_one(path: Path) -> bool:
    stamp = datetime.now().strftime("%H:%M:%S")
    relative = path.relative_to(compat.BASE_DIR)
    try:
        py_compile.compile(str(path), doraise=True)
        print(f"[{stamp}] {compat.sym('check')} {relative}")
        return True
    except py_compile.PyCompileError as exc:
        print(f"[{stamp}] {compat.sym('cross')} {relative}\n{exc}")
        return False


def main() -> int:
    compat.enable_utf8_console()

    if "--once" in sys.argv:
        results = [compile_one(path) for path in python_files()]
        failed = results.count(False)
        print(f"\n{len(results) - failed}/{len(results)} files compiled cleanly.")
        return 1 if failed else 0

    mtimes = {path: path.stat().st_mtime for path in python_files()}
    print(f"Watching {len(mtimes)} Python files under {compat.BASE_DIR}")
    print("Ctrl+C to stop.\n")

    try:
        while True:
            for path in python_files():
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime > mtimes.get(path, 0):
                    compile_one(path)
                    mtimes[path] = mtime
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
