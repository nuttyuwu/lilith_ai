#!/usr/bin/env python3
"""
Lilith setup check.

Run this first whenever something does not work:

    python lilith.py doctor      (or)      python doctor.py

It reports on Python, the GUI stack, the selected AI backend, assets, file
permissions and ports -- with the fix for each problem written out for the
platform you are actually on. Exists because "it works on my Linux box" and
"it works on my Windows 11 box" are different claims, and the gap between them
was previously only discoverable by reading a traceback.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path

from modules import compat
from modules._iface import BACKENDS, normalise_backend

OK, WARN, FAIL = "ok", "warn", "fail"
_MARKS = {OK: "[ ok ]", WARN: "[warn]", FAIL: "[FAIL]"}

_results: list[tuple[str, str, str]] = []


def report(status: str, title: str, detail: str = "") -> None:
    _results.append((status, title, detail))
    print(f"{_MARKS[status]} {title}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")


# pip name -> import name, for the cases where they differ.
IMPORT_NAMES = {
    "llama-cpp-python": "llama_cpp",
    "huggingface_hub": "huggingface_hub",
    "flask-cors": "flask_cors",
    "windows-curses": "curses",
    "pillow": "PIL",
}


def has_module(name: str) -> bool:
    module = IMPORT_NAMES.get(name, name.replace("-", "_"))
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def section(title: str) -> None:
    print(f"\n--- {title} ---")


# --------------------------------------------------------------------------

def check_python() -> None:
    ok, message = compat.check_python_version()
    report(OK if ok else FAIL, message,
           "" if ok else "Install Python 3.10 or newer from python.org.")
    report(OK, compat.describe_platform())
    report(OK, f"Project root: {compat.BASE_DIR}")

    # llama-cpp-python only publishes wheels for CPython 3.10-3.12. On 3.13+
    # pip does not error -- it quietly starts a source build that needs the
    # Visual Studio C++ workload and takes about fifteen minutes.
    if sys.version_info >= (3, 13):
        try:
            backend = normalise_backend(
                compat.load_config()["server"].get("server_ai", "")
            )
        except Exception:
            backend = ""
        version = ".".join(str(part) for part in sys.version_info[:3])
        report(FAIL if backend == "llama" else WARN,
               f"Python {version} is newer than the llama.cpp wheels support "
               f"(3.10-3.12)",
               "llama-cpp-python has no wheels for this version; pip will try\n"
               "a source build needing Visual Studio Build Tools. Rebuild the\n"
               "venv with 3.12:   rmdir /s venv  &&  py -3.12 -m venv venv")

    # A venv built FROM the Store Python keeps the WindowsApps path in
    # base_prefix even though sys.executable points into the venv.
    store_paths = (sys.executable, getattr(sys, "base_prefix", ""))
    if compat.IS_WINDOWS and any("windowsapps" in str(p).lower() for p in store_paths):
        report(WARN, "Running under the Microsoft Store Python",
               "This build is sandboxed and often cannot write outside its own\n"
               "folder or load Tk properly. Install Python from python.org and\n"
               "disable the stub under Settings > Apps > Advanced app settings >\n"
               "App execution aliases > python.exe.")

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        report(OK, f"Virtual environment active ({Path(sys.prefix).name})")
    else:
        activate = (
            "PowerShell:      .\\venv\\Scripts\\Activate.ps1\n"
            "  Command Prompt: venv\\Scripts\\activate.bat"
            if compat.IS_WINDOWS else "source venv/bin/activate"
        )
        report(WARN, "Not running inside a virtual environment",
               f"Recommended:\n  python -m venv venv\n  {activate}")


def check_config(config) -> None:
    if compat.CONFIG_PATH.exists():
        report(OK, f"config.ini found ({compat.CONFIG_PATH})")
    else:
        report(WARN, "config.ini missing",
               "It will be created from config.example.ini on first run.")

    persona = compat.project_path(config["ai_config"]["persona"])
    report(OK if persona.exists() else FAIL,
           f"Persona file: {persona.name}",
           "" if persona.exists() else f"Expected at {persona}")

    memory = compat.project_path(config["ai_config"]["memory"])
    target = memory if memory.exists() else memory.parent
    if os.access(target, os.W_OK):
        report(OK, f"Memory is writable ({memory.name})")
    else:
        report(FAIL, "Cannot write memory.json",
               f"No write permission for {target}")


def check_assets(config) -> None:
    from modules.lilith_display import EMOTION_FALLBACKS

    assets = compat.project_path(config["lilith_display"].get("assets_path", "assets"))
    place = config["lilith_display"].get("place", "room")
    place_dir = assets / place

    if not place_dir.is_dir():
        available = ([p.name for p in assets.iterdir() if p.is_dir()]
                     if assets.is_dir() else [])
        report(FAIL, f"Asset scene '{place}' not found",
               f"Looked in {place_dir}\n"
               f"Available scenes: {', '.join(available) or 'none'}")
        return

    present = {p.stem for p in place_dir.glob("*.png")}
    report(OK, f"Scene '{place}': {len(present)} images")

    # Every emotion must resolve to something, or the portrait breaks.
    unresolvable = [
        emotion for emotion, chain in EMOTION_FALLBACKS.items()
        if not any(candidate in present for candidate in chain)
    ]
    if unresolvable:
        report(WARN, "Some emotions have no image in this scene",
               f"{', '.join(sorted(unresolvable))}\n"
               "They will fall back to the first available image.")
    else:
        report(OK, "Every emotion resolves to an image")

    if "idle" not in present:
        report(WARN, "No idle.png in this scene",
               "idle is the resting state; add one for best results.")


def check_gui(config) -> None:
    if not config["lilith_display"].getboolean("enable", fallback=True):
        report(OK, "Portrait window disabled in config (headless mode)")
        return

    try:
        import tkinter  # noqa: F401
        report(OK, "tkinter available")
    except ImportError:
        hint = ("Re-run the python.org installer and enable 'tcl/tk and IDLE'."
                if compat.IS_WINDOWS else
                "sudo apt install python3-tk    (Debian/Ubuntu)\n"
                "sudo dnf install python3-tkinter    (Fedora)")
        report(FAIL, "tkinter missing", hint)

    if has_module("PIL"):
        try:
            from PIL import ImageTk  # noqa: F401
            report(OK, "Pillow with ImageTk available")
        except ImportError:
            hint = ("python -m pip install --force-reinstall pillow"
                    if compat.IS_WINDOWS else
                    "sudo apt install python3-pil.imagetk")
            report(FAIL, "Pillow is installed but ImageTk is not", hint)
    else:
        report(FAIL, "Pillow missing", "pip install pillow")

    if not compat.IS_WINDOWS and not compat.IS_MACOS:
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            report(OK, "Display server detected")
        else:
            report(WARN, "No DISPLAY or WAYLAND_DISPLAY",
                   "Lilith will run text-only. Under WSL, install WSLg or run\n"
                   "the Windows build instead.")

    host = config["viewer_socket"].get("host", "127.0.0.1")
    port = config["viewer_socket"].getint("port", fallback=8888)
    if compat.port_in_use(host, port):
        report(WARN, f"Port {port} is already in use",
               "A viewer may still be running, or another app has the port.\n"
               "Change [viewer_socket] port if this is not Lilith.")
    else:
        report(OK, f"Viewer port {port} is free")


def check_terminal_ui() -> None:
    if has_module("curses"):
        report(OK, "curses available (config and conversation editors)")
    elif compat.IS_WINDOWS:
        report(WARN, "curses missing",
               "python -m pip install windows-curses\n"
               "Without it the editors use a simpler numbered-menu mode.")
    else:
        report(WARN, "curses missing", "Unusual on Linux; install python3-full.")

    compat.enable_utf8_console()
    if compat.supports_unicode():
        report(OK, "Console can display Unicode")
    else:
        report(WARN, "Console cannot display Unicode",
               "Lilith will substitute ASCII. Windows Terminal handles this\n"
               "better than the classic console host.")


def _http_ok(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code} (server is up)"
    except Exception as exc:
        return False, str(exc)


def check_backend(config) -> None:
    raw = config["server"].get("server_ai", "ollama")
    backend = normalise_backend(raw)

    if backend not in BACKENDS:
        report(FAIL, f"Unknown backend '{raw}'",
               f"Valid values: {', '.join(sorted(BACKENDS))}")
        return

    module_name, _cls, label, package = BACKENDS[backend]
    report(OK, f"Selected backend: {label}")

    missing = [name for name in package.split() if not has_module(name)]
    if missing:
        hint = f"pip install {' '.join(missing)}"
        if "llama-cpp-python" in missing and compat.IS_WINDOWS:
            hint += ("\nOn Windows, prebuilt wheels avoid needing a C++ compiler:\n"
                     "  pip install llama-cpp-python --extra-index-url "
                     "https://abetlen.github.io/llama-cpp-python/whl/cpu")
        report(FAIL, f"{label} dependency not installed: {', '.join(missing)}", hint)
    else:
        report(OK, f"{label} Python package installed")

    if backend == "ollama":
        host = (config["server"].get("ollama_host") or "http://127.0.0.1:11434").rstrip("/")
        up, detail = _http_ok(f"{host}/api/tags")
        model = config["ai_config"].get("ai_model")
        report(OK if up else WARN, f"Ollama server at {host}",
               "" if up else f"{detail}\nStart it with:  ollama serve\n"
                             f"Then:  ollama pull {model}")

    elif backend in {"lm studio", "openai"}:
        from modules._openai_iface import normalise_base_url

        url = normalise_base_url(config["server"].get("base_url", ""))
        raw_url = config["server"].get("base_url", "")
        if not raw_url.rstrip("/").endswith("/v1"):
            report(WARN, "base_url is missing the /v1 suffix",
                   f"Configured: {raw_url}\nWill be used as: {url}\n"
                   "Set it explicitly in config.ini to avoid surprises.")
        up, detail = _http_ok(f"{url}/models")
        report(OK if up else WARN, f"Model server at {url}",
               "" if up else f"{detail}\nIn LM Studio: Developer -> Start Server, "
                             "and load a model.")

    elif backend == "llama":
        # Mirrors modules/_llama_iface.find_gguf, which is what will actually
        # run. Reporting "missing" for a model the backend would happily load
        # under a different filename would send people hunting for nothing.
        from modules._llama_iface import find_gguf

        model_dir = compat.project_path(config["ai_config"].get("model_path", "models"))
        configured = config["ai_config"].get("local_model", "").strip()
        try:
            model_file = find_gguf(model_dir, configured)
        except FileNotFoundError as exc:
            report(FAIL, "No GGUF model found", str(exc))
        else:
            size_gb = model_file.stat().st_size / 1024 ** 3
            detail = ""
            if configured and model_file.name != configured:
                detail = (f"[ai_config] local_model says {configured!r}; using\n"
                          f"{model_file.name} instead, as it is the only model present.")
            report(OK, f"GGUF model present ({model_file.name}, {size_gb:.1f} GB)", detail)

    elif backend == "hf":
        if has_module("torch"):
            try:
                import torch
                if torch.cuda.is_available():
                    report(OK, f"CUDA available ({torch.cuda.get_device_name(0)})")
                else:
                    report(WARN, "torch installed, no CUDA -- running on CPU",
                           "Expect slow replies. A CPU-only torch build is a much\n"
                           "smaller download: see https://pytorch.org/")
            except Exception as exc:
                report(WARN, f"Could not query torch: {exc}")
        else:
            report(FAIL, "torch missing", "See https://pytorch.org/ for the right build.")


def check_web(config) -> None:
    report(OK if has_module("flask") else WARN, "Flask" +
           ("" if has_module("flask") else " missing"),
           "" if has_module("flask") else "pip install -r requirements.txt")

    if not has_module("flask_cors"):
        report(WARN, "flask-cors missing", "pip install flask-cors")

    if has_module("waitress"):
        report(OK, "waitress available (cross-platform web server)")
    elif compat.IS_WINDOWS:
        report(WARN, "waitress missing",
               "pip install waitress -- gunicorn does not run on Windows.")
    elif not has_module("gunicorn"):
        report(WARN, "No production web server installed",
               "pip install waitress    (or gunicorn)\n"
               "web_lilith.py falls back to Flask's development server.")

    if compat.IS_WINDOWS and has_module("gunicorn"):
        report(WARN, "gunicorn is installed but cannot run on Windows",
               "Use waitress instead; web_lilith.py picks it up automatically.")

    port = config["web"].getint("port", fallback=5000)
    if compat.port_in_use("127.0.0.1", port):
        report(WARN, f"Web port {port} is already in use")


def check_translator(config) -> None:
    if not config["translator"].getboolean("enable", fallback=False):
        report(OK, "Translator disabled")
        return
    missing = [name for name in ("transformers", "torch", "sentencepiece")
               if not has_module(name)]
    if missing:
        report(FAIL, f"Translator enabled but missing: {', '.join(missing)}",
               "pip install -r requirements-translate.txt")
    else:
        report(OK, "Translator dependencies installed")


# --------------------------------------------------------------------------

def main() -> int:
    compat.enable_utf8_console()
    print("Lilith setup check")
    print("=" * 52)

    config = compat.load_config()

    # A malformed value (enable = yes please) makes getboolean/getint raise,
    # and an unguarded raise here aborted the whole report partway through --
    # in the one tool whose entire job is to explain a broken config. Each
    # check is isolated so a bad value is reported as a failure and the rest
    # of the report still runs.
    checks: list[tuple[str, object]] = [
        ("Environment", check_python),
        ("Configuration", lambda: check_config(config)),
        ("Assets", lambda: check_assets(config)),
        ("Portrait window", lambda: check_gui(config)),
        ("Terminal UI", check_terminal_ui),
        ("AI backend", lambda: check_backend(config)),
        ("Web interface", lambda: check_web(config)),
        ("Translator", lambda: check_translator(config)),
    ]
    for title, run in checks:
        section(title)
        try:
            run()
        except Exception as exc:
            report(FAIL, f"This check could not run: {exc}",
                   "Usually a malformed value in config.ini. Fix it by hand or\n"
                   "delete config.ini to regenerate it from config.example.ini.")

    failures = sum(1 for status, _, _ in _results if status == FAIL)
    warnings = sum(1 for status, _, _ in _results if status == WARN)

    print("\n" + "=" * 52)
    if failures:
        print(f"{failures} problem(s) will stop Lilith from running, "
              f"{warnings} warning(s).")
        return 1
    if warnings:
        print(f"No blocking problems, {warnings} warning(s). Lilith should run.")
        return 0
    print("Everything checks out. Lilith is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
