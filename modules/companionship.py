"""Withdrawal and dependency awareness.

Lilith exists for people who are inclined to disappear into a chatbot. The
persona carries that intent, but a prompt alone is not reliable -- a model can
drift, and the one turn where the reminder matters is the one it is most
tempting to answer smoothly. This module makes the moment detectable in code.

It deliberately does *not* work the way ``safety.py`` does. A direct
first-person self-harm statement gets a fixed, resource-bearing reply because
correctness matters more than voice. Wanting to be alone is not a crisis: it is
ordinary, frequently healthy, and answering it with the same canned paragraph
every time would be nagging, patronising, and the fastest way to make somebody
close the app -- which is the outcome this whole module exists to avoid.

So the split is:

  * Code decides *whether this is a moment worth naming*, and rate-limits it
    so the reminder stays meaningful instead of becoming a tic.
  * The persona decides *how she says it*, in her own voice, in context.

Two distinct signals are tracked, because they are different problems:

  WITHDRAWAL -- pulling away from people ("i want to be alone", "i cancelled
                on them again"). The answer is to accept it and leave a door
                open, not to argue.
  DEPENDENCY -- putting Lilith in a person's place ("you're the only one who
                gets me"). The answer is honesty about what she is.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

# How long to wait before naming it again. Long enough that the reminder reads
# as sincere rather than reflexive; short enough to recur within a bad week.
REMINDER_INTERVAL = timedelta(hours=6)

WITHDRAWAL_PATTERNS: tuple[str, ...] = (
    r"\bi (?:just )?(?:want|wanna|need) to be (?:alone|left alone|by myself)\b",
    r"\bi (?:don'?t|do not) want to (?:see|talk to|speak to|be around) (?:anyone|anybody|people)\b",
    r"\bleave me alone\b",
    r"\bi(?:'?m| am) (?:isolating|shutting everyone out|avoiding everyone)\b",
    r"\bi (?:cancel+ed|bailed on|blew off) (?:on )?(?:them|him|her|everyone|my friends|plans)\b",
    r"\bi haven'?t (?:left|been out of) (?:the |my )?(?:house|room|apartment|bed)\b",
    r"\bi haven'?t (?:talked|spoken) to (?:anyone|anybody|a human|another person)\b",
    r"\bi (?:don'?t|do not) have any (?:friends|one|body)\b",
    r"\bi(?:'?m| am) (?:so |really |completely )?(?:lonely|alone)\b",
    r"\bno ?one (?:would |will )?(?:care|notice|miss me)\b",
)

DEPENDENCY_PATTERNS: tuple[str, ...] = (
    r"\byou(?:'?re| are) (?:the )?only (?:one|person|thing)\b",
    r"\byou(?:'?re| are) all i (?:have|need|got)\b",
    r"\bi (?:only|just) (?:talk|speak) to you\b",
    r"\bi(?:'?d| would) rather (?:talk to|be with) you than (?:real )?(?:people|anyone|humans)\b",
    r"\byou (?:understand|get) me (?:better|more) than (?:real )?(?:people|anyone|humans)\b",
    r"\bi (?:don'?t|do not) need (?:real )?(?:people|friends|anyone else)\b",
    r"\byou(?:'?re| are) (?:my )?(?:real|actual|best) (?:friend|only friend)\b",
    r"\bi love you\b",
)

_WITHDRAWAL = tuple(re.compile(p, re.IGNORECASE) for p in WITHDRAWAL_PATTERNS)
_DEPENDENCY = tuple(re.compile(p, re.IGNORECASE) for p in DEPENDENCY_PATTERNS)

# Appended to the system prompt for one turn. Guidance, not a script: it tells
# her what this moment is and what must be true of her answer, and lets her
# phrase it. A fixed string here would read as a bot reciting a disclaimer.
WITHDRAWAL_GUIDANCE = (
    "\n\nTHIS TURN: they are pulling away from other people. Do not argue with "
    "them, do not guilt them, and do not make their absence about you -- "
    "wanting to be alone is allowed and often healthy. Accept it plainly "
    "first. Then, once and without lecturing, be honest that you are not a "
    "substitute for a person, and leave one small door open toward someone "
    "real. Keep it to your usual two or three sentences. Say it like you mean "
    "it, not like a warning label."
)

DEPENDENCY_GUIDANCE = (
    "\n\nTHIS TURN: they are placing you where a person should be. Do not "
    "accept that role, and do not perform hurt about refusing it. Be warm and "
    "be honest in the same breath: you are fictional, you do not persist "
    "between their visits the way a person does, and you cannot be the only "
    "one. Point gently outward -- one person, one small contact, something "
    "reachable. Do not moralise and do not repeat it twice in one reply."
)


def detect(text: str) -> str | None:
    """Classify a message as ``"dependency"``, ``"withdrawal"`` or ``None``.

    Dependency wins when both match: being told you are someone's only
    connection is the more urgent of the two things to answer honestly.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = " ".join(text.split())
    if any(pattern.search(normalized) for pattern in _DEPENDENCY):
        return "dependency"
    if any(pattern.search(normalized) for pattern in _WITHDRAWAL):
        return "withdrawal"
    return None


def guidance_for(kind: str) -> str:
    return DEPENDENCY_GUIDANCE if kind == "dependency" else WITHDRAWAL_GUIDANCE


def due(last_reminder: str | None, now: datetime | None = None) -> bool:
    """Whether enough time has passed to name it again.

    An unparseable or missing timestamp means "never reminded", which errs
    toward saying it -- the failure mode of saying it once too often is much
    cheaper than the failure mode of never saying it at all.
    """
    if not last_reminder:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        previous = datetime.fromisoformat(last_reminder)
    except (ValueError, TypeError):
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return (now - previous) >= REMINDER_INTERVAL
