"""Versioned transactional snapshots, preserving the existing memory contract.

The JSON-shaped document intentionally retains unknown metadata and legacy
room layouts. SQLite serializes the read/merge/write transaction across
processes; existing conflict-aware merge rules remain in LilithMemory.
"""
from contextlib import closing
from datetime import date
import json
import os
from pathlib import Path
import sqlite3


class SQLiteMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f'Unsupported memory schema version: {version}')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS memory (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            if db.execute('SELECT id FROM memory WHERE id=1').fetchone() is None:
                source = self.path.with_suffix('.json')
                data = json.loads(source.read_text(encoding='utf-8-sig')) if source.exists() else {}
                if not isinstance(data, dict):
                    raise ValueError('Legacy memory must be a JSON object')
                db.execute('INSERT INTO memory VALUES (1, ?)', (json.dumps(data, ensure_ascii=False),))
            db.execute('PRAGMA user_version=1')
        self.backup()

    def connect(self):
        # FULL durability is deliberate: chat is infrequent compared to disk IO.
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    @staticmethod
    def read(db):
        row = db.execute('SELECT payload FROM memory WHERE id=1').fetchone()
        if row is None:
            raise ValueError('Memory snapshot is missing')
        data = json.loads(row[0])
        if not isinstance(data, dict):
            raise ValueError('Memory snapshot must be a JSON object')
        return data

    def load(self):
        with closing(self.connect()) as db:
            return self.read(db)

    def save(self, memory, baseline, merge):
        self.backup()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            disk = self.read(db)
            merged = merge(baseline, memory, disk) if baseline is not None else memory
            payload = json.dumps(merged, ensure_ascii=False)
            db.execute('UPDATE memory SET payload=? WHERE id=1', (payload,))
        return merged

    def backup(self):
        """One consistent backup per day; retain seven daily snapshots."""
        target = self.path.with_name(f'{self.path.stem}.backup-{date.today().isoformat()}.sqlite3')
        if target.exists():
            return target
        # Serialize backup creation as well as saves. Unique temps avoid cross-
        # process interference; SQLite's backup API includes committed pages.
        import tempfile
        descriptor, name = tempfile.mkstemp(prefix=target.name + '.', suffix='.tmp', dir=target.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            with closing(self.connect()) as source, closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        for old in sorted(self.path.parent.glob(f'{self.path.stem}.backup-????-??-??.sqlite3'), reverse=True)[7:]:
            old.unlink(missing_ok=True)
        return target
