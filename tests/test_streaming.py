"""
Streaming filter tests.

The property that matters is parity: a reply pushed through ReplyStream in
arbitrary chunks must equal the reply the non-streaming path produces from the
same text in one piece. If those two ever disagree, the user watches one thing
appear and a different thing gets written to memory.

Run with:  python -m unittest tests.test_streaming
"""

from __future__ import annotations

import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import lilith_ai, streaming  # noqa: E402


def whole_reply(raw: str, cap: int) -> tuple[str, str | None]:
    """The non-streaming pipeline, isolated from LilithAI's state."""
    state = None
    for match in lilith_ai._STATE_TAG.finditer(raw):
        candidate = match.group(1).lower()
        if candidate in lilith_ai.VALID_STATES:
            state = candidate
    cleaned = lilith_ai._STATE_TAG.sub("", raw).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if cap > 0:
        parts = re.split(r"(?<=[.!?~…])\s+", cleaned)
        cleaned = " ".join(parts[:cap]).strip()
    return cleaned, state


def streamed_reply(raw: str, cap: int, chunks: list[str]) -> tuple[str, str | None]:
    filt = streaming.ReplyStream(cap, lilith_ai.VALID_STATES)
    shown = ""
    for chunk in chunks:
        shown += filt.feed(chunk)
    shown += filt.finish()
    assert shown == filt.text, f"delta sum {shown!r} != text {filt.text!r}"
    return filt.text, filt.state


def split_every(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def random_split(text: str, rng: random.Random) -> list[str]:
    cuts = sorted(rng.sample(range(len(text) + 1), min(len(text), 6)))
    chunks, previous = [], 0
    for cut in cuts + [len(text)]:
        if cut > previous:
            chunks.append(text[previous:cut])
            previous = cut
    return chunks or [text]


SAMPLES = (
    "...you're here. [state:smile]",
    "Hehe. You really thought I wouldn't notice? [state:cheeky]",
    "One. Two. Three. Four. Five. [state:idle]",
    "I'm fictional... but a quiet story can still mean something~ [state:thinking]",
    "line one\n\n\n\nline two [state:sad]",
    "  leading and trailing whitespace  ",
    "no tag at all",
    "[state:happy]tag at the very start",
    "a tag [state:playful] in the middle of a sentence",
    "an invalid [state:ecstatic] value is removed but ignored",
    "brackets [not a tag] stay put",
    "trailing bracket is text [",
    "Wait... what? Really~ Yes. [STATE: THINKING_SAD ]",
    "Dr. Smith. Two sentences.",
    "unicode ellipsis… then more. [state:idle]",
    "",
    "   ",
    "[state:idle]",
)

CAPS = (0, 1, 2, 3, 10)


class ParityTests(unittest.TestCase):
    def test_matches_whole_reply_pipeline(self):
        for raw in SAMPLES:
            for cap in CAPS:
                expected = whole_reply(raw, cap)
                for size in (1, 2, 3, 5, 17, 500):
                    with self.subTest(raw=raw, cap=cap, size=size):
                        self.assertEqual(
                            streamed_reply(raw, cap, split_every(raw, size)),
                            expected,
                        )

    def test_matches_under_random_chunking(self):
        rng = random.Random(20260810)
        for raw in SAMPLES:
            if not raw:
                continue
            for cap in CAPS:
                expected = whole_reply(raw, cap)
                for _ in range(25):
                    chunks = random_split(raw, rng)
                    with self.subTest(raw=raw, cap=cap, chunks=chunks):
                        self.assertEqual(streamed_reply(raw, cap, chunks), expected)

    def test_fuzzed_replies_match(self):
        rng = random.Random(4242)
        alphabet = list("ab .!?~\n") + ["...", "[state:smile]", "[state:sad]",
                                        "[", "]", "state", "…"]
        for _ in range(400):
            raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            cap = rng.choice(CAPS)
            with self.subTest(raw=raw, cap=cap):
                self.assertEqual(
                    streamed_reply(raw, cap, random_split(raw, rng) if raw else [""]),
                    whole_reply(raw, cap),
                )


class BehaviourTests(unittest.TestCase):
    def test_state_tag_split_across_chunks_is_never_shown(self):
        filt = streaming.ReplyStream(0, lilith_ai.VALID_STATES)
        shown = "".join(filt.feed(part) for part in ("hi~ ", "[sta", "te:", "smi", "le]"))
        shown += filt.finish()
        self.assertEqual(shown, "hi~")
        self.assertEqual(filt.state, "smile")

    def test_partial_tag_that_never_completes_is_shown(self):
        filt = streaming.ReplyStream(0, lilith_ai.VALID_STATES)
        shown = "".join(filt.feed(part) for part in ("cost ", "[sta"))
        shown += filt.finish()
        self.assertEqual(shown, "cost [sta")

    def test_cap_stops_the_stream_early(self):
        filt = streaming.ReplyStream(2, lilith_ai.VALID_STATES)
        filt.feed("One. Two. Three.")
        self.assertTrue(filt.done, "the cap should be reached inside the chunk")
        self.assertEqual(filt.text, "One. Two.")
        self.assertEqual(filt.feed(" Four."), "",
                         "nothing may be shown after the cap")

    def test_trailing_space_is_not_yet_a_sentence_boundary(self):
        """"Two. " may be the end of the reply, in which case nothing is cut."""
        filt = streaming.ReplyStream(2, lilith_ai.VALID_STATES)
        filt.feed("One. Two. ")
        self.assertFalse(filt.done)
        self.assertEqual(filt.finish(), "")
        self.assertEqual(filt.text, "One. Two.")

    def test_state_tag_after_the_cap_is_still_captured(self):
        """The tag is written last; the cap must not cost us the portrait."""
        filt = streaming.ReplyStream(1, lilith_ai.VALID_STATES)
        filt.feed("One. Two. Three. ")
        self.assertTrue(filt.done)
        filt.feed("[state:")
        filt.feed("cheeky]")
        filt.finish()
        self.assertEqual(filt.text, "One.")
        self.assertEqual(filt.state, "cheeky")

    def test_no_cap_keeps_everything(self):
        filt = streaming.ReplyStream(0, lilith_ai.VALID_STATES)
        shown = filt.feed("One. Two. Three. Four. Five. Six.")
        self.assertFalse(filt.done, "an uncapped stream is never cut short")
        self.assertEqual(shown + filt.finish(), "One. Two. Three. Four. Five. Six.")

    def test_deltas_are_flushed_progressively(self):
        """A word must not be held until the whole reply has arrived."""
        filt = streaming.ReplyStream(3, lilith_ai.VALID_STATES)
        first = filt.feed("...you're ")
        self.assertEqual(first, "...you're",
                         "visible text should appear before the reply ends")

    def test_invalid_state_is_stripped_but_not_adopted(self):
        filt = streaming.ReplyStream(0, lilith_ai.VALID_STATES)
        shown = filt.feed("hi [state:ecstatic_wow]") + filt.finish()
        self.assertEqual(shown, "hi")
        self.assertIsNone(filt.state)

    def test_last_valid_state_wins(self):
        filt = streaming.ReplyStream(0, lilith_ai.VALID_STATES)
        filt.feed("a [state:sad] b [state:smile]")
        filt.finish()
        self.assertEqual(filt.state, "smile")

    def test_tag_regex_matches_the_ai_module(self):
        self.assertEqual(streaming.STATE_TAG.pattern, lilith_ai._STATE_TAG.pattern)
        self.assertEqual(streaming.STATE_TAG.flags, lilith_ai._STATE_TAG.flags)


if __name__ == "__main__":
    unittest.main()
