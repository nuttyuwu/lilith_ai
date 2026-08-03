"""
OpenAI-compatible backend (LM Studio, llama.cpp server, vLLM, OpenAI itself).

Fixes over the previous version:
  * The base_url is normalised to end in ``/v1``. The shipped config.ini said
    ``http://127.0.0.1:1234/`` which is not an OpenAI-compatible endpoint, so
    every request 404'd.
  * A timeout is set, otherwise a stopped LM Studio hangs Lilith forever.
  * ``None`` content (which the API can legitimately return) no longer
    propagates into ``.strip()`` upstream.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def normalise_base_url(base_url: str) -> str:
    """LM Studio and friends serve the OpenAI API under /v1."""
    url = (base_url or "").strip().rstrip("/")
    if not url:
        return "http://127.0.0.1:1234/v1"
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class AIInterface_OpenAI:
    def __init__(
        self,
        config=None,
        model: str = "local-model",
        temperature: float = 0.7,
        max_tokens: int = 150,
        base_url: str = "",
        api_key: str = "",
        **kwargs,
    ):
        from openai import OpenAI

        timeout = 120
        if config is not None:
            timeout = config["server"].getint("request_timeout", fallback=120)

        self.base_url = normalise_base_url(base_url)
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=api_key or "not-needed",
            timeout=float(timeout),
        )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        logger.info(
            "OpenAI-compatible backend ready (url=%s model=%s)",
            self.base_url, self.model,
        )

    def get_response(self, messages: list) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            logger.error("Chat completion failed: %s", exc)
            raise RuntimeError(
                f"Could not reach the model server at {self.base_url} ({exc}). "
                "In LM Studio: Developer tab -> Start Server, and load a model."
            ) from exc

        if not response.choices:
            return ""
        return response.choices[0].message.content or ""
