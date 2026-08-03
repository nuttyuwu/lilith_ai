"""
Ollama backend.

Fixes over the previous version:
  * temperature / max_tokens are actually sent (via the ``options`` dict --
    the old code had a "idk how to set temp and max tokens" note; the answer
    is ``options={"temperature": ..., "num_predict": ...}``).
  * Honours an explicit host so Ollama can live in WSL2 while Lilith runs on
    Windows (set ``[server] ollama_host = http://127.0.0.1:11434``).
  * Connection failures produce a readable message instead of a traceback.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AIInterface_Ollama:
    def __init__(
        self,
        config=None,
        model: str = "gemma3",
        temperature: float = 0.7,
        max_tokens: int = 150,
        **kwargs,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        host = ""
        timeout = 120
        if config is not None:
            host = (config["server"].get("ollama_host", "") or "").strip()
            timeout = config["server"].getint("request_timeout", fallback=120)

        if host:
            from ollama import Client

            self._client = Client(host=host, timeout=timeout)
            self._chat = self._client.chat
        else:
            from ollama import chat as _chat

            self._client = None
            self._chat = _chat

        logger.info(
            "Ollama backend ready (model=%s host=%s temp=%s max_tokens=%s)",
            self.model, host or "default", self.temperature, self.max_tokens,
        )

    def get_response(self, messages: list) -> str:
        try:
            response = self._chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )
        except Exception as exc:
            logger.error("Ollama request failed: %s", exc)
            raise RuntimeError(
                f"Could not reach Ollama ({exc}). Is 'ollama serve' running, "
                f"and have you pulled the model with 'ollama pull {self.model}'?"
            ) from exc

        # Newer ollama clients return an object; older ones a plain dict.
        message = getattr(response, "message", None)
        if message is not None:
            return getattr(message, "content", "") or ""
        return (response.get("message") or {}).get("content", "") or ""
