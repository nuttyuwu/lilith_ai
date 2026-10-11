import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from modules import compat
from modules.lilith_memory import LilithMemory


class SQLiteMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'memory.sqlite3'
        self.config = compat.load_config()
        self.config['ai_config']['memory'] = str(self.path)

    def store(self):
        return LilithMemory(config=self.config)

    def test_import_preserves_json_and_roundtrips_rooms(self):
        original = {'meta': {'user_name': 'Test', 'user_name_set': True},
                    'conversations': {'default': [{'role': 'user', 'content': 'hello'}]},
                    'current_conversation': 'default'}
        source = self.path.with_suffix('.json')
        source.write_text(json.dumps(original), encoding='utf-8')
        store = self.store()
        data = store.load_memory()
        self.assertEqual(data, original)
        data['conversations']['other'] = []
        self.assertTrue(store.save_memory(data))
        self.assertEqual(self.store().load_memory(), data)
        self.assertEqual(json.loads(source.read_text()), original)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
        self.assertTrue(list(self.path.parent.glob('memory.backup-*.sqlite3')))

    def test_concurrent_writers_preserve_both_appends(self):
        first, second = self.store(), self.store()
        a, b = first.load_memory(), second.load_memory()
        a['conversations'] = {'default': [{'role': 'user', 'content': 'A'}]}
        b['conversations'] = {'default': [{'role': 'user', 'content': 'B'}]}
        self.assertTrue(first.save_memory(a))
        self.assertTrue(second.save_memory(b))
        self.assertEqual([x['content'] for x in b['conversations']['default']], ['A', 'B'])

    def test_invalid_save_leaves_committed_state(self):
        store = self.store()
        data = store.load_memory()
        self.assertTrue(store.save_memory(data))
        data['not_json'] = object()
        self.assertFalse(store.save_memory(data))
        self.assertNotIn('not_json', self.store().load_memory())

    def test_bad_legacy_file_is_not_silently_discarded(self):
        self.path.with_suffix('.json').write_text('{bad', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.store().load_memory()

    def test_future_schema_is_not_overwritten(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):
            self.store().load_memory()

    def test_backup_can_be_restored_and_retention_is_bounded(self):
        from modules.sqlite_memory import SQLiteMemory
        database = SQLiteMemory(self.path)
        for day in range(1, 10):
            (self.path.parent / f'memory.backup-2020-01-{day:02}.sqlite3').write_bytes(b'old')
        database.backup().unlink()
        backup = database.backup()
        self.assertEqual(len(list(self.path.parent.glob('memory.backup-*.sqlite3'))), 7)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_missing_snapshot_and_non_object_import_are_rejected(self):
        from modules.sqlite_memory import SQLiteMemory
        source = self.path.with_suffix('.json')
        source.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            SQLiteMemory(self.path)
        source.write_text('{}', encoding='utf-8')
        database = SQLiteMemory(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM memory')
        with self.assertRaises(ValueError):
            database.load()

    def test_cleanup_uses_database_and_keeps_backup(self):
        from unittest.mock import patch
        import sanitize_memory
        store = self.store()
        data = store.load_memory()
        data['conversations'] = {'default': [{'role': 'user', 'content': 'keep'}]}
        self.assertTrue(store.save_memory(data))
        with patch.object(sanitize_memory.compat, 'load_config', return_value=self.config):
            self.assertEqual(sanitize_memory.main(), 0)
        self.assertEqual(self.store().load_memory()['conversations'], data['conversations'])
        self.assertTrue(list(self.path.parent.glob('memory.bak-*.json')))

