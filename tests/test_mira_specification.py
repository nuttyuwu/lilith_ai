import unittest
from modules import compat
from modules.lilith_memory import LilithMemory
from modules.personalities import profile_config
from modules.character_runtime import guidance


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

