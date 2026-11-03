"""
Web streaming endpoint tests.

Exercises /chat/stream through Flask's test client with a stub backend, so the
SSE framing, the consent gate, the state-tag stripping and the room API are all
covered without loading a 4 GB model.

Run with:  python -m unittest tests.test_web_stream
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import compat  # noqa: E402


def _flask_available() -> bool:
    try:
        import flask  # noqa: F401
        return True
    except ImportError:
        return False


class FakeClient:
    """A backend that hands back a canned reply, optionally token by token."""

    def __init__(self, text: str, streams: bool = True, size: int = 4):
        self.text = text
        self.streams = streams
        self.size = size
        self.calls = 0

    def supports_streaming(self) -> bool:
        return self.streams

    def stream_response(self, messages):
        self.calls += 1
        for i in range(0, len(self.text), self.size):
            yield self.text[i:i + self.size]

    def get_response(self, messages) -> str:
        self.calls += 1
        return self.text

    def count_tokens(self, text):
        return None

    def context_limit(self) -> int:
        return 8192


@unittest.skipUnless(_flask_available(), "Flask not installed")
class StreamEndpointTests(unittest.TestCase):
    def setUp(self):
        import web_lilith
        from modules.lilith_ai import LilithAI

        self.web_lilith = web_lilith
        self._tmp = tempfile.TemporaryDirectory()

        config = compat.load_config()
        config["ai_config"]["memory"] = str(Path(self._tmp.name) / "memory.json")
        config["ai_config"]["max_reply_sentences"] = "3"

        # Build the brain without a backend, then attach the stub. create_app
        # would otherwise load whatever [server] server_ai names.
        original = web_lilith.LilithAI
        web_lilith.LilithAI = lambda *a, **k: LilithAI(*a, **dict(k, NO_AI=True))
        try:
            self.app = web_lilith.create_app(config)
        finally:
            web_lilith.LilithAI = original

        self.lilith = self.app.config["LILITH"]
        self.client = self.app.test_client()
        self.consent = {web_lilith.SAFETY_CONSENT_HEADER:
                        web_lilith.SAFETY_CONSENT_VERSION}

    def tearDown(self):
        self._tmp.cleanup()

    def _events(self, response) -> list[dict]:
        body = response.get_data(as_text=True)
        return [json.loads(line[5:].strip())
                for line in body.splitlines() if line.startswith("data:")]

    def stream(self, message: str):
        return self.client.post("/chat/stream", json={"message": message},
                                headers=self.consent)

    # -- the stream itself -----------------------------------------------

    def test_deltas_build_the_reply_without_the_state_tag(self):
        self.lilith.client = FakeClient("...you're here. [state:smile]")
        events = self._events(self.stream("hey"))

        deltas = [e["text"] for e in events if e["type"] == "delta"]
        done = [e for e in events if e["type"] == "done"]

        self.assertGreater(len(deltas), 1, "the reply arrived in one piece")
        self.assertEqual("".join(deltas), "...you're here.")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["reply"], "...you're here.")
        self.assertEqual(done[0]["emotion"], "smile")

    def test_streamed_text_is_what_gets_remembered(self):
        self.lilith.client = FakeClient("One. Two. Three. Four. [state:idle]")
        events = self._events(self.stream("count"))
        shown = "".join(e["text"] for e in events if e["type"] == "delta")

        self.assertEqual(shown, "One. Two. Three.", "the sentence cap applies")
        history = self.lilith.get_history(limit=2)
        self.assertEqual(history[-1]["content"], shown)

    def test_identity_questions_get_a_neutral_expression(self):
        self.lilith.client = FakeClient("I'm fictional~ [state:dissapointed]")
        events = self._events(self.stream("are you real"))
        done = next(e for e in events if e["type"] == "done")
        self.assertEqual(done["emotion"], "thinking")

    def test_crisis_replies_are_not_dripped_out(self):
        self.lilith.client = FakeClient("should never be generated")
        events = self._events(self.stream("i want to kill myself"))
        deltas = [e for e in events if e["type"] == "delta"]

        self.assertEqual(len(deltas), 1, "crisis text must arrive whole")
        self.assertEqual(self.lilith.client.calls, 0, "the model was consulted")
        self.assertIn("988", deltas[0]["text"] + json.dumps(events))

    def test_non_streaming_backend_still_answers(self):
        self.lilith.client = FakeClient("just one piece. [state:idle]", streams=False)
        events = self._events(self.stream("hey"))
        deltas = [e["text"] for e in events if e["type"] == "delta"]
        self.assertEqual(deltas, ["just one piece."])

    def test_backend_failure_becomes_an_error_event(self):
        class Broken(FakeClient):
            def stream_response(self, messages):
                raise RuntimeError("base_url=http://secret:8080 key=sk-leak")
                yield  # pragma: no cover

        self.lilith.client = Broken("")
        events = self._events(self.stream("hey"))
        errors = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertNotIn("sk-leak", json.dumps(events),
                         "backend detail must stay in the log")

    # -- gates and siblings ----------------------------------------------

    def test_consent_is_required(self):
        self.lilith.client = FakeClient("hi")
        response = self.client.post("/chat/stream", json={"message": "hey"})
        self.assertEqual(response.status_code, 428)

    def test_empty_message_is_rejected_before_streaming(self):
        self.lilith.client = FakeClient("hi")
        response = self.client.post("/chat/stream", json={"message": "  "},
                                    headers=self.consent)
        self.assertEqual(response.status_code, 400)

    def test_capabilities_reports_streaming(self):
        self.lilith.client = FakeClient("hi")
        data = self.client.get("/capabilities").get_json()
        self.assertTrue(data["streaming"])
        self.assertIn(data["current_room"], data["rooms"])

    def test_capabilities_reports_no_streaming_for_whole_reply_backends(self):
        self.lilith.client = FakeClient("hi", streams=False)
        self.assertFalse(self.client.get("/capabilities").get_json()["streaming"])

    def test_translation_disables_streaming(self):
        """Streaming source text and then replacing it would be worse than waiting."""
        self.lilith.client = FakeClient("hi", streams=True)
        self.lilith.translator = object()
        self.assertFalse(self.client.get("/capabilities").get_json()["streaming"])

    def test_rooms_can_be_created_and_switched(self):
        created = self.client.post("/rooms", json={"action": "create",
                                                   "name": "night"}).get_json()
        self.assertIn("night", created["rooms"])
        self.assertEqual(created["current"], "night")

        switched = self.client.post("/rooms", json={"action": "switch",
                                                    "name": "default"}).get_json()
        self.assertEqual(switched["current"], "default")

    def test_renaming_an_unknown_room_fails_instead_of_creating_one(self):
        response = self.client.post("/rooms", json={"action": "rename",
                                                    "name": "ghost",
                                                    "new_name": "spirit"})
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("spirit", self.lilith.list_conversations())

    def test_history_returns_the_current_room(self):
        self.lilith.client = FakeClient("hello there. [state:smile]")
        # The body must be read: the reply is generated by consuming the stream.
        self._events(self.stream("hey"))
        history = self.client.get("/history").get_json()["history"]
        self.assertEqual(history[-1]["content"], "hello there.")


if __name__ == "__main__":
    unittest.main()
