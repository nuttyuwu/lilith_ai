import json
import sqlite3
import tempfile
import unittest
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
        with sqlite3.connect(self.path) as db:
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
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):
            self.store().load_memory()

