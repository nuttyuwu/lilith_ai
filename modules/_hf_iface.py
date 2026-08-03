"""
HuggingFace transformers backend.

Fixes over the previous version:
  * ``get_response`` was handing the raw list of message dicts straight to the
    tokenizer, which cannot tokenise dicts -- the backend could never answer.
    It now renders the conversation with the model's own chat template.
  * The decoded output included the entire prompt, so Lilith replied with a
    copy of her own persona. Only the newly generated tokens are decoded now.
  * ``local_dir_use_symlinks`` was removed from huggingface_hub, and
    ``torch_dtype`` was renamed to ``dtype`` in recent transformers. Both are
    now version-probed rather than assumed.
  * Symlink-free downloads matter on Windows, where creating symlinks needs
    Developer Mode or admin rights; the cache path avoids them entirely.
  * Repository Python and pickle-based model weights are rejected.  Only
    safetensors weights may be loaded, so a floating repository revision
    cannot turn a model download into arbitrary-code execution.
"""

from __future__ import annotations

import inspect
import hashlib
import json
import logging
import os
import re

from modules import compat

logger = logging.getLogger(__name__)


class AIInterface_HF:
    def __init__(
        self,
        config=None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 150,
        **kwargs,
    ):
        config = config if config is not None else compat.load_config()
        section = config["ai_config"]

        # `model` is always supplied by _iface from [ai_config] ai_model, whose
        # default is "gemma3" -- so the `or` below could never reach
        # hf_repo_id, and this backend tried to download a repo literally
        # named "gemma3". A bare name with no owner/ is never a valid repo id,
        # so treat it as "not set" and fall through to hf_repo_id.
        candidate = (model or "").strip()
        if "/" not in candidate:
            candidate = section.get("hf_repo_id", "").strip() or candidate
        self.model_id = candidate
        self.model_name = self.model_id.split("/")[-1]
        self.local_dir = compat.project_path(section.get("model_path", "models"))

        revision = section.get("hf_revision", "").strip()
        if revision and re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
            raise ValueError(
                "[ai_config] hf_revision must be a full 40-character Hugging "
                "Face commit SHA (or blank), not a branch, tag, or abbreviated SHA."
            )
        self.revision = revision.lower()

        # Repositories owned by different accounts can share the same final
        # name, and changing a configured revision must never reuse stale
        # weights. Keep each repo/revision identity in its own local directory.
        cache_identity = f"{self.model_id}\n{self.revision or '<default>'}"
        cache_key = hashlib.sha256(cache_identity.encode("utf-8")).hexdigest()[:12]
        self.model_path = self.local_dir / f"{self.model_name}-{cache_key}"

        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = 0.9
        self.top_k = 50
        self.tokenizer = None
        self.model = None
        self.token = os.getenv("HF_API_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")

    # -- loading ----------------------------------------------------------

    # Written once the snapshot has fully arrived. Treating "directory is not
    # empty" as "download complete" meant an interrupted download wedged the
    # backend permanently: it skipped re-downloading, then failed to load with
    # a confusing "not found locally", recoverable only by deleting the folder.
    _COMPLETE_MARKER = ".lilith-download-complete"

    def _marker_data(self) -> dict[str, str | None]:
        return {
            "repo_id": self.model_id,
            "revision": self.revision or None,
        }

    def download_if_needed(self) -> None:
        marker = self.model_path / self._COMPLETE_MARKER
        try:
            recorded = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            recorded = None
        if recorded == self._marker_data():
            return
        if self.model_path.exists() and any(self.model_path.iterdir()):
            logger.warning(
                "Model folder %s is incomplete or has a mismatched identity; "
                "resuming the configured repository/revision.", self.model_path,
            )

        from huggingface_hub import snapshot_download

        self.local_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading %s into %s", self.model_id, self.model_path)
        print(f"Downloading {self.model_id} (this happens once)...")

        kwargs = {
            "repo_id": self.model_id,
            "local_dir": str(self.model_path),
            "token": self.token,
            # A configured revision is immutable (validated in __init__). A
            # blank revision is permitted for normal models because custom
            # repository code is excluded below and never trusted at load time.
            "revision": self.revision or None,
            # Auto classes do not need repository Python for architectures
            # built into transformers. Do not even place custom modules in the
            # local snapshot where a future load path might import them.
            "ignore_patterns": [
                "*.py", "**/*.py", "*.pyc", "**/*.pyc",
                "__pycache__/*", "**/__pycache__/*",
                # PyTorch/Transformers historically used pickle-backed weight
                # formats.  A malicious pickle can execute code while loading,
                # even when trust_remote_code=False.  This backend deliberately
                # supports safetensors-only repositories.
                "*.bin", "**/*.bin", "*.pt", "**/*.pt",
                "*.pth", "**/*.pth", "*.pkl", "**/*.pkl",
                "*.pickle", "**/*.pickle", "*.ckpt", "**/*.ckpt",
            ],
        }
        # Removed in huggingface_hub >= 1.0; still required on old versions to
        # avoid symlinks, which need elevated rights on Windows.
        if "local_dir_use_symlinks" in inspect.signature(snapshot_download).parameters:
            kwargs["local_dir_use_symlinks"] = False

        snapshot_download(**kwargs)

        # Only now is the snapshot known-complete.
        try:
            marker.write_text(
                json.dumps(self._marker_data(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass  # the marker is an optimisation, not a correctness guarantee

    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.download_if_needed()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path, trust_remote_code=False, local_files_only=True
            )
        except Exception as exc:
            logger.warning("Fast tokenizer unavailable (%s); trying slow", exc)
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                use_fast=False,
                trust_remote_code=False,
                local_files_only=True,
            )

        dtype = torch.float16 if self.device == "cuda" else torch.float32
        load_kwargs = {
            "low_cpu_mem_usage": True,
            "local_files_only": True,
            # Lilith does not support executable model-repository code. Models
            # that require it fail closed instead of running it with the
            # user's permissions.
            "trust_remote_code": False,
            # Never fall back to pickle-backed pytorch_model.bin weights.
            "use_safetensors": True,
        }
        # transformers renamed torch_dtype -> dtype; support both.
        params = inspect.signature(AutoModelForCausalLM.from_pretrained).parameters
        if "dtype" in params:
            load_kwargs["dtype"] = dtype
        else:
            load_kwargs["torch_dtype"] = dtype

        self.model = AutoModelForCausalLM.from_pretrained(self.model_path, **load_kwargs)
        self.model.to(self.device)
        self.model.eval()

        logger.info("transformers backend ready on %s", self.device)
        return self.model, self.tokenizer

    # -- inference --------------------------------------------------------

    def _render(self, messages: list) -> str:
        """Turn the message list into a prompt string."""
        if isinstance(messages, str):
            return messages
        if getattr(self.tokenizer, "chat_template", None):
            return self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        # No template baked into the model: use a plain transcript.
        lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lines.append(content)
            elif role == "user":
                lines.append(f"User: {content}")
            else:
                lines.append(f"Lilith: {content}")
        return "\n".join(lines) + "\nLilith:"

    def get_response(self, messages: list) -> str:
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model must be loaded before generating a response.")

        import torch

        inputs = self.tokenizer(self._render(messages), return_tensors="pt").to(
            self.model.device
        )
        prompt_length = inputs["input_ids"].shape[-1]

        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_tokens,
                do_sample=True,
                temperature=self.temperature,
                top_p=self.top_p,
                top_k=self.top_k,
                # `or` would discard a pad_token_id of 0, which is both valid
                # and common, silently swapping in eos and corrupting padding.
                pad_token_id=(
                    self.tokenizer.pad_token_id
                    if self.tokenizer.pad_token_id is not None
                    else self.tokenizer.eos_token_id
                ),
            )

        # Decode only what the model added, not the prompt we fed it.
        generated = output[0][prompt_length:]
        return self.tokenizer.decode(generated, skip_special_tokens=True).strip()
