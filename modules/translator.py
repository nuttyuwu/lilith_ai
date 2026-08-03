"""
Optional NLLB-200 translator, applied to Lilith's replies.

Fixes over the previous version:
  * ``_SIMPLE_LANG_MAP`` was defined *below* the class that used it at call
    time -- it happened to work, but only by accident of import ordering.
    It is now defined first.
  * A stray copy of ``translate`` sat at module level taking ``self`` as its
    first argument: 60 lines of dead code that shadowed nothing and confused
    everyone reading the file. Removed, along with ~130 lines of commented-out
    earlier drafts.
  * ``tokenizer.src_lang`` is now set. Without it NLLB encodes the input with
    the wrong language tag and quality drops sharply.
  * Accepts an already-parsed config object, so it no longer re-reads
    config.ini from the current working directory.
  * Model loading failures raise a message naming the missing package rather
    than a transformers traceback.
"""

from __future__ import annotations

import logging
import re

from modules import compat

logger = logging.getLogger(__name__)

# Short code -> NLLB-200 language tag.
_SIMPLE_LANG_MAP = {
    "en": "eng_Latn",
    "ru": "rus_Cyrl",
    "uk": "ukr_Cyrl",
    "fr": "fra_Latn",
    "es": "spa_Latn",
    "de": "deu_Latn",
    "pt": "por_Latn",
    "it": "ita_Latn",
    "zh": "zho_Hans",
    "ar": "ara_Arab",
    "hi": "hin_Deva",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "mn": "khk_Cyrl",
    "tr": "tur_Latn",
    "pl": "pol_Latn",
}


class Translator:
    """Translates text while leaving bracketed/quoted spans untouched.

    Lilith's replies use *asterisks* for actions and quotes for speech; those
    delimiters must survive translation intact.
    """

    _PROTECT_PATTERN = re.compile(
        r'(\*[^*]+\*|\([^)]*\)|\[[^\]]*\]|\{[^}]*\}|\u00ab[^\u00bb]*\u00bb'
        r'|\u201c[^\u201d]*\u201d|"[^"]*"|\'[^\']*\'|`[^`]*`)',
        re.MULTILINE,
    )

    def __init__(self, config=None, config_path: str | None = None,
                 model_name: str | None = None):
        config = config if config is not None else compat.load_config(config_path)
        section = config["translator"]

        source = section.get("source_lang", "en")
        target = section.get("target_lang", "ru")
        self.source_lang = self._normalise_lang(source)
        self.target_lang = self._normalise_lang(target)
        self.model_name = model_name or section.get(
            "model_name", "facebook/nllb-200-distilled-600M"
        )

        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "The translator needs transformers, torch and sentencepiece:\n"
                "    pip install -r requirements-translate.txt"
            ) from exc

        logger.info("Loading translator %s (%s -> %s)",
                    self.model_name, self.source_lang, self.target_lang)

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        self.model.eval()

        # Tell NLLB what it is reading, not just what to write.
        try:
            self.tokenizer.src_lang = self.source_lang
        except Exception:
            logger.debug("Tokenizer does not accept src_lang; continuing")

        token_id = self.tokenizer.convert_tokens_to_ids(self.target_lang)
        unknown = getattr(self.tokenizer, "unk_token_id", None)
        self.forced_bos_token_id = (
            token_id if token_id is not None and token_id != unknown else None
        )
        if self.forced_bos_token_id is None:
            logger.warning("Tokenizer did not recognise target tag %r", self.target_lang)

    @staticmethod
    def _normalise_lang(code: str) -> str:
        code = (code or "").strip()
        if "_" in code:
            return code  # already a full NLLB tag such as eng_Latn
        if code.lower() in _SIMPLE_LANG_MAP:
            return _SIMPLE_LANG_MAP[code.lower()]
        raise ValueError(
            f"Unknown language code {code!r}. Use a full NLLB tag "
            f"(e.g. eng_Latn) or one of: {', '.join(sorted(_SIMPLE_LANG_MAP))}"
        )

    def _translate_chunk(self, text: str, max_length: int, gen_kwargs: dict) -> str:
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=max_length
        )
        outputs = self.model.generate(**inputs, **gen_kwargs)
        return self.tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]

    def translate(self, text: str, max_length: int = 512, **generate_kwargs) -> str:
        if not text or not text.strip():
            return text

        gen_kwargs = {"max_length": max_length, "num_beams": 4}
        if self.forced_bos_token_id is not None:
            gen_kwargs["forced_bos_token_id"] = self.forced_bos_token_id
        gen_kwargs.update(generate_kwargs)

        out: list[str] = []
        for part in self._PROTECT_PATTERN.split(text):
            if not part:
                continue

            protected = bool(self._PROTECT_PATTERN.fullmatch(part))
            opener = closer = ""
            body = part
            if protected:
                opener, closer, body = part[0], part[-1], part[1:-1]
                if not body.strip():
                    out.append(part)
                    continue

            match = re.match(r"^(\s*)(.*?)(\s*)$", body, re.DOTALL)
            lead, core, trail = match.groups() if match else ("", body, "")
            if not core:
                out.append(part)
                continue

            try:
                translated = self._translate_chunk(core, max_length, gen_kwargs)
            except Exception as exc:
                logger.warning("Chunk translation failed (%s); keeping original", exc)
                translated = core

            out.append(f"{opener}{lead}{translated}{trail}{closer}")

        return "".join(out)


if __name__ == "__main__":
    import sys

    try:
        translator = Translator()
    except Exception as exc:
        print(f"Could not start the translator: {exc}")
        sys.exit(1)

    sample = ('This is a test sentence with *a protected phrase*, '
              'a (bracketed part), and "quoted text".')
    print("ORIGINAL:\n" + sample)
    print("\nTRANSLATED:\n" + translator.translate(sample))
