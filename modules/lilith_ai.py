"""
Lilith's conversation brain: persona, memory, emotion, backend dispatch.

Changes in this pass, beyond the cross-platform work:

  * The prompt payload is rebuilt every turn instead of being stored. Stored
    history is now pure user/assistant turns; the system block (persona + name
    + time context) is assembled fresh. This is what makes time awareness and
    history trimming possible at all.
  * History trimming moved here from _llama_iface. It was backend-specific, so
    Ollama, LM Studio and transformers sent unbounded history and eventually
    blew their context window with no error message.
  * Emotion is driven by an explicit [state:x] tag that Lilith emits, with
    keyword matching kept only as a fallback. Guessing a mood from substrings
    was never going to be reliable.
  * The emotion keyword tables are reordered: thinking_happy and thinking_sad
    now come before happy and sad. Previously "thinking happy" contained
    "happy", so the happy branch always won and thinking_happy was dead code.
  * Replies are no longer truncated at two sentences by ``split(". ")``. That
    split also mangled "Dr. " and decimals, and cut her off mid-thought.
    Brevity is a persona instruction now.
  * Replies are checked for generic assistant voice before being stored. The
    result is diagnostic only: a stylistic second generation could replace a
    truthful identity disclosure or safety refusal, so replies are never
    rewritten by this guard.
  * ``EXISTENCE_KEYWORDS`` lives here; web_lilith.py imported it from
    lilith.py, where it never existed.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone

import modules._iface as _iface
import modules.lilith_memory as lilith_memory
from modules import companionship, compat, persona_guard, safety

logger = logging.getLogger(__name__)


class MemorySaveError(RuntimeError):
    """A generated reply could not be committed to conversation history."""


_SAVE_ERROR_MESSAGE = (
    "Your reply was generated, but conversation memory could not be saved. "
    "Check available disk space and storage permissions before trying again."
)

# Identity questions are recognized so interfaces can use a neutral thinking
# state while the model answers them honestly.
EXISTENCE_KEYWORDS = (
    "are you real", "are you human", "you are not real", "you're not real",
    "youre not real", "you aren't real", "not real", "just an ai", "just a bot",
    "you are a bot", "you're a bot", "you are ai", "you're ai", "do you exist",
    "do you actually exist", "you don't exist", "you dont exist", "fictional",
    "fake", "program", "chatbot", "language model", "what are you",
    "are you an ai", "are you ai", "are you a bot", "are you a chatbot",
    "are you software", "are you a program", "are you sentient",
    "are you conscious", "are you alive", "are you a person",
    "are you really there", "are you actually there", "do you have feelings",
    "can you feel", "are you self-aware",
)

# Matched on word boundaries, not as substrings. Bare "program" and "fake"
# are in the list above, so plain `keyword in text` fired on "I'm learning
# programming today" and made her look disappointed about it.
_EXISTENCE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in EXISTENCE_KEYWORDS) + r")\b"
)

# The emotion vocabulary. modules/lilith_display.EMOTION_FALLBACKS must be able
# to resolve every one of these; tests/test_compat.py enforces that.
VALID_STATES = (
    "idle", "smile", "happy", "playful", "cheeky", "talking", "sad",
    "dissapointed", "confused", "sleep", "thinking", "thinking_happy",
    "thinking_sad", "blinking",
)

# Lilith is asked to end her replies with [state:happy] and similar.
_STATE_TAG = re.compile(r"\[\s*state\s*[:=]\s*([a-z_]+)\s*\]", re.IGNORECASE)

# Ordered longest-phrase-first: compound states must be tested before the
# single words they contain.
EXTENDED_EMOTIONS = (
    ("thinking_happy", ("thinking happy", "positive thought", "good idea",
                        "bright idea", "optimistic", "hopeful",
                        "thinking positively")),
    ("thinking_sad", ("thinking sad", "negative thought", "bad idea",
                      "worried thought", "pessimistic", "concerned",
                      "thinking negatively")),
    ("confused", ("confused", "not sure", "don't know", "dunno", "what?",
                  "huh?", "what do you mean", "i don't understand",
                  "confusion", "puzzled")),
    ("sleep", ("sleep", "tired", "exhausted", "bed", "nap", "drowsy", "yawn",
               "fatigue", "weary", "rest", "zzz", "asleep")),
    ("playful", ("playful", "joking", "kidding", "teasing", "funny", "laugh",
                 "lol", "haha", "hehe", "joke", "wit", "humor")),
    ("happy", ("happy", "happiness", "joy", "great", "fantastic", "awesome",
               "excited", "thrilled", "overjoyed", "ecstatic", "delighted",
               "wonderful")),
    ("sad", ("sad", "sadness", "unhappy", "depressed", "miserable", "sorrow",
             "grief", "heartbroken", "melancholy", "gloomy")),
    ("smile", ("smile", "smiling", "grin", "smiled", "grinning", "beaming",
               "cheerful")),
)

BASIC_EMOTIONS = (
    ("cheeky", ("of course", "ofcourse", "certainly", "definitely",
                "absolutely", "surely", "without doubt")),
    ("sad", ("sorry", "sad", "hurt", "lonely", "pain", "apologize", "regret",
             "mourn", "grieve", "heartache", "disappointed")),
    ("smile", ("love", "warm", "smile", "happy", "glad", "joy", "cherish",
               "dear", "fond", "sweet", "adore", "bliss", "content",
               "pleased")),
    ("thinking", ("...", "heavy", "missed", "miss", "longing", "alone",
                  "quiet", "ponder", "contemplate", "reflect", "consider",
                  "meditate", "ruminate")),
)

# Below this, a gap is not worth remarking on.
MIN_GAP_SECONDS = 30 * 60

# Slack left free in the context window for chat-template scaffolding and for
# any mismatch between our token estimate and the model's real tokenizer.
CONTEXT_SAFETY_MARGIN = 256


class LilithAI:
    def __init__(
        self,
        Lilith_display=None,
        config=None,
        BASE_DIR=None,
        DEFAULT_USER_NAME: str = "",
        NO_AI: bool = False,
    ):
        self.config = config if config is not None else compat.load_config()
        self.Lilith_display = Lilith_display
        self.Lilith_mem = lilith_memory.LilithMemory(
            BASE_DIR or compat.BASE_DIR, self.config, DEFAULT_USER_NAME
        )

        self.persona = self.Lilith_mem.load_persona()
        self.memory = self.Lilith_mem.load_memory()
        self.user_name = self.Lilith_mem.get_user_name(self.memory)
        self.last_reply = ""
        self.last_state: str | None = None
        self._lock = threading.RLock()

        section = self.config["ai_config"]
        self.max_history_messages = section.getint("max_history_messages", fallback=40)
        # 0 = keep the whole reply. Brevity belongs in the persona, not in a
        # string split, so this now defaults to off.
        self.max_reply_sentences = section.getint("max_reply_sentences", fallback=0)
        self.time_awareness = section.getboolean("time_awareness", fallback=True)
        self.persona_guard = section.getboolean("persona_guard", fallback=True)
        # Used as the context budget when the backend cannot report its own.
        self.n_ctx = section.getint("n_ctx", fallback=8192)
        self.max_tokens = section.getint("max_tokens", fallback=120)

        self._ensure_conversations()
        self._gap_note = self._session_gap_note()
        self.translator = self._make_translator()

        if NO_AI:
            self.client = None
            logger.info("LilithAI started in NO_AI mode (no backend loaded)")
            return

        self.client = _iface.AIInterface(
            config=self.config,
            model=section.get("ai_model"),
            temperature=section.getfloat("temperature", fallback=0.85),
            max_tokens=section.getint("max_tokens", fallback=120),
            base_url=self.config["server"].get("base_url", ""),
            api_key=self.config["server"].get("api_key", ""),
        )
        logger.info("LilithAI initialised successfully")

    # -- optional translator ---------------------------------------------

    def _make_translator(self):
        if not self.config["translator"].getboolean("enable", fallback=False):
            return None
        try:
            from modules.translator import Translator

            logger.info("Translator enabled")
            return Translator(config=self.config)
        except Exception as exc:
            logger.warning("Translator disabled (%s)", exc)
            print(f"[translator disabled: {exc}]")
            return None

    # -- conversation storage --------------------------------------------

    def _ensure_conversations(self) -> None:
        """Bring older memory.json layouts up to the current schema."""
        changed = False

        if "conversations" not in self.memory:
            legacy = self.memory.pop("conversation", None)
            self.memory["conversations"] = {"default": legacy or []}
            if legacy:
                logger.info("Migrated legacy single-conversation memory")
            changed = True
        elif "conversation" in self.memory:
            self.memory.pop("conversation", None)
            changed = True

        conversations = self.memory.get("conversations")
        if not isinstance(conversations, dict) or not conversations:
            self.memory["conversations"] = {"default": []}
            changed = True

        # System turns used to be stored inside the history. They are rebuilt
        # every turn now, so drop the stale copies: a persisted persona would
        # otherwise be sent alongside the current one, doubling the token cost
        # and letting an edited persona.txt be silently overridden.
        for name, turns in self.memory["conversations"].items():
            if not isinstance(turns, list):
                self.memory["conversations"][name] = []
                changed = True
                continue
            cleaned = [t for t in turns
                       if isinstance(t, dict) and t.get("role") in ("user", "assistant")]
            if len(cleaned) != len(turns):
                self.memory["conversations"][name] = cleaned
                changed = True

        if self.memory.get("current_conversation") not in self.memory["conversations"]:
            self.memory["current_conversation"] = next(iter(self.memory["conversations"]))
            changed = True

        if "meta" not in self.memory:
            self.memory["meta"] = {}
            changed = True

        if changed:
            self.Lilith_mem.save_memory(self.memory)

    def _get_current_conv_list(self):
        name = self.memory.get("current_conversation", "default")
        conversations = self.memory.setdefault("conversations", {})
        return name, conversations.setdefault(name, [])

    # -- time awareness ---------------------------------------------------

    def _session_gap_note(self) -> str:
        """How long since the last stored session, phrased for the prompt.

        This is ordinary application context. It must not imply that the
        fictional character watched, waited, suffered, or needed attention
        while the program was closed.
        """
        if not self.time_awareness:
            return ""

        meta = self.memory.setdefault("meta", {})
        previous = meta.get("last_seen")
        note = ""

        if previous:
            try:
                then = datetime.fromisoformat(previous)
                if then.tzinfo is None:
                    then = then.replace(tzinfo=timezone.utc)
                seconds = (datetime.now(timezone.utc) - then).total_seconds()
                if seconds >= MIN_GAP_SECONDS:
                    note = f"They were last here {self._humanise(seconds)} ago."
            except (ValueError, TypeError):
                logger.debug("Unparseable last_seen: %r", previous)
        else:
            note = "This is the first time they have come to you."

        meta["last_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # Only persist when there is a reason to. This used to save on every
        # single start, so merely launching a second process (conv_edit, the
        # web UI) rewrote memory.json before the user had typed anything --
        # which is the cross-process clobber in its most avoidable form. The
        # timestamp still updates in memory and is written with the first reply.
        if not previous:
            self.Lilith_mem.save_memory(self.memory)
        return note

    @staticmethod
    def _humanise(seconds: float) -> str:
        minutes = seconds / 60
        if minutes < 90:
            return f"{int(minutes)} minutes"
        hours = minutes / 60
        if hours < 36:
            return f"{int(hours)} hours"
        days = hours / 24
        if days < 14:
            return f"{int(days)} days"
        weeks = days / 7
        if weeks < 9:
            return f"{int(weeks)} weeks"
        return f"{int(days / 30)} months"

    def _time_context(self) -> str:
        now = datetime.now()
        parts = [f"Right now it is {now:%A %d %B %Y, %H:%M} where they are."]
        if self._gap_note:
            parts.append(self._gap_note)
        parts.append(
            "You may notice the hour or the gap if it feels natural. "
            "Do not announce it mechanically or state the date verbatim."
        )
        return " ".join(parts)

    # -- prompt assembly --------------------------------------------------

    def _system_block(self, extra: str = "") -> str:
        block = f"{self.persona}\n\nThe person you are speaking with is called {self.user_name}."
        if self.time_awareness:
            block += f"\n\n{self._time_context()}"
        return block + extra

    def _companionship_nudge(self, prompt: str) -> str:
        """One-turn guidance when someone withdraws or leans on her too hard.

        Rate-limited on purpose. Saying this every single time somebody wants
        an evening to themselves is nagging, and a companion that nags gets
        closed -- which is the exact outcome the reminder exists to prevent.
        """
        kind = companionship.detect(prompt)
        if kind is None:
            return ""

        meta = self.memory.setdefault("meta", {})
        if not companionship.due(meta.get("last_companionship_note")):
            logger.debug("%s signal seen; reminder suppressed (too recent)", kind)
            return ""

        meta["last_companionship_note"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        logger.info("Companionship reminder issued (%s)", kind)
        return companionship.guidance_for(kind)

    def _trim_history(self, history: list) -> list:
        if self.max_history_messages <= 0:
            return history
        return history[-self.max_history_messages:]

    def _backend_call(self, name: str, *args):
        """Call an optional backend capability. None when it is absent.

        Backends are duck-typed here -- the HTTP ones own no tokenizer, and
        NO_AI mode has no client at all -- so never assume the method exists.
        """
        method = getattr(self.client, name, None) if self.client is not None else None
        if not callable(method):
            return None
        try:
            return method(*args)
        except Exception:
            return None

    def _count_tokens(self, text: str) -> int:
        """Token cost of a string, exactly if the backend can, else estimated."""
        counted = self._backend_call("count_tokens", text)
        if isinstance(counted, int) and counted >= 0:
            return counted
        # ~4 chars/token is the English rule of thumb; divide by 3 instead so
        # the estimate runs high and we under-fill rather than overflow.
        return max(1, len(text) // 3)

    def _fit_history(self, history: list, system_text: str, prompt: str) -> list:
        """Drop the oldest turns until the payload fits the context window.

        Trimming by message count alone was not enough: the persona is a fixed
        cost of thousands of tokens that is never trimmed, so once persona +
        history crossed n_ctx every single turn failed, permanently, with a
        raw 'Requested tokens exceed context window' error.
        """
        history = self._trim_history(history)

        limit = self._backend_call("context_limit")
        limit = int(limit) if isinstance(limit, int) and limit > 0 else self.n_ctx
        # Leave room for the reply itself plus the template's own scaffolding.
        room = limit - self.max_tokens - CONTEXT_SAFETY_MARGIN
        room -= self._count_tokens(system_text) + self._count_tokens(prompt)

        if room <= 0:
            logger.warning(
                "Persona and prompt alone fill the %s-token context window; "
                "sending no history. Raise [ai_config] n_ctx or shorten the "
                "persona.", limit,
            )
            return []

        kept: list = []
        used = 0
        for message in reversed(history):
            # +4 covers the per-message role/delimiter tokens every chat
            # template adds around the content.
            cost = self._count_tokens(message.get("content", "")) + 4
            if used + cost > room:
                break
            kept.append(message)
            used += cost
        kept.reverse()

        # Never open on an assistant turn: strict-alternation templates
        # (Gemma, Mistral) reject a history that does not start with the user.
        while kept and kept[0].get("role") != "user":
            kept.pop(0)

        dropped = len(history) - len(kept)
        if dropped:
            logger.info("Dropped %s old turn(s) to fit the context window", dropped)
        return kept

    def _build_payload(self, history: list, prompt: str, extra: str = "") -> list:
        """Assemble the full message list sent to the backend."""
        system_text = self._system_block(extra)
        return (
            [{"role": "system", "content": system_text}]
            + self._fit_history(history, system_text, prompt)
            + [{"role": "user", "content": prompt}]
        )

    # -- reply post-processing --------------------------------------------

    def _extract_state(self, reply: str) -> tuple[str, str | None]:
        """Pull a [state:x] tag out of the reply and strip it from the text."""
        state = None
        for match in _STATE_TAG.finditer(reply):
            candidate = match.group(1).lower()
            if candidate in VALID_STATES:
                state = candidate
            else:
                logger.debug("Unknown state tag %r ignored", candidate)
        cleaned = _STATE_TAG.sub("", reply).strip()
        # A tag on its own line leaves a dangling blank line behind.
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned, state

    def _shorten(self, reply: str) -> str:
        if self.max_reply_sentences <= 0:
            return reply
        parts = re.split(r"(?<=[.!?~\u2026])\s+", reply)
        return " ".join(parts[: self.max_reply_sentences]).strip()

    # -- replying ---------------------------------------------------------

    def lilith_reply(self, prompt: str) -> str:
        # This runs before backend generation, persona diagnostics, and translation.
        # A prompt-only safety rule could be ignored or rewritten by any of
        # those layers; the fixed response is therefore selected in code.
        fixed_safety_reply = safety.crisis_response(prompt)

        if fixed_safety_reply is not None:
            # Do not wait behind a slow/hung model request, and do not make
            # crisis resources conditional on writable storage. Crisis turns
            # are intentionally not persisted; this is both the fastest path
            # and avoids retaining especially sensitive text by default.
            logger.warning("Deterministic crisis response selected")
            self.last_reply = fixed_safety_reply
            self.last_state = "thinking_sad"
            return fixed_safety_reply

        if self.client is None:
            logger.error("lilith_reply called in NO_AI mode")
            return "..."

        with self._lock:
            conv_name, history = self._get_current_conv_list()
            payload = self._build_payload(
                history, prompt, self._companionship_nudge(prompt)
            )
            raw = self._ask(payload)

            # Detect generic service voice for local diagnostics, but never
            # replace a model reply with a second generation. A style retry
            # cannot reliably distinguish a harmless phrase from a truthful
            # identity disclosure, capability limit, or safety refusal.
            if self.persona_guard:
                leak = persona_guard.find_leak(raw)
                if leak:
                    logger.info(
                        "Generic assistant phrasing detected (%r); preserving reply",
                        leak,
                    )

            reply, state = self._extract_state(raw)
            reply = self._shorten(reply.strip()) or "..."

            if self.translator is not None:
                try:
                    reply = self.translator.translate(reply)
                except Exception as exc:
                    logger.warning("Translation failed: %s", exc)

            new_turns = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": reply},
            ]
            history.extend(new_turns)
            self.memory["conversations"][conv_name] = history
            if not self.Lilith_mem.save_memory(self.memory):
                # The reply is not shown, so do not leave an unseen exchange
                # in the live context. A later successful turn must not make
                # Lilith appear to remember words the user never received.
                del history[-len(new_turns):]
                logger.error("Reply discarded because conversation memory was not saved")
                raise MemorySaveError(_SAVE_ERROR_MESSAGE)

            self.last_reply = reply
            self.last_state = state
            return reply

    def _ask(self, payload: list) -> str:
        try:
            return (self.client.get_response(payload) or "").strip()
        except Exception:
            logger.exception("Backend call failed")
            raise

    # -- conversation management -----------------------------------------

    def create_conversation(self, name: str, switch_to: bool = True) -> bool:
        name = (name or "").strip()
        if not name:
            return False
        with self._lock:
            conversations = self.memory.setdefault("conversations", {})
            if name in conversations:
                return False
            conversations[name] = []
            if switch_to:
                self.memory["current_conversation"] = name
            self.Lilith_mem.save_memory(self.memory)
            return True

    def list_conversations(self) -> list[str]:
        return list(self.memory.get("conversations", {}).keys())

    def switch_conversation(self, name: str, create_if_missing: bool = False) -> bool:
        with self._lock:
            conversations = self.memory.setdefault("conversations", {})
            if name not in conversations:
                if not create_if_missing:
                    return False
                conversations[name] = []
            self.memory["current_conversation"] = name
            self.Lilith_mem.save_memory(self.memory)
            return True

    def delete_conversation(self, name: str) -> bool:
        with self._lock:
            conversations = self.memory.get("conversations", {})
            if name not in conversations or len(conversations) == 1:
                if name in conversations:
                    logger.warning("Refusing to delete the last conversation")
                return False
            del conversations[name]
            if self.memory.get("current_conversation") == name:
                self.memory["current_conversation"] = next(iter(conversations))
            self.Lilith_mem.save_memory(self.memory)
            return True

    def clear_conversation(self, name: str | None = None) -> int:
        """Empty a room's history, keeping the room. Returns turns removed."""
        with self._lock:
            target = name or self.get_current_conversation_name()
            conversations = self.memory.setdefault("conversations", {})
            removed = len(conversations.get(target) or [])
            conversations[target] = []
            self.Lilith_mem.save_memory(self.memory)
            return removed

    def get_current_conversation_name(self) -> str:
        return self.memory.get("current_conversation", "default")

    def get_history(self, limit: int = 20) -> list[dict]:
        """Recent turns of the active conversation, for the web UI."""
        _, history = self._get_current_conv_list()
        return history[-limit:] if limit else list(history)

    # -- user name --------------------------------------------------------

    def set_user_name(self, name: str) -> None:
        with self._lock:
            self.Lilith_mem.set_user_name(self.memory, name)
            self.user_name = self.Lilith_mem.get_user_name(self.memory)

    def get_user_name(self) -> str:
        return self.Lilith_mem.get_user_name(self.memory)

    def has_user_name(self) -> bool:
        return bool(self.memory.get("meta", {}).get("user_name_set", False))

    # -- emotion ----------------------------------------------------------

    def get_current_emotion(self, extended_emotions: bool = False) -> str:
        """Prefer the state Lilith declared; fall back to keyword matching."""
        if self.last_state:
            return self.last_state

        text = (self.last_reply or "").lower()
        table = EXTENDED_EMOTIONS if extended_emotions else BASIC_EMOTIONS
        for emotion, words in table:
            if any(word in text for word in words):
                return emotion
        return "idle" if extended_emotions else "talking"

    @staticmethod
    def is_existence_question(text: str) -> bool:
        return bool(_EXISTENCE_RE.search((text or "").lower()))
