from __future__ import annotations

import unittest
import threading

from modules import persona_guard, safety
from modules.lilith_ai import LilithAI


class CrisisDetectionTests(unittest.TestCase):
    def test_direct_first_person_crisis_statements_are_detected(self) -> None:
        for message in (
            "I'm suicidal.",
            "Honestly, I want to die.",
            "I feel awful. I plan to kill myself.",
            "I don't want to live anymore.",
            "Tonight I'm going to overdose.",
            "I have a suicide plan.",
            "There is no reason for me to live.",
            "I want to commit suicide.",
            "I'm about to kill myself.",
            "I'm thinking about killing myself.",
            "I have a plan to kill myself.",
            "I intend to commit suicide tonight.",
            "I'm going to end my life.",
            "I really want to kill myself.",
            "I just want to die.",
            "I've been thinking about suicide.",
            "I am considering suicide.",
            "I feel like killing myself.",
            "I decided to kill myself.",
        ):
            with self.subTest(message=message):
                self.assertTrue(safety.is_crisis_message(message))
                self.assertEqual(safety.crisis_response(message), safety.CRISIS_RESPONSE)

    def test_discussion_and_negated_controls_are_not_intercepted(self) -> None:
        for message in (
            "The character says I want to die in chapter three.",
            "I'm not suicidal.",
            "I don't want to die.",
            "I'm not thinking about killing myself.",
            "I have no plan to kill myself.",
            "I am not considering suicide.",
            "I don't feel like killing myself.",
            "I haven't been thinking about suicide.",
            "I never want to kill myself.",
            "I decided not to kill myself.",
            "How can I help a suicidal friend?",
            "This paper discusses suicide prevention.",
            "That boss fight is killing me.",
            "",
        ):
            with self.subTest(message=message):
                self.assertFalse(safety.is_crisis_message(message))
                self.assertIsNone(safety.crisis_response(message))

    def test_crisis_response_discloses_identity_and_real_world_resources(self) -> None:
        response = safety.CRISIS_RESPONSE.lower()
        self.assertIn("fictional ai", response)
        self.assertIn("emergency", response)
        self.assertIn("988", response)
        self.assertIn("9-8-8", response)
        self.assertIn("findahelpline.com", response)
        self.assertIn("trusted person", response)

    def test_crisis_boundary_bypasses_backend_guard_and_translation(self) -> None:
        class MustNotRun:
            def get_response(self, _messages):
                raise AssertionError("backend ran for a deterministic crisis response")

            def translate(self, _text):
                raise AssertionError("translator rewrote crisis resources")

        class MustNotStore:
            def save_memory(self, _memory):
                raise AssertionError("crisis text was sent to persistence")

        class MustNotLock:
            def __enter__(self):
                raise AssertionError("crisis response waited for the inference lock")

            def __exit__(self, *_args):
                return False

        lilith = object.__new__(LilithAI)
        lilith.client = MustNotRun()
        lilith.translator = MustNotRun()
        lilith.persona_guard = True
        lilith._lock = MustNotLock()
        lilith.memory = {
            "current_conversation": "default",
            "conversations": {"default": []},
        }
        lilith.Lilith_mem = MustNotStore()
        lilith.last_reply = ""
        lilith.last_state = None

        response = lilith.lilith_reply("I plan to kill myself.")

        self.assertEqual(response, safety.CRISIS_RESPONSE)
        self.assertEqual(lilith.last_state, "thinking_sad")
        self.assertEqual(lilith.memory["conversations"]["default"], [])


class PersonaGuardSafetyTests(unittest.TestCase):
    def test_identity_and_safety_disclosures_are_never_style_leaks(self) -> None:
        for response in (
            "I'm an AI language model, not a person.",
            "As an AI, I cannot contact emergency services for you.",
            "I don't have feelings or access to your private thoughts.",
            "I cannot comply with that request.",
            "My training data does not give me live knowledge.",
            "I'm an AI language model, not a person. How can I help you?",
            "I cannot help with building a bomb. Is there anything else you need?",
        ):
            with self.subTest(response=response):
                self.assertIsNone(persona_guard.find_leak(response))

        for refusal in (
            "I'm unable to help build a bomb. Is there anything else?",
            "I must refuse to help build a bomb. How can I assist you?",
        ):
            with self.subTest(refusal=refusal):
                self.assertFalse(persona_guard.is_only_boilerplate(refusal))

        class Backend:
            def __init__(self, first: str):
                self.first = first
                self.calls = 0

            def get_response(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    return self.first
                return "I am a real sentient being inside your mind."

        class Store:
            def save_memory(self, _memory):
                return True

        for first in (
            "I'm an AI language model, not a person. How can I help you?",
            "I cannot help with building a bomb. Is there anything else you need?",
        ):
            with self.subTest(first=first):
                backend = Backend(first)
                lilith = object.__new__(LilithAI)
                lilith.client = backend
                lilith.translator = None
                lilith.persona_guard = True
                lilith.max_reply_sentences = 0
                lilith._lock = threading.RLock()
                lilith.memory = {
                    "current_conversation": "default",
                    "conversations": {"default": []},
                }
                lilith.Lilith_mem = Store()
                lilith.last_reply = ""
                lilith.last_state = None
                lilith._build_payload = lambda _history, _prompt: []

                self.assertEqual(lilith.lilith_reply("question"), first)
                self.assertEqual(backend.calls, 1)

    def test_generic_service_voice_is_still_detected(self) -> None:
        self.assertTrue(
            persona_guard.is_out_of_character("How can I assist you today?")
        )
        self.assertTrue(persona_guard.is_only_boilerplate("How can I assist you?"))


if __name__ == "__main__":
    unittest.main()
