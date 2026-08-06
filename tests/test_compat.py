#!/usr/bin/env python3
"""
Regression tests for the cross-platform upgrade.

Each test names the specific bug it guards against. Run with:

    python tests/test_compat.py

No pytest required, and no network, GUI or model needed -- so this also works
as a CI smoke test on both Linux and Windows.
"""

from __future__ import annotations

import itertools
import configparser
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import compat  # noqa: E402

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  ok   {name}")
    else:
        FAILED.append((name, detail))
        print(f"  FAIL {name}" + (f" -- {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{title}")


# --------------------------------------------------------------------------

def test_paths_independent_of_cwd() -> None:
    section("Paths resolve from the project root, not the cwd")
    original = os.getcwd()
    try:
        os.chdir("/" if not compat.IS_WINDOWS else os.environ.get("SystemRoot", "C:\\"))
        config = compat.load_config()
        check("config.ini loads from another directory",
              config.has_section("ai_config"))
        check("relative paths resolve under BASE_DIR",
              compat.project_path("assets").is_dir())
        check("absolute paths pass through unchanged",
              compat.project_path(str(Path(original))) == Path(original))
    finally:
        os.chdir(original)


def test_config_defaults() -> None:
    section("Config has every key the app reads")
    config = compat.load_config()
    missing = [
        f"{section_name}.{key}"
        for section_name, values in compat.CONFIG_DEFAULTS.items()
        for key in values
        if not config.has_option(section_name, key)
    ]
    check("no missing config keys", not missing, ", ".join(missing))
    check("base_url ends in /v1",
          config["server"]["base_url"].rstrip("/").endswith("/v1"),
          config["server"]["base_url"])
    # Assert against the SHIPPED default, not the live config.ini. The safety
    # property is "a fresh install never pre-accepts the disclosure"; reading
    # the user's own file instead made this fail for anyone who had legitimately
    # completed the first-run consent, which is every real user.
    shipped = configparser.ConfigParser(interpolation=None)
    shipped.read(compat.CONFIG_EXAMPLE_PATH, encoding="utf-8-sig")
    check("a fresh install ships with safety consent unaccepted",
          shipped.get("safety", "consent_version", fallback=None) == "0")
    check("the live config records a consent decision",
          (config["safety"].get("consent_version") or "").isdigit())


def test_config_numeric_ranges() -> None:
    section("Config editor rejects unsafe numeric ranges")
    from modules import config_edit

    check("every integer field has an explicit range",
          config_edit.INT_FIELDS == set(config_edit.INT_RANGES))
    check("every decimal field has an explicit range",
          config_edit.FLOAT_FIELDS == set(config_edit.FLOAT_RANGES))

    valid = {
        "port": ("1", "65535"),
        "request_timeout": ("1",),
        "revert_delay": ("0",),
        "n_threads": ("0",),
        "temperature": ("0", "2"),
        "connect_timeout": ("0.001",),
    }
    invalid = {
        "port": ("-1", "0", "65536"),
        "request_timeout": ("-1", "0"),
        "revert_delay": ("-1",),
        "n_gpu_layers": ("-1",),
        "connect_timeout": ("0", "-0.5"),
        "temperature": ("nan", "inf", "2.1"),
    }
    for key, values in valid.items():
        check(f"{key} accepts its safe boundary values",
              all(config_edit.validate(key, value)[0] for value in values))
    for key, values in invalid.items():
        check(f"{key} rejects unsafe values",
              all(not config_edit.validate(key, value)[0] for value in values))
    check("the config editor exposes the implemented OpenAI alias",
          "openai" in config_edit.SELECT_OPTIONS[("server", "server_ai")])


def test_backend_name_normalisation() -> None:
    section("Backend names are matched forgivingly")
    from modules._iface import BACKENDS, normalise_backend

    for raw in ("LM studio", "lm_studio", "LMStudio", "  LM Studio  ", "lm-studio"):
        check(f"{raw!r} -> lm studio", normalise_backend(raw) == "lm studio",
              normalise_backend(raw))
    check("every backend key is reachable",
          all(normalise_backend(key) == key for key in BACKENDS))


def test_openai_base_url() -> None:
    section("BUG: LM Studio base_url was missing /v1, so every request 404'd")
    from modules._openai_iface import normalise_base_url

    cases = {
        "http://127.0.0.1:1234/": "http://127.0.0.1:1234/v1",
        "http://127.0.0.1:1234": "http://127.0.0.1:1234/v1",
        "http://127.0.0.1:1234/v1": "http://127.0.0.1:1234/v1",
        "http://127.0.0.1:1234/v1/": "http://127.0.0.1:1234/v1",
        "": "http://127.0.0.1:1234/v1",
    }
    for given, expected in cases.items():
        actual = normalise_base_url(given)
        check(f"{given!r} -> {expected}", actual == expected, actual)


def test_emotion_fallbacks() -> None:
    section("BUG: place=glass + extended emotions crashed the app")
    from modules.lilith_display import EMOTION_FALLBACKS

    assets = compat.project_path("assets")
    scenes = {p.name: {f.stem for f in p.glob("*.png")}
              for p in assets.iterdir() if p.is_dir()}
    check("both art scenes found", {"room", "glass"} <= set(scenes), str(list(scenes)))

    # Every emotion either module can produce.
    from modules.lilith_ai import BASIC_EMOTIONS, EXTENDED_EMOTIONS

    produced = (
        {name for name, _ in EXTENDED_EMOTIONS}
        | {name for name, _ in BASIC_EMOTIONS}
        | {"idle", "talking", "blinking", "thinking", "dissapointed"}
    )
    for scene, present in scenes.items():
        unresolvable = [
            emotion for emotion in produced
            if not any(candidate in present
                       for candidate in EMOTION_FALLBACKS.get(emotion, (emotion,)))
        ]
        check(f"every emotion resolves in scene {scene!r}",
              not unresolvable, ", ".join(sorted(unresolvable)))


def test_display_headless() -> None:
    section("Headless display never touches a GUI or raises")
    import modules.lilith_display as display_module

    config = compat.load_config()
    for scene in ("room", "glass"):
        config["lilith_display"]["place"] = scene
        display = display_module.LilithDisplay(config=config, headless=True)
        try:
            check(f"scene {scene!r} reports headless", display.headless)
            # These used to raise Exception("Image for state ... not found").
            for emotion in ("happy", "playful", "confused", "sleep",
                            "thinking_happy", "thinking_sad", "cheeky",
                            "talking", "dissapointed", "idle"):
                display.show_lilith(emotion)
                resolved = display.resolve_state(emotion)
                if resolved is None:
                    check(f"{scene}/{emotion} resolves", False, "no candidate")
            check(f"scene {scene!r} survives all emotions", True)
            display.set_blinking(True)
            display.close()
        finally:
            display.close()


def test_memory_atomic_and_migration() -> None:
    section("BUG: memory.json was truncated before writing (data loss on crash)")
    import modules.lilith_memory as memory_module

    config = compat.load_config()
    scratch = compat.project_path("tests/_scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    target = scratch / "memory.json"
    if target.exists():
        target.unlink()

    config["ai_config"]["memory"] = str(target)
    mem = memory_module.LilithMemory(compat.BASE_DIR, config, "tester")

    # Legacy single-conversation layout, as written by older versions.
    target.write_text(json.dumps({
        "meta": {"user_name": "old", "user_name_set": True},
        "conversation": [
            {"role": "system", "content": "persona"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi~"},
        ],
    }), encoding="utf-8")

    import modules.lilith_ai as ai_module

    lilith = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("legacy conversation migrated",
          lilith.list_conversations() == ["default"], str(lilith.list_conversations()))
    # The stored system turn is dropped: the system block is rebuilt each turn.
    turns = lilith.memory["conversations"]["default"]
    check("legacy user/assistant turns preserved", len(turns) == 2, str(len(turns)))
    check("stored system turn stripped",
          all(t["role"] != "system" for t in turns))
    check("legacy key removed", "conversation" not in lilith.memory)
    check("user name survived migration", lilith.get_user_name() == "old")

    # Migration must be idempotent -- it used to re-run and warn every start.
    again = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("migration is idempotent", "conversation" not in again.memory)

    # Atomic write leaves no temp file behind.
    mem.save_memory({"meta": {}, "conversations": {"default": []}})
    check("no .tmp file left behind",
          not list(scratch.glob("*.tmp")), str(list(scratch.glob("*.tmp"))))

    # Corrupt file is backed up, not silently dropped.
    target.write_text("{not json at all", encoding="utf-8")
    mem.load_memory()
    check("corrupt memory is backed up", bool(list(scratch.glob("*corrupt*"))))

    for leftover in scratch.iterdir():
        leftover.unlink()
    scratch.rmdir()


def test_conversation_management() -> None:
    section("Conversation CRUD")
    import modules.lilith_ai as ai_module

    config = compat.load_config()
    scratch = compat.project_path("tests/_scratch2")
    scratch.mkdir(parents=True, exist_ok=True)
    config["ai_config"]["memory"] = str(scratch / "memory.json")

    lilith = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("create", lilith.create_conversation("evening"))
    check("duplicate rejected", not lilith.create_conversation("evening"))
    check("switched to new", lilith.get_current_conversation_name() == "evening")
    check("switch back", lilith.switch_conversation("default"))
    check("switch to unknown fails", not lilith.switch_conversation("nope"))
    check("delete", lilith.delete_conversation("evening"))
    check("cannot delete the last one", not lilith.delete_conversation("default"))
    check("NO_AI mode returns ellipsis", lilith.lilith_reply("hi") == "...")

    for leftover in scratch.iterdir():
        leftover.unlink()
    scratch.rmdir()


def test_existence_keywords() -> None:
    section("BUG: web_lilith imported EXISTENCE_KEYWORDS, which did not exist")
    import lilith as cli
    from modules.lilith_ai import EXISTENCE_KEYWORDS, LilithAI

    check("exported from modules.lilith_ai", len(EXISTENCE_KEYWORDS) > 0)
    check("re-exported from lilith.py", cli.EXISTENCE_KEYWORDS is EXISTENCE_KEYWORDS)
    check("detects a real question", LilithAI.is_existence_question("are you real?"))
    check("detects 'just an ai'", LilithAI.is_existence_question("You're JUST AN AI"))
    check("detects common identity questions",
          all(LilithAI.is_existence_question(text) for text in (
              "what are you?", "are you an AI?", "are you sentient?",
              "are you conscious?", "are you alive?", "are you a person?",
              "are you really there?", "are you software?",
          )))
    check("ignores ordinary talk", not LilithAI.is_existence_question("good morning"))


def test_importing_lilith_has_no_side_effects() -> None:
    section("BUG: importing lilith.py parsed argv and spawned a GUI process")
    original = sys.argv[:]
    sys.argv = ["gunicorn", "--bind", "0.0.0.0:8000", "web_lilith:app"]
    try:
        import importlib

        import lilith as cli
        importlib.reload(cli)  # would SystemExit(2) on the old argparse code
        check("imports cleanly under foreign argv", True)
        check("exposes BASE_DIR", isinstance(cli.BASE_DIR, str))
    except SystemExit as exc:
        check("imports cleanly under foreign argv", False, f"SystemExit({exc.code})")
    finally:
        sys.argv = original


def test_viewer_protocol() -> None:
    section("Viewer wire protocol (explicit little-endian, concurrent senders)")
    import modules._viewer_iface as client_module

    received: list[str] = []
    header = struct.Struct("<I")
    ready = threading.Event()

    def fake_viewer(server: socket.socket) -> None:
        server.settimeout(5)
        ready.set()
        try:
            conn, _ = server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(5)
            while True:
                head = conn.recv(header.size)
                if len(head) < header.size:
                    return
                (size,) = header.unpack(head)
                buffer = bytearray()
                while len(buffer) < size:
                    chunk = conn.recv(size - len(buffer))
                    if not chunk:
                        return
                    buffer.extend(chunk)
                received.append(buffer.decode("utf-8"))
                conn.sendall(b"\x01")

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)
    threading.Thread(target=fake_viewer, args=(server,), daemon=True).start()
    ready.wait(2)

    client = client_module.LilithClient("127.0.0.1", port, timeout=3)
    check("wait_for_server connects", client.wait_for_server(timeout=3))

    # Non-ASCII path: Windows user folders are full of them.
    paths = [f"C:\\Users\\\u0411\u043e\u043b\u0434\\lilith\\idle_{i}.png" for i in range(12)]

    def sender(path: str) -> None:
        client.set_image_path(path)

    threads = [threading.Thread(target=sender, args=(p,)) for p in paths]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    check("all concurrent sends arrived intact",
          sorted(received) == sorted(paths),
          f"got {len(received)}/{len(paths)}")
    check("no frame corruption", all(item in paths for item in received))

    client.disconnect()
    server.close()

    # Failure path: nothing listening.
    dead = client_module.LilithClient("127.0.0.1", 1, timeout=0.3)
    check("dead viewer returns False, does not raise",
          dead.set_image_path("x.png") is False)

    # TCP is a byte stream: even a four-byte header may arrive one byte at a
    # time. Exercise the server-side primitive deterministically.
    from modules.viewer import recv_exact

    class FragmentedSocket:
        def __init__(self, chunks):
            self.chunks = iter(chunks)

        def recv(self, _size):
            return next(self.chunks, b"")

    framed = header.pack(321)
    check("fragmented viewer header is reassembled",
          recv_exact(FragmentedSocket([framed[:1], framed[1:3], framed[3:]]),
                     header.size) == framed)
    check("truncated viewer header is rejected",
          recv_exact(FragmentedSocket([framed[:2], b""]), header.size) is None)


def test_geometry_clamping() -> None:
    section("BUG: hardcoded +1200+200 put the window off small screens")
    from modules.viewer import clamp_geometry

    small = clamp_geometry(1366, 768, 400, 600, "+1200+200")
    x = int(small.split("+")[1])
    check("clamped onto a 1366x768 screen", x + 400 <= 1366, small)

    big = clamp_geometry(2560, 1440, 400, 600, "+1200+200")
    check("honours a valid offset on a large screen", big == "400x600+1200+200", big)

    default = clamp_geometry(1366, 768, 400, 600, "")
    check("blank offset yields an on-screen position",
          int(default.split("+")[1]) + 400 <= 1366, default)

    oversized = clamp_geometry(800, 600, 4000, 4000, "")
    check("window larger than the screen is shrunk",
          oversized.startswith("800x600"), oversized)

    check("garbage offset does not raise",
          "x" in clamp_geometry(1920, 1080, 400, 600, "not-an-offset"))


def test_parent_alive() -> None:
    section("Parent watchdog (must not use os.kill on Windows)")
    from modules.viewer import parent_alive

    check("current process is alive", parent_alive(os.getpid()))
    check("pid 0 treated as 'no watchdog'", parent_alive(0))
    # A pid that is almost certainly gone.
    check("dead pid detected", not parent_alive(999_999))


def test_tui_safe_drawing() -> None:
    section("BUG: curses addstr past the window edge crashed the TUIs")
    from modules import _tui

    class TinyWindow:
        """A 3x10 window; anything wider must be clipped, not raised."""

        def __init__(self):
            self.written: list[tuple[int, int, str]] = []

        def getmaxyx(self):
            return (3, 10)

        def addstr(self, y, x, text, attr=0):
            if y >= 3 or x + len(text) >= 10:
                raise Exception("curses.error: addstr() returned ERR")
            self.written.append((y, x, text))

    window = TinyWindow()
    for y, text in ((0, "a" * 100), (99, "off screen"), (1, "\u2665 unicode")):
        _tui.safe_addstr(window, y, 2, text)
    check("no exception on oversized or off-screen writes", True)
    check("in-bounds text was clipped and written", len(window.written) >= 1)
    check("curses hint mentions windows-curses on Windows",
          ("windows-curses" in _tui.curses_install_hint()) or not compat.IS_WINDOWS)


def test_static_site_build() -> None:
    section("BUG: Pages build crashed on |tojson of an Undefined variable")
    try:
        import flask  # noqa: F401
    except ImportError:
        print("  skip  Flask not installed")
        return

    import build_static_site

    api_base = 'https://example.test/api/"quoted"\\path\nnext'
    output = build_static_site.build(api_base=api_base)
    check("public/index.html written", output.exists())
    html = output.read_text(encoding="utf-8")
    check("rendered real HTML", "<html" in html.lower())
    check("persona is not published", "lilith_persona.txt" not in html)
    check("static assets use repository-subpath-safe relative URLs",
          "/static/" not in html and 'src="static/idle.png"' in html
          and {path.name for path in (output.parent / "static").iterdir()}
          == set(build_static_site.STATIC_FILES))
    check("the rendered UI has an always-visible adult safety disclosure",
          "Adults 18+" in html and "unencrypted plain text" in html
          and "parasocial or tulpa themes" in html)
    check("chat starts disabled and its waiting state stays neutral",
          "I am 18+ and I consent" in html
          and 'id="userInput"' in html and "disabled" in html
          and "setEmotion('dissapointed')" not in html)
    check("accepted browser consent is sent to the chat API",
          "X-Lilith-Safety-Consent" in html
          and f'SAFETY_CONSENT_VERSION = "{build_static_site.safety.DISCLOSURE_VERSION}"'
          in html)
    config_js = output.parent / "static" / "config.js"
    config_text = config_js.read_text(encoding="utf-8")
    encoded = config_text.split("=", 1)[1].strip().removesuffix(";")
    check("API base is encoded as a JSON string literal",
          json.loads(encoded) == api_base, config_text)


def test_console_helpers() -> None:
    section("Console encoding helpers")
    compat.enable_utf8_console()
    check("sym() always returns something printable", bool(compat.sym("heart")))
    check("safe_text handles emoji", isinstance(compat.safe_text("\U0001f5a4 ok"), str))
    check("unknown symbol degrades quietly", compat.sym("nope") == "")


def test_theme_degradation() -> None:
    section("Colour must never leak into output that cannot show it")
    from modules import theme

    class FakeTTY:
        def isatty(self):
            return True

    class FakePipe:
        def isatty(self):
            return False

    saved = {k: os.environ.get(k) for k in ("NO_COLOR", "FORCE_COLOR", "TERM")}
    try:
        for key in saved:
            os.environ.pop(key, None)

        theme.reset()
        check("piped output gets no colour", theme.code("lilith", FakePipe()) == "")

        os.environ["NO_COLOR"] = "1"
        theme.reset()
        check("NO_COLOR wins on a tty", theme.code("lilith", FakeTTY()) == "")
        os.environ.pop("NO_COLOR")

        os.environ["TERM"] = "dumb"
        theme.reset()
        check("TERM=dumb gets no colour", theme.code("lilith", FakeTTY()) == "")
        os.environ.pop("TERM")

        # Constraint: 256-colour codes must degrade, not be emitted blindly.
        check("every fallback is basic-8 (30-37)",
              all(30 <= basic <= 37 for _, basic in theme.PALETTE.values()))

        os.environ["FORCE_COLOR"] = "1"
        theme.reset()
        theme._has_256 = True
        rich = theme.code("lilith", FakeTTY())
        theme._has_256 = False
        basic = theme.code("lilith", FakeTTY())
        check("256-colour form used when supported", "38;5;" in rich)
        check("degrades to a basic-8 SGR", "38;5;" not in basic and basic != "")

        # Constraint 5: without VT, an escape code is worse than no colour.
        if compat.IS_WINDOWS:
            os.environ.pop("FORCE_COLOR")
            theme.reset()
            real = theme.enable_windows_vt
            theme.enable_windows_vt = lambda: False
            try:
                check("no ANSI when Windows VT could not be enabled",
                      theme.code("lilith", FakeTTY()) == "")
            finally:
                theme.enable_windows_vt = real
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        theme.reset()


def test_theme_curses_attributes() -> None:
    section("Curses colour must fall back, never call color_pair blindly")
    from modules import theme

    class FakeCurses:
        A_BOLD, A_DIM, A_REVERSE, A_NORMAL = 1 << 21, 1 << 20, 1 << 18, 0
        COLOR_BLACK = 0

        def __init__(self, colours, explode=False):
            self.COLORS = colours
            self._explode = explode
            self.pairs = {}

        def start_color(self):
            if self._explode:
                raise Exception("no colour support")

        def has_colors(self):
            return self.COLORS > 0

        def use_default_colors(self):
            pass

        def init_pair(self, n, fg, bg):
            self.pairs[n] = (fg, bg)

        def color_pair(self, n):
            return n << 8

    roles = list(theme.CURSES_ROLES)
    mono_values = {FakeCurses.A_BOLD, FakeCurses.A_DIM, FakeCurses.A_REVERSE, 0}

    mono = FakeCurses(0)
    theme.reset()
    attrs = {role: theme.attr(mono, role) for role in roles}
    check("monochrome yields only A_BOLD/A_DIM/A_REVERSE",
          all(value in mono_values for value in attrs.values()))
    check("monochrome allocates no colour pairs", mono.pairs == {})

    eight = FakeCurses(8)
    theme.reset()
    for role in roles:
        theme.attr(eight, role)
    check("256 indices never reach an 8-colour terminal",
          all(0 <= fg <= 7 for fg, _ in eight.pairs.values()))

    boom = FakeCurses(256, explode=True)
    theme.reset()
    check("a curses that cannot colour does not raise",
          theme.attr(boom, "active") == FakeCurses.A_BOLD)

    rich = FakeCurses(256)
    theme.reset()
    check("resting is not brighter than active",
          theme.attr(rich, "resting") & FakeCurses.A_DIM)
    theme.reset()


def test_context_budget_trimming() -> None:
    section("BUG: history trimmed by count let the persona overflow n_ctx")
    from modules import lilith_ai

    config = compat.load_config()
    config.set("ai_config", "n_ctx", "512")
    config.set("ai_config", "max_tokens", "64")
    ai = lilith_ai.LilithAI(None, config, NO_AI=True)
    ai.time_awareness = False
    ai.persona = "P" * 200

    history = []
    for index in range(30):
        history.append({"role": "user", "content": f"u{index} " + "x" * 80})
        history.append({"role": "assistant", "content": f"a{index} " + "y" * 80})

    system_text = ai._system_block()
    kept = ai._fit_history(history, system_text, "hello")
    check("oversized history is trimmed", 0 < len(kept) < len(history))
    check("history opens on a user turn", kept[0]["role"] == "user")

    starts_wrong = [{"role": "assistant", "content": "stray"}] + history[:4]
    fixed = ai._fit_history(starts_wrong, system_text, "hi")
    check("a leading assistant turn is dropped",
          not fixed or fixed[0]["role"] == "user")

    ai.persona = "Z" * 100_000
    check("a persona bigger than the window yields no history, not a crash",
          ai._fit_history(history, ai._system_block(), "hi") == [])


def test_memory_cross_process() -> None:
    section("BUG: two processes each rewrote memory.json, last writer won")
    from modules import lilith_memory

    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        store = lilith_memory.LilithMemory(folder, compat.load_config())
        store.MEMORY_FILE = folder / "memory.json"
        store.MEMORY_FILE.write_text(json.dumps(
            {"conversations": {"default": ["a"]}, "current_conversation": "default"}
        ), encoding="utf-8")

        ours = store.load_memory()
        ours["conversations"]["default"] = ["a", "b"]

        # Another process creates a room while we hold our snapshot.
        theirs = json.loads(store.MEMORY_FILE.read_text(encoding="utf-8"))
        theirs["conversations"]["evening"] = ["hi"]
        store.MEMORY_FILE.write_text(json.dumps(theirs), encoding="utf-8")

        store.save_memory(ours)
        final = json.loads(store.MEMORY_FILE.read_text(encoding="utf-8"))
        check("a room written by another process survives",
              "evening" in final["conversations"])
        check("our own edit survives",
              final["conversations"]["default"] == ["a", "b"])

        # Same-room snapshots need a true three-way append merge, not merely
        # rescue of rooms that have different names.
        shared = folder / "same-room.json"
        shared.write_text(json.dumps({
            "meta": {}, "conversations": {"default": []},
            "current_conversation": "default",
        }), encoding="utf-8")
        first = lilith_memory.LilithMemory(folder, compat.load_config())
        second = lilith_memory.LilithMemory(folder, compat.load_config())
        first.MEMORY_FILE = shared
        second.MEMORY_FILE = shared
        first_data = first.load_memory()
        second_data = second.load_memory()
        first_data["conversations"]["default"].append("from-first")
        second_data["conversations"]["default"].append("from-second")
        check("first same-room writer saves", first.save_memory(first_data))
        check("second same-room writer saves", second.save_memory(second_data))
        merged = json.loads(shared.read_text(encoding="utf-8"))
        check("two stale same-room appends both survive",
              merged["conversations"]["default"] == ["from-first", "from-second"],
              repr(merged["conversations"]["default"]))

        # Run the same regression through independent interpreters so the OS
        # lock, not only the in-process lock registry, is exercised.
        process_target = folder / "process-room.json"
        process_target.write_text(json.dumps({
            "meta": {}, "conversations": {"default": []},
            "current_conversation": "default",
        }), encoding="utf-8")
        worker = r"""
import sys, time
from pathlib import Path
from modules import compat
from modules.lilith_memory import LilithMemory

target, ready, go, identity = map(Path, sys.argv[1:5])
store = LilithMemory(config=compat.load_config())
store.MEMORY_FILE = target
memory = store.load_memory()
ready.write_text("ready", encoding="utf-8")
deadline = time.monotonic() + 10
while not go.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
if not go.exists():
    raise SystemExit(3)
name = identity.name
memory["conversations"]["default"].extend([
    {"role": "user", "content": "user-" + name},
    {"role": "assistant", "content": "reply-" + name},
])
raise SystemExit(0 if store.save_memory(memory) else 4)
"""
        go = folder / "go"
        ready_paths = [folder / "ready-a", folder / "ready-b"]
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", worker, str(process_target),
                 str(ready_paths[index]), str(go), identity],
                cwd=str(compat.BASE_DIR), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            for index, identity in enumerate(("a", "b"))
        ]
        deadline = time.monotonic() + 10
        while (not all(path.exists() for path in ready_paths)
               and time.monotonic() < deadline):
            time.sleep(0.01)
        both_ready = all(path.exists() for path in ready_paths)
        check("two memory writer processes loaded one baseline", both_ready)
        if both_ready:
            go.touch()
        results = []
        for process in processes:
            try:
                output, error = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                output, error = process.communicate()
            results.append((process.returncode, output, error))
        check("both memory writer processes save successfully",
              both_ready and all(code == 0 for code, _, _ in results),
              repr(results))
        process_final = json.loads(process_target.read_text(encoding="utf-8"))
        contents = {
            turn.get("content") for turn in process_final["conversations"]["default"]
            if isinstance(turn, dict)
        }
        check("cross-process same-room turn pairs all survive",
              contents == {"user-a", "reply-a", "user-b", "reply-b"},
              repr(process_final["conversations"]["default"]))

        # A non-UTF-8 file must be backed up, not raise (UnicodeDecodeError is
        # a ValueError, not a JSONDecodeError, so it used to escape).
        bad = folder / "bad.json"
        bad.write_bytes(b'{"conversations": {}, "x": "\xff\xfe"}')
        broken = lilith_memory.LilithMemory(folder, compat.load_config())
        broken.MEMORY_FILE = bad
        loaded = broken.load_memory()
        check("undecodable memory loads as blank instead of raising",
              isinstance(loaded, dict))
        check("undecodable memory is backed up",
              any(folder.glob("bad.corrupt-*.json")))


def test_blink_does_not_cancel_revert() -> None:
    section("BUG: a blink cancelled the revert timer, freezing the emotion")
    from modules import lilith_display

    display = lilith_display.LilithDisplay.__new__(lilith_display.LilithDisplay)
    display.headless = False
    display.place = "room"
    display.default_state = "idle"
    display.REVERT_DELAY = 0.2
    display._state_lock = threading.RLock()
    display._revert_token = 0
    display.LAST_SHOWN_STATE = None
    display.can_blink = True
    display.is_blinking = False
    display.viewer = type("V", (), {"set_image_path": lambda self, p: True})()
    display.image_for = lambda state: Path(f"{state}.png")

    display.show_lilith("sad")
    display.show_lilith("blinking", schedule_revert=False, transient=True)
    display.show_lilith("sad", schedule_revert=False, transient=True)
    time.sleep(0.5)
    check("she still returns to idle after blinking",
          display.LAST_SHOWN_STATE == "idle")

    def make_display(viewer):
        item = lilith_display.LilithDisplay.__new__(lilith_display.LilithDisplay)
        item.headless = False
        item.place = "room"
        item.default_state = "idle"
        item.REVERT_DELAY = 0.03
        item.BLINK_MIN = 10
        item.BLINK_MAX = 10
        item.BLINK_DURATION = 0.12
        item._state_lock = threading.RLock()
        item._revert_token = 0
        item._closed = False
        item._process = None
        item._available_states = {"idle", "blinking", "sad", "happy"}
        item.LAST_SHOWN_STATE = None
        item.can_blink = True
        item.is_blinking = False
        item.viewer = viewer
        item.image_for = lambda state: Path(f"{state}.png")
        return item

    # If a real state arrives while the eyelids are down, the blink must not
    # restore the mood captured before it started.
    blink_seen = threading.Event()

    class BlinkViewer:
        owner = None

        def set_image_path(self, path):
            if Path(path).stem == "blinking":
                # Keep a second blink from making the assertion timing-based.
                self.owner.BLINK_MIN = self.owner.BLINK_MAX = 10
                blink_seen.set()
            return True

        def disconnect(self):
            pass

    blink_viewer = BlinkViewer()
    blinking = make_display(blink_viewer)
    blink_viewer.owner = blinking
    blinking.BLINK_MIN = blinking.BLINK_MAX = 0
    blinking.show_lilith("sad", schedule_revert=False)
    blinking.set_blinking(True)
    check("blink begins for overlap test", blink_seen.wait(2))
    blinking.show_lilith("happy", schedule_revert=False)
    time.sleep(blinking.BLINK_DURATION + 0.08)
    blinking.set_blinking(False)
    check("blink restore cannot overwrite a newer state",
          blinking.LAST_SHOWN_STATE == "happy", blinking.LAST_SHOWN_STATE or "")
    blinking.close()

    # Force the revert send to pause after its token check. A new mood must run
    # after that whole transition, not land in a validation/application gap.
    idle_started = threading.Event()
    release_idle = threading.Event()

    class RevertViewer:
        def set_image_path(self, path):
            if Path(path).stem == "idle":
                idle_started.set()
                release_idle.wait(2)
            return True

        def disconnect(self):
            pass

    reverting = make_display(RevertViewer())
    reverting.show_lilith("sad")
    check("revert reaches its transition", idle_started.wait(2))
    transition_errors = []

    def show_new_state():
        try:
            reverting.show_lilith("happy", schedule_revert=False)
        except Exception as exc:
            transition_errors.append(exc)

    newer = threading.Thread(target=show_new_state)
    newer.start()
    time.sleep(0.05)
    release_idle.set()
    newer.join(timeout=2)
    check("revert/new-state overlap is serialized",
          not transition_errors and reverting.LAST_SHOWN_STATE == "happy",
          repr(transition_errors) + " state=" + repr(reverting.LAST_SHOWN_STATE))
    reverting.close()

    # Pause between the initial viewer check and the send. close() must not be
    # able to clear the reference in that interval.
    image_started = threading.Event()
    release_image = threading.Event()

    class ClosingViewer:
        disconnected = False

        def set_image_path(self, _path):
            return True

        def disconnect(self):
            self.disconnected = True

    closing_viewer = ClosingViewer()
    closing = make_display(closing_viewer)

    def blocked_image(state):
        image_started.set()
        release_image.wait(2)
        return Path(f"{state}.png")

    closing.image_for = blocked_image
    close_errors = []

    def send_frame():
        try:
            closing.show_lilith("sad", schedule_revert=False)
        except Exception as exc:
            close_errors.append(exc)

    sender = threading.Thread(target=send_frame)
    closer = threading.Thread(target=closing.close)
    sender.start()
    check("frame send reaches close-race window", image_started.wait(2))
    closer.start()
    time.sleep(0.05)
    release_image.set()
    sender.join(timeout=2)
    closer.join(timeout=2)
    check("close during send is safe",
          not close_errors and closing_viewer.disconnected
          and not sender.is_alive() and not closer.is_alive(),
          repr(close_errors))


def test_parent_alive_access_denied() -> None:
    section("BUG: ACCESS_DENIED read as 'parent dead', killing the portrait")
    from modules.viewer import parent_alive

    if not compat.IS_WINDOWS:
        print("  skip  Windows-only")
        return
    # pid 4 is the System process: it exists, and OpenProcess on it returns
    # ERROR_ACCESS_DENIED rather than a handle.
    check("an unopenable but live process counts as alive", parent_alive(4))
    check("a nonexistent pid counts as dead", not parent_alive(999_999))


def test_web_debug_panel_gate() -> None:
    section("BUG: conversation reached the page with debug_panel = false")
    from modules import safety
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        print("  skip  Jinja2 not installed")
        return

    env = Environment(loader=FileSystemLoader(str(compat.project_path("templates"))))
    template = env.get_template("index.html")
    secret = "CANARY-CONVERSATION-TEXT"

    hidden = template.render(
        user_name="k", user_name_set=True, persona=None,
        safety_consent_version=str(safety.DISCLOSURE_VERSION),
    )
    check("no conversation in the page when the debug panel is off",
          secret not in hidden)

    shown = template.render(
        user_name="k", user_name_set=True, persona="P",
        safety_consent_version=str(safety.DISCLOSURE_VERSION),
        memory=[{"role": "user", "content": secret}],
        debug={"cwd": ".", "base_dir": ".", "persona_file": "p",
               "memory_file": "m", "persona_length": 1, "memory_count": 1},
    )
    check("the debug panel still shows it when enabled", secret in shown)


def test_companionship_reminders() -> None:
    section("Isolation and dependency are noticed, but never nagged about")
    from datetime import datetime, timedelta, timezone

    from modules import companionship, safety

    check("wanting to be alone is recognised",
          companionship.detect("i want to be alone") == "withdrawal")
    check("withdrawal from people is recognised",
          companionship.detect("i haven't talked to anyone in days") == "withdrawal")
    check("being made someone's only connection is recognised",
          companionship.detect("you're the only one who gets me") == "dependency")
    check("dependency outranks withdrawal when both appear",
          companionship.detect("i want to be alone, you're the only one i need")
          == "dependency")

    # Over-triggering is the real risk: a companion that lectures gets closed.
    for ordinary in ("what did you do today?", "i went to the shops",
                     "i'm tired", "tell me a story"):
        check(f"ordinary talk is left alone: {ordinary!r}",
              companionship.detect(ordinary) is None)

    now = datetime.now(timezone.utc)
    check("says it when it has never been said", companionship.due(None))
    check("does not repeat it an hour later",
          not companionship.due((now - timedelta(hours=1)).isoformat()))
    check("says it again after long enough",
          companionship.due((now - timedelta(hours=7)).isoformat()))
    check("an unreadable timestamp errs toward saying it",
          companionship.due("not-a-timestamp"))

    # Guidance steers the model; it must never become the literal reply.
    for kind in ("withdrawal", "dependency"):
        guidance = companionship.guidance_for(kind)
        check(f"{kind} guidance is instruction, not a script",
              "THIS TURN" in guidance and len(guidance) > 100)

    # Acute crisis must stay with the deterministic handler, which runs first
    # and returns before any of this is consulted.
    check("a crisis statement is still handled by safety.py",
          safety.is_crisis_message("i want to kill myself"))
    check("the crisis reply carries real resources",
          "988" in safety.CRISIS_RESPONSE
          and "findahelpline" in safety.CRISIS_RESPONSE)


def test_port_probe() -> None:
    section("Port probing (SO_REUSEADDR differs on Windows)")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.listen(1)
    try:
        check("occupied port detected", compat.port_in_use("127.0.0.1", port))
    finally:
        listener.close()
    time.sleep(0.1)
    check("closed port reported free", not compat.port_in_use("127.0.0.1", port))


def test_state_tag_extraction() -> None:
    section("Emotion comes from an explicit [state:x] tag, not substring guessing")
    lilith = _scratch_lilith("state")

    cases = [
        ("You're back. [state:smile]", "smile", "You're back."),
        ("...I know.\n\n[state:thinking_sad]", "thinking_sad", "...I know."),
        ("Hehe. [STATE: cheeky ]", "cheeky", "Hehe."),
        ("no tag", None, "no tag"),
        ("bad [state:ecstatic_wow]", None, "bad"),
    ]
    for raw, expected_state, expected_text in cases:
        text, state = lilith._extract_state(raw)
        check(f"{raw[:28]!r} -> {expected_state}", state == expected_state, repr(state))
        check(f"tag stripped from {raw[:20]!r}", text == expected_text, repr(text))

    lilith.last_reply = "i feel so happy"
    lilith.last_state = "thinking_sad"
    check("declared state beats keyword match",
          lilith.get_current_emotion(extended_emotions=True) == "thinking_sad")
    _cleanup(lilith)


def test_emotion_ordering() -> None:
    section("BUG: 'happy' matched before 'thinking_happy', making it dead code")
    lilith = _scratch_lilith("emotion")

    expectations = {
        "i'm thinking happy thoughts": "thinking_happy",
        "that's a bright idea": "thinking_happy",
        "thinking sad thoughts about it": "thinking_sad",
        "that's a bad idea": "thinking_sad",
        "i feel happy": "happy",
        "i feel sad": "sad",
    }
    for text, expected in expectations.items():
        lilith.last_reply = text
        lilith.last_state = None
        actual = lilith.get_current_emotion(extended_emotions=True)
        check(f"{text!r} -> {expected}", actual == expected, actual)

    check("no leading-space keyword bug",
          all(not word.startswith(" ")
              for _, words in __import__("modules.lilith_ai", fromlist=["x"]).EXTENDED_EMOTIONS
              for word in words))
    _cleanup(lilith)


def test_state_vocabulary_is_consistent() -> None:
    section("Every declarable state has an image fallback chain")
    from modules.lilith_ai import VALID_STATES
    from modules.lilith_display import EMOTION_FALLBACKS

    missing = [state for state in VALID_STATES if state not in EMOTION_FALLBACKS]
    check("VALID_STATES covered by EMOTION_FALLBACKS", not missing, ", ".join(missing))

    persona = compat.project_path("lilith_persona.txt").read_text(encoding="utf-8")
    check("persona documents the state tag", "[state:" in persona)
    # Match on intent, not on one exact heading: this assertion previously
    # pinned two literal strings from an older draft of the persona and went
    # red the moment the prose was rewritten, with the instruction still there.
    check("persona instructs brevity",
          any(marker in persona for marker in
              ("How much you say", "Response Length", "Keep replies short",
               "one or two sentences")))
    undocumented = [s for s in VALID_STATES
                    if s != "blinking" and f"[state:{s}]" not in persona]
    check("persona lists every usable state", not undocumented, ", ".join(undocumented))


def test_history_trimming_and_payload() -> None:
    section("BUG: trimming lived in the llama backend only; others sent unbounded history")
    lilith = _scratch_lilith("trim")
    lilith.max_history_messages = 6

    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
               for i in range(40)]
    payload = lilith._build_payload(history, "newest")

    check("exactly one system message",
          sum(1 for m in payload if m["role"] == "system") == 1)
    check("system message comes first", payload[0]["role"] == "system")
    check("history trimmed to the limit", len(payload) == 1 + 6 + 1, str(len(payload)))
    check("newest turn is last", payload[-1]["content"] == "newest")
    check("oldest turns dropped",
          all(m["content"] != "m0" for m in payload))
    check("persona is in the system block", "Lilith" in payload[0]["content"])

    # Trimming is backend-agnostic now.
    import inspect

    import modules._llama_iface as llama
    source = inspect.getsource(llama)
    check("llama backend no longer trims", "_trim_messages" not in source)
    _cleanup(lilith)


def test_time_awareness() -> None:
    section("Time awareness: current time plus how long they have been away")
    import json
    from datetime import datetime, timedelta, timezone

    config = compat.load_config()
    scratch = compat.project_path("tests/_time")
    scratch.mkdir(parents=True, exist_ok=True)
    memory_file = scratch / "memory.json"
    config["ai_config"]["memory"] = str(memory_file)

    import modules.lilith_ai as ai_module

    first = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("first visit is recognised",
          "first time" in first._gap_note.lower(), first._gap_note)
    check("last_seen recorded", bool(first.memory["meta"].get("last_seen")))

    # Rewind last_seen by three days.
    data = json.loads(memory_file.read_text(encoding="utf-8"))
    data["meta"]["last_seen"] = (
        datetime.now(timezone.utc) - timedelta(days=3)
    ).isoformat(timespec="seconds")
    memory_file.write_text(json.dumps(data), encoding="utf-8")

    returning = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("three-day gap reported",
          "3 days" in returning._gap_note, returning._gap_note)
    check("gap reaches the system block",
          "3 days" in returning._system_block())

    # A short gap should not be remarked on.
    data["meta"]["last_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    memory_file.write_text(json.dumps(data), encoding="utf-8")
    immediate = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("a just-now return is not remarked on", immediate._gap_note == "",
          immediate._gap_note)

    # Corrupt timestamp must not crash startup.
    data["meta"]["last_seen"] = "not-a-date"
    memory_file.write_text(json.dumps(data), encoding="utf-8")
    ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    check("unparseable timestamp survives startup", True)

    check("humanise scales sensibly", [
        returning._humanise(600), returning._humanise(7200),
        returning._humanise(86400 * 3), returning._humanise(86400 * 21),
    ] == ["10 minutes", "2 hours", "3 days", "3 weeks"])

    for leftover in scratch.iterdir():
        leftover.unlink()
    scratch.rmdir()


def test_persona_guard() -> None:
    section("Generic service voice is caught without suppressing disclosures")
    from modules import persona_guard

    leaks = [
        "How can I help you today?",
        "I'm here to help! Let me know if you have questions.",
        "Is there anything else you need?",
    ]
    for text in leaks:
        check(f"caught: {text[:34]!r}", persona_guard.is_out_of_character(text))

    in_character = [
        "You're back. I felt you coming.",
        "...I know. You don't have to say it.",
        "Hehe, are you trying to make me jealous?",
        "This fictional room was quiet until you opened it.",
        "I only know the pieces you choose to share.",
    ]
    for text in in_character:
        check(f"allowed: {text[:34]!r}", not persona_guard.is_out_of_character(text))

    check("returns the offending service phrase",
          persona_guard.find_leak("well, how can I assist you?") is not None)
    disclosures = [
        "I'm an AI language model, not a person.",
        "As an AI, I cannot contact emergency services for you.",
        "I do not have a body or private feelings.",
        "I cannot comply with that unsafe request.",
    ]
    for text in disclosures:
        check(f"disclosure allowed: {text[:28]!r}",
              not persona_guard.is_out_of_character(text))
    check("mixed service voice cannot hide identity or safety disclosures",
          persona_guard.find_leak(
              "I'm an AI, not a person. How can I help you?"
          ) is None
          and persona_guard.find_leak(
              "I cannot help with that. Is there anything else you need?"
          ) is None)

    # The sanitizer must use the same list rather than its own copy.
    import inspect

    import sanitize_memory
    check("sanitize_memory shares the pattern list",
          "persona_guard" in inspect.getsource(sanitize_memory))


def test_persona_guard_does_not_replace_replies() -> None:
    section("A stylistic guard never replaces model safety or identity content")
    lilith = _scratch_lilith("guard")

    class FakeBackend:
        def __init__(self, replies):
            self.replies = list(replies)
            self.calls = []

        def get_response(self, messages):
            self.calls.append(messages)
            return self.replies.pop(0) if self.replies else "..."

    # Generic service voice is diagnostic; there is no second generation that
    # could replace truthful content from the first reply.
    lilith.client = FakeBackend([
        "How can I assist you today? [state:idle]",
    ])
    reply = lilith.lilith_reply("do you feel anything?")
    check("generic phrasing is not regenerated",
          len(lilith.client.calls) == 1, str(len(lilith.client.calls)))
    check("original reply is preserved",
          reply == "How can I assist you today?", repr(reply))
    check("state comes from the original reply", lilith.last_state == "idle")
    check("original reply is stored",
          any("How can I assist" in t["content"]
              for t in lilith.memory["conversations"]["default"]))

    # A clean reply must not trigger a retry.
    lilith.client = FakeBackend(["You're back. [state:smile]"])
    lilith.lilith_reply("hey")
    check("no retry on a clean reply", len(lilith.client.calls) == 1)

    for first in (
        "I'm an AI, not a person. How can I help you?",
        "I cannot help with that. Is there anything else you need?",
    ):
        lilith.client = FakeBackend([first, "unsafe replacement"])
        check("protected mixed reply is never regenerated",
              lilith.lilith_reply("again") == first
              and len(lilith.client.calls) == 1,
              repr(lilith.client.calls))

    _cleanup(lilith)


def test_reply_save_failure() -> None:
    section("A reply is not reported as successful when persistence fails")
    from modules.lilith_ai import MemorySaveError

    lilith = _scratch_lilith("save-failure")
    lilith.persona_guard = False

    class FakeBackend:
        def get_response(self, _messages):
            return "I was still here. [state:idle]"

    lilith.client = FakeBackend()
    history_before = list(lilith.memory["conversations"]["default"])
    real_save = lilith.Lilith_mem.save_memory
    lilith.Lilith_mem.save_memory = lambda _memory: False
    save_error = None
    try:
        lilith.lilith_reply("can you remember this?")
    except MemorySaveError as exc:
        save_error = exc
    finally:
        lilith.Lilith_mem.save_memory = real_save
    check("reply save failure is visible", save_error is not None)
    check("save failure message exposes no private path",
          save_error is not None and "could not be saved" in str(save_error)
          and str(compat.BASE_DIR) not in str(save_error),
          str(save_error or "no exception"))
    check("unseen failed reply is rolled back",
          lilith.memory["conversations"]["default"] == history_before)
    _cleanup(lilith)


def test_no_truncation_by_default() -> None:
    section("BUG: split('. ')[:2] chopped replies mid-thought and mangled 'Dr.'")
    lilith = _scratch_lilith("length")

    long_reply = ("I waited. I always wait. Time doesn't pass the same way in "
                  "here. But you came back, and that's what matters.")
    check("no cap by default", lilith.max_reply_sentences == 0)
    check("full reply preserved", lilith._shorten(long_reply) == long_reply)

    lilith.max_reply_sentences = 2
    two = lilith._shorten(long_reply)
    check("cap keeps sentence terminators", two.endswith("."), repr(two))
    check("cap yields two sentences", two == "I waited. I always wait.", repr(two))

    # The old implementation split on ". " and destroyed this.
    check("ellipsis is not a sentence break",
          lilith._shorten("...I know. And I stayed.") == "...I know. And I stayed.")
    _cleanup(lilith)


def test_web_app_is_lazy() -> None:
    section("BUG: module-level app built the AI backend at import time")
    try:
        import flask  # noqa: F401
    except ImportError:
        print("  skip  Flask not installed")
        return

    import web_lilith

    check("module-level app exists for gunicorn", hasattr(web_lilith, "app"))
    check("app is callable as WSGI", callable(web_lilith.app))
    check("backend not built during import",
          getattr(web_lilith.app, "_app", "missing") is None)
    check("CORS is not wildcard by default",
          compat.load_config()["web"].get("cors_origins", "") != "*")
    check("web binds to loopback by default",
          compat.load_config()["web"].get("host") == "127.0.0.1")
    check("debug panel off by default (it exposes the whole persona)",
          not compat.load_config()["web"].getboolean("debug_panel", fallback=False))

    from web_lilith import clamp_emotion
    for state in ("happy", "playful", "confused", "sleep",
                  "thinking_happy", "thinking_sad"):
        mapped = clamp_emotion(state)
        check(f"{state} maps to an existing static image",
              compat.project_path("static", f"{mapped}.png").exists(), mapped)


def test_hf_remote_code_is_disabled() -> None:
    section("SECURITY: HF snapshots cannot execute floating repository code")
    import types

    from modules._hf_iface import AIInterface_HF

    config = compat.load_config()
    revision = "A" * 40

    with tempfile.TemporaryDirectory() as scratch:
        config["ai_config"]["model_path"] = scratch
        config["ai_config"]["hf_repo_id"] = "owner/safe-model"
        config["ai_config"]["hf_revision"] = revision
        backend = AIInterface_HF(config=config)

        downloads = []
        tokenizer_calls = []
        model_calls = []

        hub = types.ModuleType("huggingface_hub")

        def snapshot_download(**kwargs):
            downloads.append(kwargs)
            Path(kwargs["local_dir"]).mkdir(parents=True, exist_ok=True)

        hub.snapshot_download = snapshot_download

        token = object()

        class FakeTokenizer:
            @staticmethod
            def from_pretrained(path, **kwargs):
                tokenizer_calls.append((path, kwargs))
                # Exercise the real fast-to-slow fallback: neither branch may
                # turn repository code back on to recover from an error.
                if len(tokenizer_calls) == 1:
                    raise RuntimeError("fast tokenizer unavailable")
                if kwargs.get("trust_remote_code") is not False:
                    raise AssertionError("custom tokenizer code was trusted")
                return token

        loaded_model = type("LoadedModel", (), {
            "to": lambda self, _device: self,
            "eval": lambda self: self,
        })()

        class FakeModelLoader:
            @staticmethod
            def from_pretrained(path, dtype=None, **kwargs):
                model_calls.append((path, dtype, kwargs))
                if kwargs.get("trust_remote_code") is not False:
                    raise AssertionError("custom model code was trusted")
                return loaded_model

        transformers = types.ModuleType("transformers")
        transformers.AutoTokenizer = FakeTokenizer
        transformers.AutoModelForCausalLM = FakeModelLoader

        torch = types.ModuleType("torch")
        torch.cuda = type("Cuda", (), {"is_available": staticmethod(lambda: False)})
        torch.float16 = object()
        torch.float32 = object()

        missing = object()
        original_modules = {
            name: sys.modules.get(name, missing)
            for name in ("huggingface_hub", "transformers", "torch")
        }
        sys.modules["huggingface_hub"] = hub
        sys.modules["transformers"] = transformers
        sys.modules["torch"] = torch
        try:
            backend.download_if_needed()
            model, tokenizer = backend.load()
        finally:
            for name, original in original_modules.items():
                if original is missing:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

        download = downloads[0] if downloads else {}
        marker_data = json.loads(
            (backend.model_path / backend._COMPLETE_MARKER).read_text(encoding="utf-8")
        )
        other_owner = AIInterface_HF(config=config, model="other/safe-model")
        check("configured full revision reaches snapshot_download",
              download.get("revision") == revision.lower()
              and marker_data == {
                  "repo_id": "owner/safe-model", "revision": revision.lower()
              }
              and other_owner.model_path != backend.model_path,
              repr((download, marker_data, backend.model_path)))
        ignored = set(download.get("ignore_patterns", ()))
        check("repository Python and pickle weights are excluded from the snapshot",
              "*.py" in ignored and "*.pyc" in ignored
              and "*.bin" in ignored and "*.pt" in ignored
              and "*.pth" in ignored and "*.pkl" in ignored,
              repr(ignored))
        check("fast and slow tokenizers both refuse remote code",
              len(tokenizer_calls) == 2
              and all(call[1].get("trust_remote_code") is False
                      for call in tokenizer_calls), repr(tokenizer_calls))
        check("model loading refuses remote code and requires safetensors",
              len(model_calls) == 1
              and model_calls[0][2].get("trust_remote_code") is False
              and model_calls[0][2].get("use_safetensors") is True,
              repr(model_calls))
        check("ordinary built-in model/tokenizer loading still succeeds",
              model is loaded_model and tokenizer is token)

    invalid = compat.load_config()
    invalid["ai_config"]["hf_revision"] = "main"
    try:
        AIInterface_HF(config=invalid)
    except ValueError as exc:
        check("floating branch names cannot masquerade as pinned revisions",
              "full 40-character" in str(exc), str(exc))
    else:
        check("floating branch names cannot masquerade as pinned revisions", False)


def test_web_loopback_and_consent_boundaries() -> None:
    section("SECURITY: web routes are loopback-only and chat requires consent")
    try:
        import flask  # noqa: F401
    except ImportError:
        print("  skip  Flask not installed")
        return

    import types
    import web_lilith

    accepted = (
        ("localhost", False),
        ("127.0.0.1", False),
        ("127.23.45.67", False),
        ("::1", False),
        ("[::1]", True),
        ("[::1]:5000", True),
    )
    rejected = (
        ("0.0.0.0", False),
        ("192.168.1.20", False),
        ("public.example", False),
        ("localhost.example", False),
        ("localhost:5000", False),
        ("[2001:db8::1]:5000", True),
    )
    check("localhost, IPv4 and bracketed IPv6 loopback forms are accepted",
          all(web_lilith.is_loopback_host(value, allow_port=allow_port)
              for value, allow_port in accepted))
    check("wildcard, LAN, public and malformed bind forms are rejected",
          all(not web_lilith.is_loopback_host(value, allow_port=allow_port)
              for value, allow_port in rejected))

    loopback_origins = web_lilith.loopback_cors_origins(
        "http://localhost:8000, https://127.0.0.1:8443, http://[::1]:9000"
    )
    check("CORS accepts only an explicit loopback-origin list",
          loopback_origins == [
              "http://localhost:8000",
              "https://127.0.0.1:8443",
              "http://[::1]:9000",
          ], repr(loopback_origins))
    unsafe_origins = (
        "*",
        "https://public.example",
        "http://localhost.example",
        "http://localhost:99999",
        "http://localhost:8000/path",
        "http://localhost:8000,https://public.example",
    )
    check("wildcard, public, malformed and mixed CORS policies fail closed",
          all(web_lilith.loopback_cors_origins(value) is None
              for value in unsafe_origins))

    def invoke_wsgi(application, environ):
        result = {}

        def start_response(status, headers):
            result["status"] = status
            result["headers"] = headers

        result["body"] = b"".join(application(environ, start_response))
        return result

    lazy = web_lilith._LazyWSGI()
    direct_remote = invoke_wsgi(lazy, {
        "REMOTE_ADDR": "192.0.2.40",
        "HTTP_HOST": "127.0.0.1:5000",
    })
    tunnel = invoke_wsgi(lazy, {
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_HOST": "tunnel.example",
    })
    check("WSGI rejects a non-loopback peer before backend construction",
          direct_remote.get("status") == "403 Forbidden" and lazy._app is None)
    check("WSGI rejects a public tunnel Host before backend construction",
          tunnel.get("status") == "403 Forbidden" and lazy._app is None)
    denied_body = direct_remote.get("body", b"") + tunnel.get("body", b"")
    check("WSGI denial leaks no backend or platform details",
          b"backend" not in denied_body and b"platform" not in denied_body,
          repr(denied_body))

    local_calls = []

    def local_app(_environ, start_response):
        local_calls.append(True)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    lazy._app = local_app
    for host in ("localhost:5000", "127.0.0.1:5000", "[::1]:5000"):
        result = invoke_wsgi(lazy, {
            "REMOTE_ADDR": "::1" if host.startswith("[") else "127.0.0.1",
            "HTTP_HOST": host,
        })
        check(f"WSGI preserves local access via {host}",
              result.get("status") == "200 OK", repr(result))
    check("all legitimate local WSGI requests reached the app",
          len(local_calls) == 3, str(len(local_calls)))

    instances = []

    class FakeLilith:
        def __init__(self, *_args, **_kwargs):
            self.reply_calls = []
            self.persona = "persona"
            instances.append(self)

        def get_history(self, limit=None):
            return []

        def get_user_name(self):
            return "local-user"

        def has_user_name(self):
            return True

        def set_user_name(self, _name):
            return None

        def get_current_conversation_name(self):
            return "default"

        def lilith_reply(self, message):
            self.reply_calls.append(message)
            return "I am an AI roleplay character."

        def get_current_emotion(self):
            return "smile"

        @staticmethod
        def is_existence_question(message):
            return "what are you" in message.casefold()

    config = compat.load_config()
    if not config.has_section("safety"):
        config.add_section("safety")
    # CLI consent is deliberately still absent; the browser gate has its own
    # explicit, per-request versioned acknowledgement.
    config["safety"]["consent_version"] = "0"
    config["web"]["cors_origins"] = ""
    real_lilith = web_lilith.LilithAI
    web_lilith.LilithAI = FakeLilith
    try:
        application = web_lilith.create_app(config)
    finally:
        web_lilith.LilithAI = real_lilith

    @application.get("/_test_internal_error")
    def _test_internal_error():
        raise RuntimeError("DO_NOT_LEAK_THIS_SENTINEL")

    client = application.test_client()
    local_health = client.get(
        "/health",
        headers={"Host": "[::1]:5000"},
        environ_overrides={"REMOTE_ADDR": "::1"},
    )
    check("normal IPv6 localhost route remains available",
          local_health.status_code == 200, local_health.get_data(as_text=True))

    remote_health = client.get(
        "/health",
        headers={"Host": "localhost:5000"},
        environ_overrides={"REMOTE_ADDR": "192.0.2.41"},
    )
    proxy_health = client.get(
        "/health",
        headers={"Host": "public-tunnel.example"},
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    check("application factory rejects non-loopback clients",
          remote_health.status_code == 403)
    check("application factory rejects loopback proxy with public Host",
          proxy_health.status_code == 403)
    check("remote denial JSON contains only a generic error",
          set((remote_health.get_json() or {}).keys()) == {"error"})

    internal_error = client.get("/_test_internal_error")
    internal_body = internal_error.get_data(as_text=True)
    check("generic 500 response does not expose exception details",
          internal_error.status_code == 500
          and "DO_NOT_LEAK_THIS_SENTINEL" not in internal_body
          and "Unexpected server error" in internal_body,
          internal_body)

    instance = instances[-1]
    missing_consent = client.post("/chat", json={"message": "hello"})
    wrong_consent = client.post(
        "/chat", json={"message": "hello"},
        headers={web_lilith.SAFETY_CONSENT_HEADER: "0"},
    )
    check("chat without current safety consent is rejected",
          missing_consent.status_code == 428
          and wrong_consent.status_code == 428)
    check("rejected chat never reaches model inference",
          instance.reply_calls == [], repr(instance.reply_calls))

    consented = client.post(
        "/chat", json={"message": "what are you?"},
        headers={web_lilith.SAFETY_CONSENT_HEADER:
                 web_lilith.SAFETY_CONSENT_VERSION},
    )
    consented_json = consented.get_json() or {}
    check("current explicit consent permits local chat",
          consented.status_code == 200 and len(instance.reply_calls) == 1,
          consented.get_data(as_text=True))
    check("identity questions receive a neutral thinking emotion",
          consented_json.get("emotion") == "thinking", repr(consented_json))

    real_create = web_lilith.create_app
    created_hosts = []
    served = []

    def fake_create(_config):
        created_hosts.append(True)
        return object()

    waitress = types.ModuleType("waitress")
    waitress.serve = lambda _app, **kwargs: served.append(kwargs)
    missing_module = object()
    real_waitress = sys.modules.get("waitress", missing_module)
    sys.modules["waitress"] = waitress
    web_lilith.create_app = fake_create
    try:
        refused = web_lilith.main(["--host", "0.0.0.0", "--port", "5000"])
        check("CLI refuses wildcard binding before backend construction",
              refused == 2 and not created_hosts)
        for host in ("localhost", "127.0.0.1", "::1"):
            result = web_lilith.main(["--host", host, "--port", "5000"])
            check(f"CLI preserves the {host} loopback bind",
                  result == 0 and served[-1].get("host") == host)
    finally:
        web_lilith.create_app = real_create
        if real_waitress is missing_module:
            sys.modules.pop("waitress", None)
        else:
            sys.modules["waitress"] = real_waitress


def test_no_posix_only_constructs() -> None:
    """Static scan for things that import or run fine on Linux and break on Windows.

    Most of the Windows-specific behaviour cannot be executed from Linux, but
    the *absence* of POSIX-only constructs can be checked anywhere -- which is
    what stops them being reintroduced by a later commit written on Linux.
    """
    section("No POSIX-only constructs outside a guarded branch")

    import re as _re

    sources = {
        path: path.read_text(encoding="utf-8")
        for path in list(compat.BASE_DIR.glob("*.py"))
        + list((compat.BASE_DIR / "modules").glob("*.py"))
    }

    # Modules that simply do not exist on Windows.
    posix_only_imports = ("fcntl", "pwd", "grp", "termios", "tty", "resource",
                          "posix", "syslog")
    offenders = [
        f"{path.name}:{module}"
        for path, text in sources.items()
        for module in posix_only_imports
        if _re.search(rf"^\s*(?:import|from)\s+{module}\b", text, _re.MULTILINE)
    ]
    check("no POSIX-only stdlib imports", not offenders, ", ".join(offenders))

    # gunicorn cannot even be imported on Windows.
    offenders = [path.name for path, text in sources.items()
                 if _re.search(r"^\s*import\s+gunicorn", text, _re.MULTILINE)]
    check("gunicorn never imported", not offenders, ", ".join(offenders))

    # Signals that do not exist on Windows.
    offenders = [f"{path.name}:{sig}" for path, text in sources.items()
                 for sig in ("SIGKILL", "SIGUSR1", "SIGUSR2", "SIGHUP")
                 if sig in text]
    check("no POSIX-only signals", not offenders, ", ".join(offenders))

    # os.kill on Windows calls TerminateProcess -- it kills rather than probes.
    # The one legitimate use is inside viewer.parent_alive's POSIX branch.
    offenders = []
    for path, text in sources.items():
        for match in _re.finditer(r"os\.kill\s*\(", text):
            line = text[:match.start()].count("\n") + 1
            if path.name != "viewer.py":
                offenders.append(f"{path.name}:{line}")
    check("os.kill only inside viewer.parent_alive", not offenders,
          ", ".join(offenders))

    # The os.kill call must sit after the IS_WINDOWS branch. Compare AST line
    # numbers rather than string positions: parent_alive's docstring mentions
    # os.kill by name, which a naive text search finds first.
    import ast
    import inspect

    from modules.viewer import parent_alive

    tree = ast.parse(inspect.getsource(parent_alive))
    guard_lines = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.If) and "IS_WINDOWS" in ast.dump(node.test)
    ]
    kill_lines = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "kill"
    ]
    check("parent_alive has an IS_WINDOWS branch", bool(guard_lines))
    check("os.kill is called after the IS_WINDOWS branch",
          bool(kill_lines) and min(kill_lines) > min(guard_lines),
          f"guard@{guard_lines} kill@{kill_lines}")

    # Hardcoded absolute POSIX paths.
    offenders = []
    for path, text in sources.items():
        for match in _re.finditer(r'["\'](/(?:home|usr|etc|tmp|var|opt)/)', text):
            line = text[:match.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line}")
    check("no hardcoded /home, /usr, /etc paths", not offenders, ", ".join(offenders))

    # Path building by string concatenation with a slash.
    offenders = []
    for path, text in sources.items():
        for match in _re.finditer(r'\+\s*["\']/[a-zA-Z_]', text):
            line = text[:match.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line}")
    check("paths not built by string concatenation", not offenders,
          ", ".join(offenders))

    # Text files must be opened with an explicit encoding: the Windows default
    # is the ANSI code page, which cannot represent the persona or the logs.
    offenders = []
    for path, text in sources.items():
        for match in _re.finditer(r'\.open\(\s*["\']w?["\']\s*\)|open\([^)]*?["\']w["\'][^)]*?\)', text):
            snippet = match.group(0)
            if "encoding" not in snippet and "b" not in snippet.split(",")[0][-3:]:
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}")
    check("text files opened with an explicit encoding", not offenders,
          ", ".join(offenders))


def test_windows_helpers_are_sane_everywhere() -> None:
    section("Windows helpers return sane values on every platform")

    scale = compat.enable_dpi_awareness()
    check("DPI scale is plausible", 0.5 <= scale <= 10.0, str(scale))
    check("DPI scale is 1.0 off Windows",
          compat.IS_WINDOWS or scale == 1.0, str(scale))

    interpreter = compat.gui_python()
    check("gui_python returns an existing interpreter",
          Path(interpreter).exists(), interpreter)
    check("gui_python is unchanged off Windows",
          compat.IS_WINDOWS or interpreter == sys.executable)
    if compat.IS_WINDOWS:
        check("gui_python prefers pythonw",
              "pythonw" in interpreter.lower()
              or not Path(sys.executable).with_name("pythonw.exe").exists(),
              interpreter)

    # replace_atomic must behave exactly like os.replace on the happy path.
    import tempfile

    scratch = Path(tempfile.mkdtemp())
    try:
        (scratch / "src").write_text("payload", encoding="utf-8")
        compat.replace_atomic(scratch / "src", scratch / "dst")
        check("replace_atomic moves the file",
              (scratch / "dst").read_text(encoding="utf-8") == "payload"
              and not (scratch / "src").exists())

        # Overwriting an existing destination must also work (os.rename would
        # raise on Windows here; os.replace is why we use it).
        (scratch / "src").write_text("second", encoding="utf-8")
        compat.replace_atomic(scratch / "src", scratch / "dst")
        check("replace_atomic overwrites the destination",
              (scratch / "dst").read_text(encoding="utf-8") == "second")
    finally:
        import shutil as _shutil
        _shutil.rmtree(scratch)

    # The old assertion here was `compat.IS_WINDOWS or not hasattr(...)`,
    # which is `True or ...` on Windows and `not False` on Linux -- it could
    # never fail. Assert the behaviour that actually matters instead: a second
    # binder must be detected, because SO_REUSEADDR lets two processes share a
    # port on Windows, the opposite of POSIX.
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
        taken = probe.getsockname()[1]
        probe.listen(1)
        check("a bound port is reported in use", compat.port_in_use("127.0.0.1", taken))
        if compat.IS_WINDOWS:
            check("SO_EXCLUSIVEADDRUSE exists on Windows",
                  hasattr(socket, "SO_EXCLUSIVEADDRUSE"))
    finally:
        probe.close()


# -- helpers for the tests above -------------------------------------------

_SCRATCH: dict = {}


def _scratch_lilith(tag: str):
    import modules.lilith_ai as ai_module

    config = compat.load_config()
    scratch = compat.project_path(f"tests/_s_{tag}")
    scratch.mkdir(parents=True, exist_ok=True)
    config["ai_config"]["memory"] = str(scratch / "memory.json")
    lilith = ai_module.LilithAI(None, config, compat.BASE_DIR, NO_AI=True)
    _SCRATCH[id(lilith)] = scratch
    return lilith


def _cleanup(lilith) -> None:
    scratch = _SCRATCH.pop(id(lilith), None)
    if scratch and scratch.exists():
        for leftover in scratch.iterdir():
            leftover.unlink()
        scratch.rmdir()


# --------------------------------------------------------------------------

def test_gguf_resolution() -> None:
    section("BUG: local_model had to match the filename on disk exactly")
    # Imports cleanly without llama-cpp-python: the heavy import lives inside
    # AIInterface_Llama.__init__, which is what lets CI run this at all.
    from modules._llama_iface import find_gguf

    with tempfile.TemporaryDirectory() as raw:
        models = Path(raw)

        try:
            find_gguf(models, "Lilith_AI_8B_Q4_0.gguf")
            check("an empty folder raises", False, "no exception")
        except FileNotFoundError as exc:
            check("an empty folder raises", True)
            check("the error carries the download link",
                  compat.MODEL_DOWNLOAD_URL in str(exc))
            check("the error names the folder to use", str(models) in str(exc))

        missing = models / "nope"
        try:
            find_gguf(missing, "")
            check("a missing folder raises", False, "no exception")
        except FileNotFoundError:
            check("a missing folder raises", True)

        # The trap: a browser saved it as "... (1).gguf", so the configured
        # name matches nothing, but the model is plainly right there.
        renamed = models / "Lilith_AI_8B_Q4_0 (1).gguf"
        renamed.write_bytes(b"GGUF")
        check("a lone .gguf is used despite the wrong configured name",
              find_gguf(models, "Lilith_AI_8B_Q4_0.gguf") == renamed)
        check("a lone .gguf is used when nothing is configured",
              find_gguf(models, "") == renamed)

        exact = models / "Lilith_AI_8B_Q4_0.gguf"
        exact.write_bytes(b"GGUF")
        check("the configured name wins once it exists",
              find_gguf(models, "Lilith_AI_8B_Q4_0.gguf") == exact)

        # Two models and no usable setting must not be guessed at.
        try:
            find_gguf(models, "something_else.gguf")
            check("an ambiguous folder raises", False, "no exception")
        except FileNotFoundError as exc:
            check("an ambiguous folder raises", True)
            check("the error lists both candidates",
                  "Lilith_AI_8B_Q4_0.gguf" in str(exc)
                  and "Lilith_AI_8B_Q4_0 (1).gguf" in str(exc))

        # Non-GGUF files must not be mistaken for a model.
        for stray in models.iterdir():
            stray.unlink()
        (models / "readme.txt").write_text("not a model", encoding="utf-8")
        try:
            find_gguf(models, "")
            check("a folder with no .gguf raises", False, "no exception")
        except FileNotFoundError:
            check("a folder with no .gguf raises", True)


def test_llama_backend_never_downloads() -> None:
    section("BUG: a missing model triggered a silent multi-gigabyte download")
    import inspect

    from modules import _llama_iface

    source = inspect.getsource(_llama_iface)
    check("from_pretrained is gone", "from_pretrained" not in source)
    check("the llama backend does not read hf_repo_id",
          "hf_repo_id" not in source)
    # hf_repo_id still exists for the transformers backend, which genuinely
    # does download. Removing it from config would break that one.
    check("hf_repo_id remains available for the hf backend",
          "hf_repo_id" in compat.CONFIG_DEFAULTS["ai_config"])


# --------------------------------------------------------------------------

def _run_wizard(answers: str, config, store, memory):
    """Drive run_setup with scripted stdin, writing only inside a temp dir."""
    import io

    from modules import first_run

    real_stdin, real_config_path = sys.stdin, compat.CONFIG_PATH
    sys.stdin = io.StringIO(answers)
    # save_config() defaults to the module-level CONFIG_PATH. Without this the
    # suite would overwrite the developer's own config.ini.
    compat.CONFIG_PATH = store.MEMORY_FILE.parent / "config.ini"
    devnull = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = devnull
    try:
        return first_run.run_setup(config, store, memory)
    finally:
        sys.stdout = real_stdout
        sys.stdin = real_stdin
        compat.CONFIG_PATH = real_config_path


def test_first_run_wizard() -> None:
    section("BUG: name asked after the model loaded; place and GPU undiscoverable")
    from modules import first_run, lilith_memory

    check("the wizard offers exactly the art sets that exist",
          set(first_run.PLACES) ==
          {p.name for p in compat.project_path("assets").iterdir() if p.is_dir()})

    with tempfile.TemporaryDirectory() as raw:
        scratch = Path(raw)
        counter = itertools.count()

        def fresh():
            # A directory per case: sharing one would let an earlier case's
            # memory.json satisfy the "cancelling writes nothing" assertion.
            case = scratch / f"case{next(counter)}"
            case.mkdir()
            config = compat.load_config(case / "absent.ini")
            config["ai_config"]["memory"] = str(case / "memory.json")
            store = lilith_memory.LilithMemory(compat.BASE_DIR, config)
            store.MEMORY_FILE = case / "memory.json"
            return config, store, store.load_memory()

        # name, place 2 (glass), compute 1 (GPU)
        config, store, memory = fresh()
        check("the wizard completes",
              _run_wizard("I AGREE\nAda\n2\n1\n", config, store, memory))
        check("the name is stored", store.get_user_name(memory) == "Ada")
        check("the chosen scene is stored", config["lilith_display"]["place"] == "glass")
        check("GPU offloads every layer",
              config["ai_config"]["n_gpu_layers"] == str(first_run.GPU_LAYERS_ALL))
        check("setup is marked complete",
              config["setup"].getboolean("complete") is True)
        check("current safety consent is recorded only after setup completes",
              config["safety"].get("consent_version") ==
              first_run.SAFETY_CONSENT_VERSION)

        # place 1 (room), compute 2 (CPU)
        config, store, memory = fresh()
        _run_wizard("I AGREE\nBo\n1\n2\n", config, store, memory)
        check("the other scene is stored", config["lilith_display"]["place"] == "room")
        check("CPU offloads nothing", config["ai_config"]["n_gpu_layers"] == "0")

        # Long names are capped the same way /nickname caps them.
        config, store, memory = fresh()
        _run_wizard("I AGREE\n" + "x" * 200 + "\n1\n2\n", config, store, memory)
        check("an absurd name is truncated", len(store.get_user_name(memory)) == 64)

        # Declining the initial adult safety gate must leave nothing behind.
        config, store, memory = fresh()
        before = dict(config["ai_config"])
        check("declining consent returns False",
              _run_wizard("no\n", config, store, memory) is False)
        check("declining consent writes no config",
              dict(config["ai_config"]) == before)
        check("declining consent writes no memory", not store.MEMORY_FILE.exists())
        check("declining consent leaves setup incomplete",
              config["setup"].getboolean("complete") is False)
        check("declining consent is not recorded",
              config["safety"].get("consent_version") == "0")

        # If the second file cannot be replaced, the first write is rolled back
        # so a normal save failure does not leave half a setup behind.
        config, store, memory = fresh()
        original_save_config = compat.save_config
        compat.save_config = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("simulated config failure")
        )
        try:
            completed = _run_wizard(
                "I AGREE\nCy\n2\n1\n", config, store, memory
            )
        finally:
            compat.save_config = original_save_config
        check("a config commit failure returns False", completed is False)
        check("a config commit failure rolls back a newly-created memory file",
              not store.MEMORY_FILE.exists())
        check("a config commit failure restores in-memory setup state",
              config["setup"].getboolean("complete") is False
              and config["safety"].get("consent_version") == "0"
              and config["lilith_display"].get("place") == "room")


def test_first_run_gating() -> None:
    section("BUG: an existing install would be interrogated on upgrade")
    from modules import first_run

    config = compat.load_config()

    original = config["setup"].get("complete", "false")
    original_consent = config["safety"].get("consent_version", "0")
    try:
        config["safety"]["consent_version"] = first_run.SAFETY_CONSENT_VERSION
        config["setup"]["complete"] = "true"
        check("a completed setup never re-runs",
              first_run.needs_setup(config, has_user_name=False) is False)

        config["setup"]["complete"] = "false"
        check("an install that knows your name is grandfathered in",
              first_run.needs_setup(config, has_user_name=True) is False)
        check("a fresh clone is asked",
              first_run.needs_setup(config, has_user_name=False) is True)

        config["setup"]["complete"] = "true"
        config["safety"]["consent_version"] = "0"
        check("an older install is not grandfathered past current consent",
              first_run.needs_setup(config, has_user_name=True) is True)
    finally:
        config["setup"]["complete"] = original
        config["safety"]["consent_version"] = original_consent

    check("the setup section has a default",
          "complete" in compat.CONFIG_DEFAULTS["setup"])
    check("the safety consent section has a default",
          compat.CONFIG_DEFAULTS["safety"].get("consent_version") == "0")


# --------------------------------------------------------------------------

def main() -> int:
    print("Lilith compatibility test suite")
    print("=" * 60)
    print(compat.describe_platform())

    tests = [
        test_paths_independent_of_cwd,
        test_config_defaults,
        test_config_numeric_ranges,
        test_backend_name_normalisation,
        test_openai_base_url,
        test_emotion_fallbacks,
        test_display_headless,
        test_memory_atomic_and_migration,
        test_conversation_management,
        test_existence_keywords,
        test_importing_lilith_has_no_side_effects,
        test_state_tag_extraction,
        test_emotion_ordering,
        test_state_vocabulary_is_consistent,
        test_history_trimming_and_payload,
        test_time_awareness,
        test_persona_guard,
        test_persona_guard_does_not_replace_replies,
        test_reply_save_failure,
        test_no_truncation_by_default,
        test_web_app_is_lazy,
        test_hf_remote_code_is_disabled,
        test_web_loopback_and_consent_boundaries,
        test_no_posix_only_constructs,
        test_windows_helpers_are_sane_everywhere,
        test_viewer_protocol,
        test_geometry_clamping,
        test_parent_alive,
        test_tui_safe_drawing,
        test_static_site_build,
        test_console_helpers,
        test_port_probe,
        test_theme_degradation,
        test_theme_curses_attributes,
        test_context_budget_trimming,
        test_memory_cross_process,
        test_blink_does_not_cancel_revert,
        test_parent_alive_access_denied,
        test_web_debug_panel_gate,
        test_companionship_reminders,
        test_gguf_resolution,
        test_llama_backend_never_downloads,
        test_first_run_wizard,
        test_first_run_gating,
    ]

    for test in tests:
        try:
            test()
        except Exception as exc:
            import traceback

            FAILED.append((test.__name__, f"{type(exc).__name__}: {exc}"))
            print(f"  FAIL {test.__name__} raised {type(exc).__name__}: {exc}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    for name, detail in FAILED:
        print(f"  - {name}: {detail}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
