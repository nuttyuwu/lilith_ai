"""
First-run setup.

An adult fictional-roleplay and privacy disclosure, followed by three setup
questions before anything heavy loads: what to call you, which scene Lilith
appears in, and whether the offline model runs on the GPU or the CPU. Everything
else keeps its default and can be changed later with ``python lilith.py edit``.

Why these three specifically:

  * The name was already asked, but inside ``chat_loop`` -- after the portrait
    window had opened and the model had finished loading. On a CPU-only 8B that
    is a minute of staring at nothing before the first question.
  * ``place`` decides which art set loads, and the two sets have genuinely
    different expressions. Discovering it exists required reading config.ini.
  * ``n_gpu_layers`` defaults to 0, so every fresh clone ran entirely on the CPU
    no matter what hardware it was on. That is the safe default -- offloading
    more layers than the card has memory for fails deep inside llama.cpp -- but
    nobody could reasonably be expected to guess it was there.

Deliberately plain ``input()`` rather than a curses screen. This runs before
anything else, on a machine where ``windows-curses`` may well not be installed
yet, and a setup wizard that cannot start is worse than no wizard at all.
``_tui.ask_choice`` is the same numbered-menu fallback the other screens use.
"""

from __future__ import annotations

import copy
import logging
import sys

from modules import _tui, compat, lilith_memory, safety, theme

logger = logging.getLogger(__name__)

# llama.cpp clamps this to the model's real layer count, so "all of them"
# needs no knowledge of the architecture. -1 also means "all" in current
# builds, but it meant "none" in older ones -- this is the unambiguous spelling.
GPU_LAYERS_ALL = 999
SAFETY_CONSENT_VERSION = str(safety.DISCLOSURE_VERSION)

PLACES = ("room", "glass")

_PLACE_LABELS = (
    "room   -- an apartment interior, ten expressions, the fuller set",
    "glass  -- a closer, quieter framing, eight expressions",
)

_COMPUTE_LABELS = (
    "GPU -- much faster, if llama.cpp was built for your card",
    "CPU -- works on anything, but slow on a large model",
)


def _say(text: str, colour: str = "lilith") -> None:
    print(theme.paint(compat.safe_text(text), colour))


def _quiet(text: str) -> None:
    print(theme.paint(compat.safe_text(text), "muted", faint=True))


def _ask_name(current: str) -> str | None:
    """None when the user gave up (Ctrl+C / EOF)."""
    while True:
        _say('Lilith tilts her head. "what should i call you?"')
        if current:
            _quiet(f"  (blank keeps '{current}')")
        try:
            entered = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if entered:
            # Matches the cap the web UI applies at /nickname.
            return entered[:64]
        if current:
            return current
        _quiet("  ...she waits. give her a name to hold onto.")


def _has_current_consent(config) -> bool:
    return config["safety"].get("consent_version", "0").strip() == SAFETY_CONSENT_VERSION


def _ask_safety_consent() -> bool:
    """Require an explicit adult opt-in before collecting setup answers."""
    _say("Before Lilith starts, please read this safety notice.", "problem")
    _quiet("  Lilith is fictional AI roleplay for adults (18+), not a person.")
    _quiet("  It may explore intense parasocial or tulpa themes as fiction.")
    _quiet("  She is not mental-health care or a substitute for professional support.")
    _quiet("  Names and conversations are stored locally as unencrypted plain text.")
    _quiet("  Your configured model backend may also receive what you type.")
    try:
        answer = input("  Type I AGREE to confirm you are 18+ and consent: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if answer.casefold() != "i agree":
        _quiet("  Consent was not recorded. Lilith will not start.")
        return False
    return True


def run_setup(config, memory_store=None, memory=None) -> bool:
    """Ask for safety consent and the three setup answers, then save.

    No consent or setup answers are written while questions are being answered.
    (The general config loader may already have created config.ini from its
    template.) The two destination files are each replaced atomically; if the
    second write fails, the first is rolled back on a best-effort basis because
    two files cannot form one filesystem transaction.
    """
    heart = compat.sym("heart")
    print()
    if not _ask_safety_consent():
        return False

    store = memory_store or lilith_memory.LilithMemory(compat.BASE_DIR, config)
    memory = memory if memory is not None else store.load_memory()

    print()
    _say(f"{heart} Setting Lilith up. Three questions, then she's yours.")
    _quiet("  Change any of it later with:  python lilith.py edit")
    print()

    name = _ask_name(store.get_user_name(memory))
    if name is None:
        return False

    print()
    place_index = _tui.ask_choice(
        "Where should she appear?", list(_PLACE_LABELS), allow_blank=False
    )
    if place_index is None:
        return False
    place = PLACES[place_index]

    print()
    _quiet("The offline model can run on your graphics card or your processor.")
    _quiet("This only affects the 'llama' backend -- Ollama and LM Studio")
    _quiet("manage their own hardware, so leave it on CPU if you use those.")
    compute_index = _tui.ask_choice(
        "How should the offline model run?", list(_COMPUTE_LABELS), allow_blank=False
    )
    if compute_index is None:
        return False
    use_gpu = compute_index == 0

    # Everything answered -- now commit. Keep enough state to undo the memory
    # write if config.ini cannot be replaced afterward.
    original_memory = copy.deepcopy(memory)
    memory_file_existed = store.MEMORY_FILE.exists()
    original_config = {
        "place": config["lilith_display"].get("place", "room"),
        "n_gpu_layers": config["ai_config"].get("n_gpu_layers", "0"),
        "setup_complete": config["setup"].get("complete", "false"),
        "consent_version": config["safety"].get("consent_version", "0"),
    }
    memory.setdefault("meta", {})
    memory["meta"]["user_name"] = name.strip()
    memory["meta"]["user_name_set"] = True
    if not store.save_memory(memory):
        memory.clear()
        memory.update(original_memory)
        _quiet("  Could not save memory.json. No configuration was changed.")
        return False

    config["lilith_display"]["place"] = place
    config["ai_config"]["n_gpu_layers"] = str(GPU_LAYERS_ALL if use_gpu else 0)
    config["safety"]["consent_version"] = SAFETY_CONSENT_VERSION
    mark_complete(config, save=False)
    try:
        compat.save_config(config)
    except (OSError, KeyboardInterrupt) as exc:
        config["lilith_display"]["place"] = original_config["place"]
        config["ai_config"]["n_gpu_layers"] = original_config["n_gpu_layers"]
        config["setup"]["complete"] = original_config["setup_complete"]
        config["safety"]["consent_version"] = original_config["consent_version"]
        memory.clear()
        memory.update(original_memory)
        if memory_file_existed:
            rolled_back = store.save_memory(memory)
        else:
            try:
                store.MEMORY_FILE.unlink(missing_ok=True)
                rolled_back = True
            except OSError:
                rolled_back = False
        logger.error("Could not save setup configuration: %s", exc)
        if rolled_back:
            _quiet("  Could not save config.ini; the memory change was rolled back.")
        else:
            _quiet("  Could not save config.ini or roll memory.json back. Check both files.")
        return False

    logger.info("First-run setup: place=%s n_gpu_layers=%s",
                place, config["ai_config"]["n_gpu_layers"])

    print()
    _say(f"{heart} Thank you, {name}. She'll remember.")
    if use_gpu:
        _quiet("  If she fails to start with a memory error, your card cannot hold")
        _quiet("  the whole model -- lower [ai_config] n_gpu_layers, or pick CPU.")
    print()
    return True


def mark_complete(config, save: bool = True) -> None:
    if not config.has_section("setup"):
        config.add_section("setup")
    config["setup"]["complete"] = "true"
    if save:
        compat.save_config(config)


def needs_setup(config, has_user_name: bool) -> bool:
    """Whether the wizard should run.

    Current safety consent is always required. Once it exists, an install that
    already knows the user's name can still be grandfathered past the older
    three-question setup flag.
    """
    if not _has_current_consent(config):
        return True
    if config["setup"].getboolean("complete", fallback=False):
        return False
    return not has_user_name


def maybe_run(config, force: bool = False) -> bool:
    """Entry point for lilith.py. False only when the user cancelled setup."""
    # Piped stdin, a cron job, CI: never treat the absence of an interactive
    # terminal as consent. Existing installs with current consent may still use
    # non-interactive entry points.
    if not force and not sys.stdin.isatty():
        if _has_current_consent(config):
            return True
        print(
            "Lilith requires interactive 18+ safety consent. "
            "Run: python lilith.py setup",
            file=sys.stderr,
        )
        return False

    store = lilith_memory.LilithMemory(compat.BASE_DIR, config)
    memory = store.load_memory()
    has_name = bool(memory.get("meta", {}).get("user_name_set"))

    if not force:
        if not needs_setup(config, has_name):
            if has_name and not config["setup"].getboolean("complete", fallback=False):
                mark_complete(config)
            return True

    return run_setup(config, store, memory)
