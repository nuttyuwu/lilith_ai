"""
Incremental reply filtering for live token streaming.

The non-streaming path can post-process a finished reply: it pulls the
``[state:x]`` tag out, strips whitespace, and applies the sentence cap, all
with the whole text in hand.  Streaming has none of that luxury -- text is
shown the moment it arrives and cannot be taken back.

Three things therefore have to be decided one character at a time:

  * **The state tag must never be shown.**  It arrives at the end, but it can
    also arrive split across chunks (``"[sta"`` then ``"te:smile]"``), so any
    trailing text that is still a viable start of a tag is held back until it
    either completes or is ruled out.
  * **Trailing whitespace must be held back**, because it may need collapsing
    (``\\n{3,}`` -> ``\\n\\n``) or dropping entirely at the end.  It cannot be
    normalised until the character after it is known.
  * **The sentence cap has to stop the stream**, not truncate it afterwards.

``ReplyStream`` is written so that feeding a reply through it in *any* chunking
produces exactly the text that ``LilithAI._extract_state`` + ``str.strip`` +
``LilithAI._shorten`` produce from the same reply in one piece.  What the user
watched appear is therefore byte-identical to what is written to memory, and
streaming and non-streaming turns cannot drift apart.
tests/test_streaming.py enforces that parity against random chunk boundaries.
"""

from __future__ import annotations

import re

# Kept in sync with modules.lilith_ai by tests/test_streaming.py, which imports
# both and compares. Duplicated rather than imported to keep this module free
# of the AI backend import chain.
STATE_TAG = re.compile(r"\[\s*state\s*[:=]\s*([a-z_]+)\s*\]", re.IGNORECASE)

# Any suffix that could still become a state tag once more text arrives:
# "[", "[ ", "[s", "[stat", "[state", "[state:", "[state: smi", "[state:smile ".
# Alternatives are longest-first so "state" is preferred over its own prefixes.
# The trailing \s* matters: STATE_TAG permits "[state: sad ]", so a suffix
# ending in the space before "]" is still a live candidate and must be held.
PARTIAL_TAG = re.compile(
    r"\[\s*(?:state(?:\s*(?:[:=]\s*[a-z_]*\s*)?)?|stat|sta|st|s)?$",
    re.IGNORECASE,
)

_TRAILING_SPACE = re.compile(r"\s+$")
_BLANK_LINES = re.compile(r"\n{3,}")

# Matches LilithAI._shorten's sentence split: a terminator, then whitespace.
TERMINATORS = ".!?~…"


class ReplyStream:
    """Filters a token stream into displayable text.

    Feed raw model chunks to :meth:`feed`; it returns the text that is safe to
    show right now, which is often ``""`` while a tag candidate or a whitespace
    run is being held.  :meth:`finish` releases the end of the reply.

    ``done`` turns True once the sentence cap is reached, which is the caller's
    signal to stop generation early instead of paying for tokens nobody will
    see.
    """

    def __init__(self, sentence_cap: int = 0, valid_states: tuple[str, ...] = ()):
        self.sentence_cap = max(0, int(sentence_cap or 0))
        self.valid_states = valid_states
        self.state: str | None = None
        self.text = ""
        self.done = False
        self._held = ""
        self._sentences = 0

    # -- internals --------------------------------------------------------

    def _take_tags(self, buffer: str) -> str:
        """Remove every complete tag, remembering the last valid state.

        Mirrors ``_extract_state``: *all* matches are stripped from the text,
        but only recognised values update the portrait, so an invented state
        is dropped rather than shown to the user as literal text.
        """
        def replace(match: re.Match) -> str:
            candidate = match.group(1).lower()
            if not self.valid_states or candidate in self.valid_states:
                self.state = candidate
            return ""

        return STATE_TAG.sub(replace, buffer)

    def _normalise_gap(self, gap: str) -> str:
        """Whitespace between two visible characters, as _shorten would leave it."""
        if self.sentence_cap and self.text[-1:] in tuple(TERMINATORS):
            # _shorten joins the sentences it keeps with a single space.
            return " "
        return _BLANK_LINES.sub("\n\n", gap)

    def _emit(self, chunk: str) -> str:
        """Append to the visible reply, stopping at the sentence cap.

        Returns the delta actually shown, which is shorter than *chunk* when
        the cap falls inside it.
        """
        shown = ""
        for piece in _split_gaps(chunk):
            if not piece.strip():
                if not self.text:
                    continue  # leading whitespace; str.strip() would drop it
                at_boundary = self.text[-1:] in tuple(TERMINATORS)
                if at_boundary:
                    self._sentences += 1
                    if self.sentence_cap and self._sentences >= self.sentence_cap:
                        # The cap lands on this boundary: everything from the
                        # whitespace onwards belongs to a sentence we do not keep.
                        self.done = True
                        return shown
                piece = self._normalise_gap(piece)
            self.text += piece
            shown += piece
        return shown

    # -- public API -------------------------------------------------------

    def feed(self, chunk: str) -> str:
        """Absorb a raw model chunk; return the text safe to display now.

        Chunks are still parsed after the cap is reached. The state tag is
        written last, *after* the sentences that get discarded, so a stream cut
        short at the cap would leave the portrait guessing from keywords. Text
        past the cap is dropped; the tag inside it is not.
        """
        if not chunk:
            return ""

        buffer = self._take_tags(self._held + chunk)
        self._held = ""

        # Hold back anything that could still grow into a state tag, and any
        # trailing whitespace whose normalisation depends on what follows.
        partial = PARTIAL_TAG.search(buffer)
        if partial and partial.group(0):
            self._held = partial.group(0)
            buffer = buffer[: partial.start()]

        if self.done:
            return ""

        trailing = _TRAILING_SPACE.search(buffer)
        if trailing:
            self._held = trailing.group(0) + self._held
            buffer = buffer[: trailing.start()]

        return self._emit(buffer)

    def finish(self) -> str:
        """Release the tail of the reply. Returns any final visible text."""
        if self.done:
            self._held = ""
            return ""

        # A held partial tag that never completed was ordinary text after all
        # ("[" on its own, say), so it is shown rather than swallowed. Held
        # trailing whitespace is dropped, matching the final str.strip().
        remainder = _TRAILING_SPACE.sub("", self._take_tags(self._held))
        self._held = ""
        shown = self._emit(remainder) if remainder else ""
        self.done = True
        return shown


def _split_gaps(text: str) -> list[str]:
    """Split into alternating visible runs and whitespace runs."""
    return [piece for piece in re.split(r"(\s+)", text) if piece]
