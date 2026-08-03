#!/usr/bin/env python3
"""
Strips generic assistant-speak out of Lilith's memory so she stays in character.

Fixes over the previous version:
  * It only understood the legacy ``data['conversation']`` layout. Since the
    multi-conversation rewrite, memory lives under
    ``data['conversations'][name]``, so the script reported "removed 0
    entries" no matter how much boilerplate had accumulated. Both layouts are
    handled now, and writes are atomic.
  * The pattern list moved to modules/persona_guard.py, which Lilith also uses
    before storage for diagnostics. Cleanup is deliberately more conservative:
    it removes only standalone boilerplate and preserves mixed disclosures or
    refusals.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime

from modules import compat, persona_guard

def is_boilerplate(entry: dict) -> bool:
    if entry.get("role") != "assistant":
        return False
    return persona_guard.is_only_boilerplate(entry.get("content", "") or "")


def clean(entries: list) -> tuple[list, int]:
    kept = [entry for entry in entries if not is_boilerplate(entry)]
    return kept, len(entries) - len(kept)


def main() -> int:
    compat.enable_utf8_console()
    config = compat.load_config()
    memory_file = compat.project_path(config["ai_config"]["memory"])

    if not memory_file.exists():
        print(f"No memory file at {memory_file} -- nothing to clean.")
        return 1

    backup = memory_file.with_name(
        f"{memory_file.stem}.bak-{datetime.now():%Y%m%d-%H%M%S}.json"
    )
    shutil.copy2(memory_file, backup)
    print(f"Backup written to {backup.name}")

    try:
        data = json.loads(memory_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"memory.json is not valid JSON: {exc}")
        return 1

    total = 0

    # Current layout.
    for name, entries in (data.get("conversations") or {}).items():
        if isinstance(entries, list):
            data["conversations"][name], removed = clean(entries)
            if removed:
                print(f"  {name}: removed {removed}")
            total += removed

    # Legacy layout, still supported.
    if isinstance(data.get("conversation"), list):
        data["conversation"], removed = clean(data["conversation"])
        if removed:
            print(f"  (legacy): removed {removed}")
        total += removed

    # A distinct suffix from LilithMemory.save_memory's ".json.tmp": sharing
    # it meant running this while Lilith was live had both processes writing
    # and os.replace-ing the very same scratch file.
    tmp = memory_file.with_suffix(".json.sanitize-tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, memory_file)

    print(f"Removed {total} out-of-character entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
