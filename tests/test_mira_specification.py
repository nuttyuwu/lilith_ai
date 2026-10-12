import unittest
from modules import compat
from modules.lilith_memory import LilithMemory
from modules.personalities import profile_config
from modules.character_runtime import guidance
from modules.lilith_ai import LilithAI
from pathlib import Path
import tempfile


class MiraSpecificationTests(unittest.TestCase):
    def test_new_spec_is_the_loaded_personality(self):
        config = profile_config(compat.load_config(), 'mira')
        persona = LilithMemory(config=config).load_persona()
        for requirement in ('HIGH-FIDELITY CHARACTER SIMULATION', 'Usually 2–12 words',
                            'NEVER GIVE AUTOMATIC APOLOGIES', 'There is no third-guy storyline',
                            'do not assume an emotional reunion or confrontation', '18+'):
            self.assertIn(requirement, persona)
        self.assertNotIn('Default to Mode D', persona)

    def test_soft_keeps_independence_and_yandere_does_not_invent_rivals(self):
        soft = guidance('mira', 'soft', ('idle', 'angry'), True)
        self.assertIn('not automatic agreement', soft)
        self.assertIn('2–12 words', soft)
        intense = guidance('mira', 'yandere', ('idle', 'angry'), True)
        self.assertIn('Do not invent romantic rivals', intense)
        self.assertIn('No narrator', intense)

    def test_money_joke_is_only_cued_by_relevant_message(self):
        with tempfile.TemporaryDirectory() as folder:
            config = compat.load_config()
            config['ai_config']['memory'] = str(Path(folder) / 'memory.json')
            brain = LilithAI(config=profile_config(config, 'mira'), NO_AI=True)
            self.assertIn('Do not mention or copy that joke here', brain._build_payload([], 'you forgot movie night')[0]['content'])
            self.assertNotIn('Do not mention or copy that joke here', brain._build_payload([], 'it cost 5 dollars')[0]['content'])
            history = [{'role':'user','content':'it cost 5 dollars'}, {'role':'assistant','content':'WHO IS DOLLORES'}]
            self.assertNotIn('Do not mention or copy that joke here', brain._build_payload(history, 'who did you think i meant lol')[0]['content'])
        from evaluate_character import assess
        self.assertFalse(assess('yandere_jealousy', 'WHOS DOLLARAS???', 'angry', {'angry'})['scene_relevant'])

