import json
import tempfile
import unittest
from pathlib import Path
from modules import compat
from modules.lilith_ai import LilithAI
from modules.personalities import profile_config


class ReplyFormatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = compat.load_config()
        config['ai_config']['memory'] = str(Path(self.tmp.name) / 'memory.json')
        self.brain = LilithAI(config=profile_config(config, 'mira'), NO_AI=True)

    def test_json_reply_and_expression_are_separate(self):
        self.assertEqual(self.brain._extract_state('{"reply":"i need a minute","emotion":"sad_confused"}'), ('i need a minute', 'sad_confused'))

    def test_invalid_expression_uses_neutral(self):
        self.assertEqual(self.brain._extract_state('{"reply":"hey","emotion":"invented"}'), ('hey', 'idle'))

    def test_broken_json_is_rejected(self):
        for text in ('{"reply":"unfinished', '{"reply":17,"emotion":"sad"}', '{"reply":"","emotion":"sad"}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.brain._extract_state(text)

    def test_legacy_tags_still_work_and_plain_reply_is_neutral(self):
        self.assertEqual(self.brain._extract_state('hi [state:blushing]'), ('hi', 'blushing'))
        self.assertEqual(self.brain._extract_state('I am not angry.'), ('I am not angry.', 'idle'))

    def test_modes_are_turn_scoped_and_leave_persona_unchanged(self):
        original = self.brain.persona
        intense = self.brain._build_payload([], 'hey', temperament='yandere')[0]['content']
        gentle = self.brain._build_payload([], 'hey', temperament='soft')[0]['content']
        self.assertIn('YANDERE', intense)
        self.assertIn('SOFT', gentle)
        self.assertNotIn('YANDERE', gentle)
        self.assertEqual(self.brain.persona, original)
        self.assertIn('microphone', gentle)
        self.assertIn('"emotion"', gentle)
        with self.assertRaises(ValueError):
            self.brain._build_payload([], 'hey', temperament='invalid')

    def test_stream_and_whole_match_without_json_leaking(self):
        raw = json.dumps({'reply': 'wait... what?', 'emotion': 'confused'})
        class Client:
            def get_response(self, payload): return raw
            def supports_streaming(self): return True
            def stream_response(self, payload): yield from raw
        self.brain.client = Client()
        whole = self.brain.lilith_reply('hello')
        events = list(self.brain.reply_stream('hello'))
        self.assertEqual(''.join(value for kind, value in events if kind == 'delta'), whole)
        self.assertEqual(events[-1][1]['emotion'], 'confused')
        self.assertEqual(self.brain.get_history()[-1]['content'], whole)

    def test_invalid_json_never_commits_or_streams(self):
        class Client:
            def get_response(self, payload): return '{"reply":"bad'
            def supports_streaming(self): return True
            def stream_response(self, payload): yield '{"reply":"bad'
        self.brain.client = Client()
        before = self.brain.get_history()
        with self.assertRaises(ValueError): self.brain.lilith_reply('test')
        with self.assertRaises(ValueError): list(self.brain.reply_stream('test'))
        self.assertEqual(before, self.brain.get_history())
