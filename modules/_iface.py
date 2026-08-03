"""
Backend dispatcher.

Picks one of the four AI backends based on ``[server] server_ai`` and hides
the differences behind a single ``get_response(messages)`` call.

Two things changed for cross-platform support:
  * The config is no longer read from the current working directory at import
    time -- that made the app only runnable from the project root.
  * A missing optional dependency now produces an actionable message naming
    the exact install command for the current OS, instead of a bare
    ImportError from deep inside a submodule.
"""

from __future__ import annotations

import importlib
import logging

from modules import compat

logger = logging.getLogger(__name__)

# server_ai value -> (module, class, human name, pip package)
BACKENDS: dict[str, tuple[str, str, str, str]] = {
    "ollama": ("modules._ollama_iface", "AIInterface_Ollama", "Ollama", "ollama"),
    "lm studio": ("modules._openai_iface", "AIInterface_OpenAI", "LM Studio", "openai"),
    "openai": ("modules._openai_iface", "AIInterface_OpenAI", "OpenAI API", "openai"),
    "hf": ("modules._hf_iface", "AIInterface_HF", "HuggingFace transformers", "transformers torch huggingface_hub"),
    "llama": ("modules._llama_iface", "AIInterface_Llama", "llama.cpp", "llama-cpp-python"),
}


def normalise_backend(name: str) -> str:
    """Accept 'LM studio', 'lm_studio', 'LMStudio' and friends as one value."""
    cleaned = (name or "").strip().lower().replace("_", " ").replace("-", " ")
    cleaned = " ".join(cleaned.split())
    if cleaned in {"lmstudio", "lm studio"}:
        return "lm studio"
    return cleaned


class BackendUnavailable(RuntimeError):
    """Raised when the selected backend's dependency is not installed."""


def _install_hint(package: str) -> str:
    exe = "python" if compat.IS_WINDOWS else "python3"
    extra = ""
    if package == "llama-cpp-python" and compat.IS_WINDOWS:
        extra = (
            "\n  On Windows this needs prebuilt wheels; try:\n"
            "    pip install llama-cpp-python "
            "--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu\n"
            "  or install the 'Desktop development with C++' workload from the "
            "Visual Studio Build Tools."
        )
    return f"  {exe} -m pip install {package}{extra}"


class AIInterface:
    """Uniform wrapper over whichever backend the config selected."""

    def __init__(self, config=None, **kwargs):
        self.config = config if config is not None else compat.load_config()
        raw = self.config["server"].get("server_ai", "ollama")
        self.backend = normalise_backend(raw)

        if self.backend not in BACKENDS:
            supported = ", ".join(sorted(BACKENDS))
            raise ValueError(
                f"Unsupported [server] server_ai = {raw!r} in config.ini. "
                f"Supported values: {supported}."
            )

        module_name, class_name, label, package = BACKENDS[self.backend]
        logger.info("Loading AI backend: %s (%s)", label, module_name)

        # Every backend defers its heavy third-party import into __init__ or
        # load() so that merely picking a backend does not pay for torch. That
        # means importing the wrapper module can never fail, and guarding only
        # import_module left this hint unreachable: a missing llama_cpp
        # surfaced as a bare ModuleNotFoundError from inside the submodule,
        # with none of the Windows wheel advice below. Cover the whole chain.
        try:
            module = importlib.import_module(module_name)
            self.imp = getattr(module, class_name)(config=self.config, **kwargs)
            # transformers needs an explicit load step; the others load lazily.
            if hasattr(self.imp, "load"):
                self.imp.load()
        except ImportError as exc:
            missing = getattr(exc, "name", None) or package
            raise BackendUnavailable(
                f"The {label} backend needs a package that is not installed "
                f"({missing}).\n{_install_hint(package)}\n"
                f"Or choose a different backend with: python lilith.py edit"
            ) from exc

    def get_response(self, messages: list) -> str:
        response = self.imp.get_response(messages)
        return response if isinstance(response, str) else ""

    def count_tokens(self, text: str):
        """Exact token count, or None when the backend cannot say.

        Only the local backends own a tokenizer; the HTTP ones would have to
        guess, so they return None and LilithAI falls back to an estimate.
        """
        counter = getattr(self.imp, "count_tokens", None)
        if counter is None:
            return None
        try:
            return counter(text)
        except Exception:
            return None

    def context_limit(self) -> int:
        """The backend's context window in tokens, or 0 when unknown."""
        try:
            return int(getattr(self.imp, "context_limit", 0) or 0)
        except Exception:
            return 0
