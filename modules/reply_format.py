"""Validate model dialogue separately from portrait metadata."""
import json
import re

TAG = re.compile(r'\[\s*state\s*[:=]\s*([a-z_]+)\s*\]', re.I)


def schema(states):
    return {'type':'object', 'properties': {
        'reply': {'type':'string', 'minLength':1, 'maxLength':280},
        'emotion': {'type':'string', 'enum':list(states)}},
        'required':['reply','emotion'], 'additionalProperties':False}


def clean(text):
    text = TAG.sub('', text).strip()
    return re.sub(r'[!?]{4,}', lambda match: match.group(0)[:3], text)


def decode(raw, valid_states):
    text = raw.strip()
    if text.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.I)
        if not match:
            raise ValueError('Incomplete response envelope')
        text = match.group(1).strip()
    if text.startswith('{') or (text.startswith('[') and not TAG.match(text)):
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {'reply', 'emotion'}:
            raise ValueError('Response requires reply and emotion fields')
        if not isinstance(data['reply'], str) or not data['reply'].strip():
            raise ValueError('Response reply must be nonempty text')
        if not isinstance(data['emotion'], str):
            raise ValueError('Response emotion must be text')
        state = data['emotion'].strip().lower()
        dialogue = clean(data['reply'])
        if not dialogue:
            raise ValueError('Response contains no dialogue')
        return dialogue, state if state in valid_states else 'idle'
    # Compatibility with older local models and previously tagged replies.
    state = 'idle'
    for tag in TAG.finditer(text):
        if tag.group(1).lower() in valid_states:
            state = tag.group(1).lower()
    dialogue = clean(text)
    if not dialogue:
        raise ValueError('Response contains no dialogue')
    return dialogue, state


class ValidatedStream:
    """Hold metadata until the completed envelope can be validated.

    Neither partial JSON nor an invalid envelope is displayed or persisted.
    This intentionally emits the validated text at completion, while native
    unstructured Lilith streams retain their existing token delivery.
    """
    def __init__(self, sentence_cap, valid_states):
        self.parts = []
        self.sentence_cap = sentence_cap
        self.valid_states = valid_states
        self.text = ''
        self.state = None

    def feed(self, chunk):
        self.parts.append(chunk)
        return ''

    def finish(self):
        self.text, self.state = decode(''.join(self.parts), self.valid_states)
        self.text = re.sub(r'\n{3,}', '\n\n', self.text)
        if self.sentence_cap > 0:
            self.text = ' '.join(re.split(r'(?<=[.!?~…])\s+', self.text)[:self.sentence_cap]).strip()
        return self.text
