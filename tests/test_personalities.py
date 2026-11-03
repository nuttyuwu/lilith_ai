import tempfile
import unittest
from pathlib import Path
from modules import compat
from modules.personalities import profile_config
from modules.lilith_ai import LilithAI

class PersonalityTests(unittest.TestCase):
    def test_mira_has_own_prompt_and_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = compat.load_config()
            config['ai_config']['memory'] = str(Path(tmp) / 'memory.json')
            original = LilithAI(None, config, NO_AI=True)
            mira = LilithAI(None, profile_config(config, 'mira'), NO_AI=True)
            self.assertIn('MIRA', mira.persona)
            self.assertNotEqual(original.Lilith_mem.MEMORY_FILE, mira.Lilith_mem.MEMORY_FILE)
            mira.set_user_name('Mira user')
            self.assertNotEqual(original.get_user_name(), mira.get_user_name())
            self.assertEqual(config['ai_config']['memory'], str(Path(tmp) / 'memory.json'))

    def test_invalid_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            profile_config(compat.load_config(), '../mira')

class CharacterWebTests(unittest.TestCase):
    def setUp(self):
        import web_lilith
        from unittest.mock import patch
        self.tmp = tempfile.TemporaryDirectory()
        config = compat.load_config()
        config['ai_config']['memory'] = str(Path(self.tmp.name) / 'memory.json')
        self.web = web_lilith
        with patch.object(web_lilith, 'LilithAI', side_effect=lambda *a, **k: LilithAI(*a, **dict(k, NO_AI=True))):
            self.app = web_lilith.create_app(config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_character_requests_do_not_switch_other_browsers(self):
        self.client.post('/nickname', json={'user_name': 'Mira friend'}, headers={'X-Lilith-Character': 'mira'})
        self.assertEqual(self.client.get('/character', headers={'X-Lilith-Character': 'mira'}).json['user_name'], 'Mira friend')
        self.assertNotEqual(self.client.get('/character').json['user_name'], 'Mira friend')
        self.assertEqual(self.client.get('/character', headers={'X-Lilith-Character': 'unknown'}).status_code, 400)

    def test_mira_rooms_stay_separate(self):
        self.client.post('/rooms', json={'action': 'create', 'name': 'reunion'}, headers={'X-Lilith-Character': 'mira'})
        self.assertNotIn('reunion', self.client.get('/rooms').json['rooms'])
        self.assertIn('reunion', self.client.get('/rooms', headers={'X-Lilith-Character': 'mira'}).json['rooms'])

    def test_public_hostname_requires_auth_and_same_origin(self):
        import base64
        from unittest.mock import patch
        password = 'test_only_password_long_enough'
        config = compat.load_config()
        config['ai_config']['memory'] = str(Path(self.tmp.name) / 'public.json')
        with patch.dict('os.environ', {'LILITH_PUBLIC_HOST': 'lilith.lil4kh.uk', 'LILITH_WEB_PASSWORD': password}), patch.object(self.web, 'LilithAI', side_effect=lambda *a, **k: LilithAI(*a, **dict(k, NO_AI=True))):
            client = self.web.create_app(config).test_client()
        base = 'https://lilith.lil4kh.uk'
        self.assertEqual(client.get('/history', base_url=base).status_code, 401)
        auth = {'Authorization': 'Basic ' + base64.b64encode(('khongor:' + password).encode()).decode()}
        self.assertEqual(client.get('/history', base_url=base, headers=auth).status_code, 200)
        self.assertEqual(client.post('/nickname', base_url=base, headers=auth, json={'user_name':'x'}).status_code, 403)
        auth['Origin'] = base
        self.assertEqual(client.post('/nickname', base_url=base, headers=auth, json={'user_name':'x'}).status_code, 200)
        self.assertEqual(client.get('/history', base_url='https://evil.example', headers=auth).status_code, 403)
        self.assertEqual(client.get('/history', base_url=base, headers=auth, environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code, 403)

    def test_cors_supports_character_chooser(self):
        from unittest.mock import patch
        config = compat.load_config()
        config['ai_config']['memory'] = str(Path(self.tmp.name) / 'cors.json')
        config['web']['cors_origins'] = 'http://localhost:8000'
        with patch.object(self.web, 'LilithAI', side_effect=lambda *a, **k: LilithAI(*a, **dict(k, NO_AI=True))):
            client = self.web.create_app(config).test_client()
        res = client.get('/character', headers={'Origin': 'http://localhost:8000', 'X-Lilith-Character':'mira'})
        self.assertEqual(res.headers.get('Access-Control-Allow-Origin'), 'http://localhost:8000')
        res = client.options('/character', headers={'Origin': 'http://localhost:8000', 'Access-Control-Request-Method':'GET', 'Access-Control-Request-Headers':'X-Lilith-Character'})
        self.assertIn('X-Lilith-Character', res.headers.get('Access-Control-Allow-Headers', ''))

    def test_mira_expression_tags_survive_both_reply_paths(self):
        from test_web_stream import FakeClient
        brain = self.app.config['CHARACTERS']['mira']
        headers = {'X-Lilith-Character':'mira', self.web.SAFETY_CONSENT_HEADER:self.web.SAFETY_CONSENT_VERSION}
        for mood in ('blushing', 'angry', 'sad_confused', 'confused'):
            brain.client = FakeClient('heyy [state:' + mood + ']')
            res = self.client.post('/chat', json={'message':'hey'}, headers=headers)
            self.assertEqual(res.json['emotion'], mood)
            self.assertEqual(res.json['reply'], 'heyy')
            res = self.client.post('/chat/stream', json={'message':'hey'}, headers=headers)
            import json
            events = [json.loads(line[5:]) for line in res.get_data(as_text=True).splitlines() if line.startswith('data:')]
            done = next(e for e in events if e['type'] == 'done')
            self.assertEqual(done['emotion'], mood)
            self.assertEqual(done['reply'], 'heyy')

    def test_desktop_mira_blink_matches_current_expression(self):
        from modules.lilith_display import LilithDisplay
        config = profile_config(compat.load_config(), 'mira')
        display = LilithDisplay(config=config, headless=True)
        for mood in ('idle', 'sad', 'confused', 'sad_confused', 'angry', 'smile', 'happy', 'cheeky', 'thinking'):
            display.LAST_SHOWN_STATE = mood
            self.assertEqual(display.image_for('blinking').stem, display.resolve_state(mood) + '_blink')

    def test_temperament_is_request_scoped_and_invalid_choice_rejected(self):
        import json
        brain = self.app.config['CHARACTERS']['mira']
        payloads = []
        class Client:
            def get_response(self, payload):
                payloads.append(payload[0]['content'])
                return json.dumps({'reply':'hmph!', 'emotion':'angry'})
            def supports_streaming(self): return False
        brain.client = Client()
        headers = {'X-Lilith-Character':'mira', 'X-Lilith-Safety-Consent':'2', 'X-Lilith-Temperament':'yandere'}
        result = self.client.post('/chat', json={'message':'In our fictional anime scene, I forgot our date.'}, headers=headers)
        self.assertEqual(result.json['emotion'], 'angry')
        self.assertIn('Selected temperament: YANDERE', payloads[-1])
        headers['X-Lilith-Temperament'] = 'soft'
        self.client.post('/chat/stream', json={'message':'hey'}, headers=headers).get_data()
        self.assertIn('Selected temperament: SOFT', payloads[-1])
        self.assertNotIn('Selected temperament: YANDERE', payloads[-1])
        headers['X-Lilith-Temperament'] = 'invalid'
        self.assertEqual(self.client.post('/chat', json={'message':'hey'}, headers=headers).status_code, 400)
        self.assertEqual(len(payloads), 2)

    def test_buffered_save_failure_does_not_claim_reply_was_shown(self):
        import json
        from unittest.mock import Mock
        brain = self.app.config['CHARACTERS']['mira']
        brain.client = Mock()
        brain.client.get_structured_response.return_value = '{"reply":"hey","emotion":"smile"}'
        brain.Lilith_mem.save_memory = Mock(return_value=False)
        headers = {'X-Lilith-Character':'mira', 'X-Lilith-Safety-Consent':'2'}
        response = self.client.post('/chat/stream', json={'message':'hey'}, headers=headers)
        events = [json.loads(line[5:]) for line in response.get_data(as_text=True).splitlines() if line.startswith('data:')]
        self.assertFalse(any(event['type'] == 'delta' for event in events))
        self.assertFalse(events[-1]['shown'])
