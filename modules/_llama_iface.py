"""
llama.cpp backend (offline GGUF inference).

Fixes over the previous version:
  * This backend no longer downloads anything. The GGUF is fetched by hand and
    placed in ``models/``; see the README. Auto-download was removed because it
    only ever worked against a Hugging Face repo, and the weights are now
    distributed as a direct link that no library can resolve on its own. A
    missing file is a clear, actionable error instead of a silent 4 GB fetch.
  * The configured filename is a preference, not a requirement. If exactly one
    GGUF is present it is used regardless of its name -- ``local_model`` having
    to match "exactly" was a real trap, since a browser that renames a download
    to "...(1).gguf" would otherwise break the whole backend.
  * Paths are joined with pathlib instead of string concatenation, so
    ``model_path`` works with or without a trailing slash and on Windows
    backslash paths.
  * Uses the GGUF's own chat template via ``create_chat_completion`` when
    available, instead of hand-rolling a Llama-2 style prompt that the
    Lilith 8B model was not trained on.
  * ``n_threads`` defaults to the real CPU count instead of a hardcoded 4.
  * History trimming was removed from here and moved into LilithAI. It was
    backend-specific, so Ollama, LM Studio and transformers sent unbounded
    history and silently overran their context windows.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from modules import compat

logger = logging.getLogger(__name__)


def _place_it_here(model_dir: Path) -> str:
    """The instruction every failure in this module ends with."""
    return (
        f"Download it from:\n  {compat.MODEL_DOWNLOAD_URL}\n"
        f"and put the .gguf file in:\n  {model_dir}"
    )


def find_gguf(model_dir: Path, configured: str = "") -> Path:
    """Find the GGUF to load. Looks in ``model_dir`` and nowhere else.

    Nothing is ever downloaded. The resolution order is deliberate:

      1. The configured ``local_model``, if that file is actually there.
      2. Otherwise, the only ``*.gguf`` in the folder -- whatever it is called.

    Step 2 is the important one. Requiring the filename to match config.ini
    exactly meant a download that arrived as ``Lilith_AI_8B_Q4_0 (1).gguf``, or
    a differently-quantised build, failed with a "not found" naming a file the
    user could plainly see was sitting right there.

    Ambiguity is never guessed at: more than one GGUF and no valid
    ``local_model`` raises and lists the candidates.
    """
    if configured:
        candidate = model_dir / configured
        if candidate.is_file():
            return candidate

    if not model_dir.is_dir():
        raise FileNotFoundError(
            f"The model folder does not exist yet: {model_dir}\n"
            + _place_it_here(model_dir)
        )

    found = sorted(p for p in model_dir.glob("*.gguf") if p.is_file())

    if not found:
        missing = f" ({configured} is not there)" if configured else ""
        raise FileNotFoundError(
            f"No .gguf model found in {model_dir}{missing}\n"
            + _place_it_here(model_dir)
        )

    if len(found) == 1:
        if configured and found[0].name != configured:
            # Worth saying out loud: the config and the disk disagree, and we
            # are about to ignore the config. Silence here would look like the
            # setting had no effect.
            logger.warning(
                "[ai_config] local_model is %r, but the only model in %s is "
                "%r -- loading that instead.", configured, model_dir, found[0].name,
            )
        return found[0]

    names = "\n  ".join(p.name for p in found)
    raise FileNotFoundError(
        f"More than one .gguf in {model_dir} and [ai_config] local_model "
        f"({configured or 'unset'}) does not name any of them.\n"
        f"Set it to one of:\n  {names}"
    )


class AIInterface_Llama:
    def __init__(
        self,
        config=None,
        temperature: float = 0.7,
        max_tokens: int = 150,
        **kwargs,
    ):
        from llama_cpp import Llama

        config = config if config is not None else compat.load_config()
        section = config["ai_config"]

        self.temperature = temperature
        self.max_tokens = max_tokens

        model_dir = compat.project_path(section.get("model_path", "models"))

        n_ctx = section.getint("n_ctx", fallback=8192)
        n_batch = section.getint("n_batch", fallback=256)
        n_gpu_layers = section.getint("n_gpu_layers", fallback=0)
        n_threads = section.getint("n_threads", fallback=0) or (os.cpu_count() or 4)

        # Raises with download instructions when the folder is empty. Let it
        # propagate: _iface wraps backend construction, and lilith.py turns the
        # message into "Lilith could not wake up: ..." with the fix in it.
        self.model_path = find_gguf(model_dir, section.get("local_model", "").strip())

        logger.info(
            "Loading GGUF %s (n_ctx=%s threads=%s batch=%s gpu_layers=%s)",
            self.model_path, n_ctx, n_threads, n_batch, n_gpu_layers,
        )
        self.llm = Llama(
            model_path=str(self.model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_batch=n_batch,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )

        # Not every build exposes the chat-completion helper.
        self._has_chat_api = hasattr(self.llm, "create_chat_completion")

    def count_tokens(self, text: str) -> int:
        """Exact token count for this model, for LilithAI's context budget."""
        return len(self.llm.tokenize(text.encode("utf-8", "ignore")))

    @property
    def context_limit(self) -> int:
        try:
            return int(self.llm.n_ctx())
        except Exception:
            return 0

    @staticmethod
    def _is_context_overflow(exc: Exception) -> bool:
        """True when the call failed for length, not for a missing template."""
        text = str(exc).lower()
        return (
            "context window" in text
            or "exceed" in text and "token" in text
            or "n_ctx" in text
        )

    @staticmethod
    def _is_missing_chat_template(exc: Exception) -> bool:
        """True only for an explicit, persistent missing-template failure."""
        text = str(exc).lower()
        if "chat template" not in text:
            return False
        return any(
            marker in text
            for marker in (
                "not available",
                "not found",
                "not set",
                "missing",
                "does not have",
                "unsupported",
            )
        )

    @staticmethod
    def _messages_to_prompt(messages: list) -> str:
        """Fallback prompt builder for builds without the chat API."""
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"<<SYS>>\n{content}\n<</SYS>>\n\n"
            elif role == "user":
                prompt += f"User: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"
        return prompt + "Assistant: "

    def get_response(self, messages: list) -> str:

        if self._has_chat_api:
            try:
                result = self.llm.create_chat_completion(
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=0.9,
                )
                choice = result["choices"][0]
                return (choice.get("message", {}).get("content") or "").strip()
            except Exception as exc:
                # A length error is transient: the prompt was too long *this
                # turn*. The raw-prompt fallback is no shorter, so it would
                # fail too -- and disabling the chat API here would silently
                # switch every later reply to a Llama-2 prompt this model was
                # never trained on, permanently degrading quality with no
                # visible sign. Let the caller trim and retry instead.
                if self._is_context_overflow(exc):
                    raise
                # Some GGUFs genuinely ship without a usable chat template;
                # that property is persistent and can be cached. Every other
                # error may be transient (GPU reset, allocation failure, or a
                # backend hiccup), so use the compatibility fallback for this
                # turn without permanently degrading every later reply.
                if self._is_missing_chat_template(exc):
                    logger.warning(
                        "Model has no usable chat template (%s); using raw prompts", exc
                    )
                    self._has_chat_api = False
                else:
                    logger.warning(
                        "create_chat_completion failed for this turn (%s); "
                        "using raw prompt and retrying chat mode next turn",
                        exc,
                    )

        output = self.llm(
            self._messages_to_prompt(messages),
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=0.9,
            stop=["User:", "</s>", "<|eot_id|>"],
        )
        return (output["choices"][0]["text"] or "").strip()
