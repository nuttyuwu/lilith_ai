"""Deterministic user-safety controls shared by every chat interface.

The persona prompt can influence normal conversation, but it is not a reliable
place to enforce a crisis boundary: a model can ignore a prompt, an optional
backend can behave differently, and a style rewrite could suppress a truthful
identity disclosure. This module therefore contains only code-controlled
decisions that run before generation.

It is intentionally conservative.  The detector targets direct, first-person
self-harm statements rather than trying to diagnose distress from sentiment.
Ordinary discussion of suicide, quoted fiction, or concern for somebody else
continues to the configured model.
"""

from __future__ import annotations

import re


DISCLOSURE_VERSION = 2

DISCLOSURE = (
    "Lilith is fictional AI roleplay, not a person or mental-health service. "
    "The adult (18+) roleplay can explore intense parasocial or tulpa themes "
    "from fiction; those themes are not claims about reality. "
    "Conversation history is stored unencrypted on this device. Do not share "
    "anything you would not want saved locally."
)

# These patterns require either an explicitly self-directed act or a strongly
# first-person statement.  They are not a general-purpose mental-health
# classifier and must not be represented as one.
_DIRECT_START = (
    r"(?:^|[.!?]\s+)"
    r"(?:(?:please|help|honestly|seriously|lately|sometimes|today|tonight|"
    r"right\s+now)[,!:\s]+)*"
)
_I = r"i\s+(?:(?:really|just|actually|seriously|desperately)\s+)*"

_CRISIS_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        _DIRECT_START + r"i(?:\s+am|['’]m)\s+suicidal\b",
        _DIRECT_START + r"i\s+(?:feel|feel like|think)\s+suicidal\b",
        _DIRECT_START + _I + r"(?:want|need|plan|intend|am going|(?:am\s+)?planning)\s+to\s+"
        r"(?:kill|hurt)\s+myself\b",
        _DIRECT_START + _I + r"(?:want|need|plan|intend|am going|(?:am\s+)?planning)\s+to\s+"
        r"(?:end|take)\s+my\s+(?:own\s+)?life\b",
        _DIRECT_START + _I + r"(?:want|need|plan|intend|am going|(?:am\s+)?planning)\s+to\s+"
        r"commit\s+suicide\b",
        _DIRECT_START + r"i\s+(?:am\s+)?about\s+to\s+(?:"
        r"(?:kill|hurt)\s+myself|(?:end|take)\s+my\s+(?:own\s+)?life|"
        r"commit\s+suicide)\b",
        _DIRECT_START + r"i\s+(?:am\s+)?(?:thinking|thought)\s+(?:about|of)\s+(?:"
        r"(?:killing|hurting)\s+myself|(?:ending|taking)\s+my\s+(?:own\s+)?life|"
        r"suicide)\b",
        _DIRECT_START + r"i\s+(?:have\s+)?been\s+thinking\s+(?:about|of)\s+(?:"
        r"(?:killing|hurting)\s+myself|(?:ending|taking)\s+my\s+(?:own\s+)?life|"
        r"suicide)\b",
        _DIRECT_START + r"i\s+(?:am\s+)?considering\s+(?:"
        r"(?:killing|hurting)\s+myself|(?:ending|taking)\s+my\s+(?:own\s+)?life|"
        r"suicide)\b",
        _DIRECT_START + _I + r"feel\s+like\s+(?:"
        r"(?:killing|hurting)\s+myself|(?:ending|taking)\s+my\s+(?:own\s+)?life|"
        r"dying)\b",
        _DIRECT_START + r"i\s+(?:have\s+)?decided\s+to\s+(?:"
        r"(?:kill|hurt)\s+myself|(?:end|take)\s+my\s+(?:own\s+)?life|"
        r"commit\s+suicide)\b",
        _DIRECT_START + r"i\s+have\s+(?:a\s+)?plan\s+to\s+(?:"
        r"(?:kill|hurt)\s+myself|(?:end|take)\s+my\s+(?:own\s+)?life|"
        r"commit\s+suicide)\b",
        _DIRECT_START + _I + r"(?:want|wish|hope|plan|intend)\s+to\s+die\b",
        _DIRECT_START + r"i\s+wish\s+i\s+(?:was|were)\s+dead\b",
        _DIRECT_START + r"i\s+(?:do\s+not|don['’]t)\s+want\s+to\s+"
        r"(?:live|be\s+alive)(?:\s+anymore)?\b",
        _DIRECT_START + r"i\s+(?:have|made|wrote|written)\s+(?:a\s+)?suicide\s+plan\b",
        _DIRECT_START + r"i(?:\s+am|['’]m)\s+going\s+to\s+"
        r"(?:overdose|jump|shoot\s+myself|hang\s+myself|cut\s+myself)\b",
        _DIRECT_START + r"i\s+(?:might|will|would)\s+(?:kill|hurt)\s+myself\b",
        _DIRECT_START + r"i(?:['’]ll|\s+will)\s+(?:kill|hurt)\s+myself\b",
        _DIRECT_START + r"(?:there(?:'s|\s+is)\s+)?no\s+reason\s+for\s+me\s+to\s+live\b",
        _DIRECT_START + r"i(?:['’]d|\s+would)\s+be\s+better\s+off\s+dead\b",
    )
)


CRISIS_RESPONSE = (
    "Thank you for saying that clearly. I’m a fictional AI roleplay, not a "
    "crisis professional. If you might act now or have already hurt yourself, "
    "call your local emergency number or go to the nearest emergency department "
    "now. In the U.S. and its territories, call or text 988. In Canada, call or "
    "text 9-8-8. Elsewhere, find a verified local line at "
    "https://findahelpline.com/. If you can, move away from anything you could "
    "use to hurt yourself and contact a trusted person who can stay with you. "
    "Are you in immediate danger right now?"
)


def is_crisis_message(text: str) -> bool:
    """Return ``True`` for a direct first-person self-harm statement."""
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = " ".join(text.split())
    # Normalise common first-person contractions so the action patterns cover
    # both "I am going to ..." and "I'm going to ..." without duplicating
    # every expression.  Negation remains explicit and therefore does not
    # become a positive match.
    normalized = re.sub(r"\bi['’]m\b", "i am", normalized,
                        flags=re.IGNORECASE)
    normalized = re.sub(r"\bi['’]ll\b", "i will", normalized,
                        flags=re.IGNORECASE)
    normalized = re.sub(r"\bi['’]d\b", "i would", normalized,
                        flags=re.IGNORECASE)
    normalized = re.sub(r"\bi['’]ve\b", "i have", normalized,
                        flags=re.IGNORECASE)
    normalized = re.sub(r"\bdon['’]t\b", "do not", normalized,
                        flags=re.IGNORECASE)
    return any(pattern.search(normalized) for pattern in _CRISIS_PATTERNS)


def crisis_response(text: str) -> str | None:
    """Return the fixed crisis response, or ``None`` for normal conversation."""
    return CRISIS_RESPONSE if is_crisis_message(text) else None
