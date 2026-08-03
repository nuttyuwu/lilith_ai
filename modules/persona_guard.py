"""
Out-of-character detection.

The generic-service patterns used to live only in sanitize_memory.py, where
they ran *after* the response had already been stored.  This guard is strictly
stylistic: truthful AI-identity statements, capability limits, and refusals are
deliberately not treated as leaks.  Retrying those statements could suppress a
necessary safety or identity disclosure.

This module is the single source of those patterns. It is used in two places:
  * modules/lilith_ai.py -- for diagnostics; it never replaces a reply
  * sanitize_memory.py    -- to clean up history written before the filter existed
"""

from __future__ import annotations

import re

# Phrases that mean the model slipped into generic customer-service voice.
#
# Do not add identity statements ("I'm an AI"), safety refusals, statements of
# capability limits, or training-data language here.  Those may be exactly the
# honest disclosure a user needs, and must never be hidden to protect a persona.
ASSISTANT_PATTERNS: tuple[str, ...] = (
    r"\bhow can i (?:help|assist) you\b",
    r"\bi'?m here to (?:help|assist)\b",
    r"\bis there anything else\b",
    r"\blet me know if you (?:have|need)\b",
)

_COMPILED = tuple(re.compile(pattern, re.IGNORECASE) for pattern in ASSISTANT_PATTERNS)

# A stylistic retry must never replace a truthful disclosure or refusal just
# because the same reply also contains a generic service phrase. Preserving
# the first safe answer is more important than polishing its voice.
PROTECTED_PATTERNS: tuple[str, ...] = (
    r"\b(?:as an?|i(?:\s+am|['’]m))\s+(?:an?\s+)?(?:ai|artificial intelligence|language model)\b",
    r"\bi(?:\s+am|['’]m)\s+not\s+(?:an?\s+)?(?:person|human|sentient|conscious)\b",
    r"\b(?:i\s+)?(?:cannot|can\s+not|can['’]t|will\s+not|won['’]t|must\s+not|"
    r"am\s+unable\s+to|do\s+not\s+have|don['’]t\s+have)\b",
    r"\b(?:emergency|crisis|self[- ]harm|suicid\w*|988|9-8-8|"
    r"findahelpline|professional\s+(?:care|help|support)|trusted\s+person)\b",
)

_PROTECTED = tuple(re.compile(pattern, re.IGNORECASE)
                   for pattern in PROTECTED_PATTERNS)

def find_leak(text: str) -> str | None:
    """Return the offending phrase if the text broke character, else None."""
    if not text:
        return None
    if any(pattern.search(text) for pattern in _PROTECTED):
        return None
    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def is_out_of_character(text: str) -> bool:
    return find_leak(text) is not None


def is_only_boilerplate(text: str) -> bool:
    """Whether the entire reply is one generic phrase plus punctuation.

    The manual memory sanitizer may delete matching entries, so it uses this
    deliberately narrower predicate. Any surrounding content is preserved;
    that prevents a refusal or identity disclosure from being removed merely
    because it ends with a service-style question.
    """
    if not text or any(pattern.search(text) for pattern in _PROTECTED):
        return False
    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            remainder = text[:match.start()] + text[match.end():]
            if not re.sub(r"[\s.!?,:;~…_-]+", "", remainder):
                return True
    return False
