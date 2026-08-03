from __future__ import annotations

import unittest

from modules._llama_iface import AIInterface_Llama


def _interface(fake_llm) -> AIInterface_Llama:
    interface = object.__new__(AIInterface_Llama)
    interface.llm = fake_llm
    interface.temperature = 0.7
    interface.max_tokens = 40
    interface._has_chat_api = True
    return interface


class LlamaChatFallbackTests(unittest.TestCase):
    def test_transient_chat_error_does_not_permanently_disable_chat_mode(self) -> None:
        class FakeLlama:
            def __init__(self):
                self.chat_calls = 0
                self.raw_calls = 0

            def create_chat_completion(self, **_kwargs):
                self.chat_calls += 1
                if self.chat_calls == 1:
                    raise RuntimeError("temporary GPU allocation failure")
                return {"choices": [{"message": {"content": "native chat"}}]}

            def __call__(self, _prompt, **_kwargs):
                self.raw_calls += 1
                return {"choices": [{"text": "one-turn fallback"}]}

        fake = FakeLlama()
        interface = _interface(fake)
        messages = [{"role": "user", "content": "hello"}]

        self.assertEqual(interface.get_response(messages), "one-turn fallback")
        self.assertTrue(interface._has_chat_api)
        self.assertEqual(interface.get_response(messages), "native chat")
        self.assertEqual((fake.chat_calls, fake.raw_calls), (2, 1))

    def test_explicit_missing_template_is_cached(self) -> None:
        class FakeLlama:
            def __init__(self):
                self.chat_calls = 0
                self.raw_calls = 0

            def create_chat_completion(self, **_kwargs):
                self.chat_calls += 1
                raise ValueError("model chat template is not available")

            def __call__(self, _prompt, **_kwargs):
                self.raw_calls += 1
                return {"choices": [{"text": "raw"}]}

        fake = FakeLlama()
        interface = _interface(fake)
        messages = [{"role": "user", "content": "hello"}]

        self.assertEqual(interface.get_response(messages), "raw")
        self.assertFalse(interface._has_chat_api)
        self.assertEqual(interface.get_response(messages), "raw")
        self.assertEqual((fake.chat_calls, fake.raw_calls), (1, 2))

    def test_context_overflow_is_not_hidden_by_raw_fallback(self) -> None:
        class FakeLlama:
            raw_calls = 0

            def create_chat_completion(self, **_kwargs):
                raise ValueError("tokens exceed the context window")

            def __call__(self, _prompt, **_kwargs):
                self.raw_calls += 1
                return {"choices": [{"text": "must not run"}]}

        fake = FakeLlama()
        interface = _interface(fake)

        with self.assertRaisesRegex(ValueError, "context window"):
            interface.get_response([{"role": "user", "content": "too long"}])
        self.assertEqual(fake.raw_calls, 0)


if __name__ == "__main__":
    unittest.main()
