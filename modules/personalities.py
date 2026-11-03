"""Independent personality prompts and histories sharing the same backend."""
from copy import deepcopy
from pathlib import Path

PROFILES = ('lilith', 'mira')

def profile_config(config, profile):
    if profile not in PROFILES:
        raise ValueError('Choose lilith or mira')
    result = deepcopy(config)
    result['ai_config']['character'] = profile
    if profile == 'mira':
        result['ai_config']['persona'] = 'mira_persona.txt'
        result['lilith_display']['assets_path'] = 'static'
        result['lilith_display']['place'] = 'mira'
        memory = Path(config['ai_config']['memory'])
        result['ai_config']['memory'] = str(memory.with_name(memory.stem + '.mira' + memory.suffix))
    return result
