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

    def test_empty_dialogue_is_rejected_in_both_formats(self):
        for raw in ('', '[state:smile]', '{"reply":"[state:sad]","emotion":"sad"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.brain._extract_state(raw)

    def test_json_fences_fields_and_types(self):
        self.assertEqual(self.brain._extract_state('```json\n{"reply":"hi","emotion":"smile"}\n```'), ('hi', 'smile'))
        for raw in ('```json\n{"reply":"hi"}', '[]', '{"reply":"hi","emotion":null}', '{"reply":"hi","emotion":"idle","extra":1}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.brain._extract_state(raw)

    def test_sentence_cap_has_whole_stream_parity(self):
        from modules.reply_format import ValidatedStream
        raw = '{"reply":"One. Two. Three.","emotion":"thinking"}'
        stream = ValidatedStream(1, self.brain.valid_states)
        self.assertEqual(stream.feed(raw), '')
        self.assertEqual(stream.finish(), 'One.')

    def test_lilith_can_keep_legacy_format(self):
        config = compat.load_config()
        config['ai_config']['memory'] = str(Path(self.tmp.name) / 'lilith.json')
        lilith = LilithAI(config=profile_config(config, 'lilith'), NO_AI=True)
        self.assertFalse(lilith.structured_replies)
        self.assertEqual(lilith._extract_state('hi [state:smile]'), ('hi', 'smile'))

    def test_stop_and_audio_questions_do_not_depend_on_model(self):
        from unittest.mock import Mock
        self.brain.client = Mock()
        self.brain.client.get_response.side_effect = AssertionError('Model must not run')
        self.assertIn('stopped', self.brain.lilith_reply('stop roleplay', temperament='yandere'))
        self.assertIn('fictional AI version of Mira', self.brain.lilith_reply('Are you the real Mira?'))
        events = list(self.brain.reply_stream('Can you hear my voice?', temperament='soft'))
        self.assertIn("can't hear", events[-1][1]['reply'])
        self.brain.client.get_response.assert_not_called()
        history = self.brain.get_history()
        self.assertIn('Roleplay is stopped in this room', self.brain._build_payload(history, 'hello')[0]['content'])
        self.assertNotIn('Roleplay is stopped in this room', self.brain._build_payload(history, 'resume roleplay')[0]['content'])

    def test_native_schema_path_validates_and_preserves_emotion(self):
        from unittest.mock import Mock
        self.brain.client = Mock()
        self.brain.client.get_structured_response.return_value = '{"reply":"HEY!","emotion":"angry"}'
        events = list(self.brain.reply_stream('fictional jealousy', temperament='yandere'))
        self.assertEqual(events[-1][1]['emotion'], 'angry')
        schema = self.brain.client.get_structured_response.call_args.args[1]
        self.assertFalse(schema['additionalProperties'])
        self.assertIn('angry', schema['properties']['emotion']['enum'])
        self.brain.client.stream_response.assert_not_called()

    def test_llama_chat_receives_schema_without_changing_plain_calls(self):
        from unittest.mock import Mock
        from modules._llama_iface import AIInterface_Llama
        backend = object.__new__(AIInterface_Llama)
        backend._has_chat_api = True
        backend.max_tokens = 160
        backend.temperature = .4
        backend.llm = Mock()
        backend.llm.create_chat_completion.return_value = {'choices':[{'message':{'content':'{"reply":"hi","emotion":"idle"}'}}]}
        backend.get_structured_response([], {'type':'object'})
        self.assertIn('response_format', backend.llm.create_chat_completion.call_args.kwargs)
        backend.get_response([])
        self.assertNotIn('response_format', backend.llm.create_chat_completion.call_args.kwargs)

    def test_dramatic_punctuation_does_not_become_spam(self):
        text, mood = self.brain._extract_state('{"reply":"another girl?!?!?!?!?!","emotion":"angry"}')
        self.assertEqual(text, 'another girl?!?')
        self.assertEqual(mood, 'angry')
