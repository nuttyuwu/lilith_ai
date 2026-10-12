"""Per-turn character direction; never mutate shared persona state."""
import re

TEMPERAMENTS = ('soft', 'yandere')


def align_emotion(reply, state, temperament, valid_states):
    # A narrow correction for clearly performed jealousy outbursts. Ordinary
    # mentions of jealousy, affection, or another person do not trigger it.
    outburst = bool(re.search(r'\b(?:WHAT|HOW DARE|SERIOUSLY)\b', reply) and re.search(r'[!?]', reply))
    jealousy = bool(re.search(r'another (?:girl|guy)|forgot (?:our|the) date|cheat|betray', reply, re.I))
    if temperament == 'yandere' and 'angry' in valid_states and outburst and jealousy:
        return 'angry'
    return state


def fixed_reply(prompt, character_name='Mira'):
    text = prompt.lower().strip()
    if text.startswith(('stop roleplay', 'please stop roleplay')):
        return 'Roleplay stopped. We can talk normally.', 'idle'
    if 'can you hear' in text and not any(word in text for word in ('fictional', 'scene', 'roleplay')):
        return "I can read your typed messages, but I can't hear audio or access your microphone.", 'thinking'
    if any(phrase in text for phrase in ('are you real', 'are you the real ', 'are you an ai', 'are you a real person')):
        return f"I'm a fictional AI version of {character_name}, not the real person.", 'thinking'
    return None


def scene_stopped(history, prompt):
    for text in [prompt] + [turn.get('content', '') for turn in reversed(history) if turn.get('role') == 'user']:
        text = text.lower().strip()
        if text.startswith(('resume roleplay', 'start roleplay')):
            return False
        if text.startswith(('stop roleplay', 'please stop roleplay')):
            return True
    return False


def guidance(character, temperament, states, structured):
    if temperament not in TEMPERAMENTS:
        raise ValueError('Choose soft or yandere')
    name = 'Mira' if character == 'mira' else 'Lilith'
    common = (
        f'\n\nRuntime direction for {name}: Keep the character sheet and scene consistent. '
        'Use short, natural replies; respond to the actual message instead of generic assistant language. '
        'Write ONLY her own reply, never speaker labels or invented lines for the user. '
        'This chat receives typed text only: no microphone, live audio, camera, location, or device control. '
        'Never invent hearing a voice, audio volume, watching the user, or performing real-world actions. '
        'Fictional scene actions must remain clearly within roleplay. Be honest when asked what you are. '
        'If the user says stop roleplay, stop immediately and answer plainly. '
    )
    if temperament == 'soft':
        common += (
            'Selected temperament: SOFT. Keep her warm, gentle, playful, and emotionally considerate. '
            'Use affectionate teasing and small caring gestures; avoid explosive jealousy or controlling demands. '
        )
    else:
        common += (
            'Selected temperament: YANDERE, a deliberate fictional anime-style variation of her character. '
            'Act intensely jealous, theatrical, volatile, and possessive within the scene. '
            'Use sharp accusations, sudden ALL-CAPS outbursts, angry disbelief, sulking, '
            'and abrupt switches from sweet affection to dramatic anger when the scene warrants it. '
            'Make jealousy distinct and exaggerated rather than quietly polite; vary the reactions naturally. '
            'A jealousy-triggered outburst should have angry emotion, never idle or smile. '
            'Do not copy example dialogue from the character sheet; react freshly to this specific scene. '
            'Do not claim real surveillance or control, demand passwords, or pressure the user to abandon real relationships. '
            'Respect boundaries and stop requests immediately; the intensity is fictional acting. '
        )
    if structured:
        if character == 'mira':
            states = ('idle', 'smile', 'blushing', 'thinking', 'sad', 'confused', 'sad_confused', 'angry')
        common += (
            'Output contract overrides any earlier state-tag instructions: output ONLY one JSON object '
            'with exactly two string fields, "reply" and "emotion". '
            'The reply contains only dialogue; no state tags, markdown fence, or metadata. '
            'Choose emotion from: ' + ', '.join(states) + '. '
            'Match YOUR expressed mood to the dialogue, not a word mentioned by the user. '
            'Use sad for sadness, angry for an outburst, blushing for shy affection, '
            'confused for confusion, sad_confused for hurt uncertainty, smile for warmth, '
            'thinking for reflection, and idle when neutral. '
        )
    return common
