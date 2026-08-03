#!/usr/bin/env python3
"""
Lilith -- web interface.

Fixes over the previous version:
  * No longer does ``from lilith import ...``. That import pulled in
    ``EXISTENCE_KEYWORDS`` (which never existed there -- instant ImportError),
    and as a side effect ran lilith.py's argparse against gunicorn's flags and
    spawned a Tk portrait window on a headless server.
  * Builds its own app with an application factory, so gunicorn, waitress and
    ``python web_lilith.py`` all work from the same code.
  * The display runs headless here, so no GUI is required.
  * ``request.json`` raised 415 on requests without a JSON content type; it
    now uses ``get_json(silent=True)`` and validates.
  * Emotions are clamped to the images that actually exist in static/, so the
    portrait cannot 404.
  * Serves with waitress on Windows, where gunicorn does not run at all.
"""

from __future__ import annotations

import argparse
import ipaddress
import logging
import os
import sys
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request

from modules import compat, safety
from modules.lilith_ai import EXISTENCE_KEYWORDS, LilithAI

logger = logging.getLogger(__name__)

BASE_DIR = str(compat.BASE_DIR)
SAFETY_CONSENT_HEADER = "X-Lilith-Safety-Consent"
SAFETY_CONSENT_VERSION = str(safety.DISCLOSURE_VERSION)
_LOCAL_ONLY_ERROR = "Lilith's web interface is available on localhost only."


def is_loopback_host(value: str | None, *, allow_port: bool = False) -> bool:
    """Return whether *value* names a literal loopback host (or localhost).

    Bind addresses never include a port. HTTP Host values may, including the
    bracketed IPv6 form ``[::1]:5000``. Hostnames other than ``localhost`` are
    intentionally rejected instead of resolved: DNS and hosts-file mappings
    are not a trustworthy security boundary.
    """
    text = str(value or "").strip()
    if not text or any(char in text for char in "/?#@"):
        return False

    candidate = text
    if text.startswith("["):
        closing = text.find("]")
        if closing < 0:
            return False
        candidate = text[1:closing]
        suffix = text[closing + 1:]
        if suffix:
            if (not allow_port or not suffix.startswith(":")
                    or not suffix[1:].isdigit()):
                return False
    elif allow_port and text.count(":") == 1:
        candidate, port = text.rsplit(":", 1)
        if not candidate or not port.isdigit():
            return False

    if candidate.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def _wsgi_request_is_loopback(environ: dict) -> bool:
    """Validate both the network peer and HTTP Host at the WSGI boundary."""
    peer = environ.get("REMOTE_ADDR", "")
    host = environ.get("HTTP_HOST") or environ.get("SERVER_NAME", "")
    return (is_loopback_host(peer)
            and is_loopback_host(host, allow_port=True))


def _local_only_wsgi_response(start_response):
    """Return a detail-free WSGI denial without constructing the AI backend."""
    body = (f'{{"error":"{_LOCAL_ONLY_ERROR}"}}\n').encode("utf-8")
    start_response("403 Forbidden", [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def loopback_cors_origins(value: str | None) -> list[str] | None:
    """Validate a comma-separated CORS allowlist.

    ``None`` means the requested policy was unsafe and must be disabled. Since
    the bundled API is loopback-only, allowing a public website (especially
    ``*``) would let that site drive a user's localhost service from the
    browser with the publicly known consent header.
    """
    raw = str(value or "").strip()
    if not raw:
        return []

    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    if not origins or "*" in origins:
        return None

    for origin in origins:
        try:
            parsed = urlsplit(origin)
            # Accessing .port validates its syntax and range.
            _ = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or not is_loopback_host(parsed.hostname)
        ):
            return None
    return origins

# Emotions the bundled static/*.png set can actually show.
WEB_EMOTIONS = {
    "idle", "smile", "talking", "thinking", "sad", "cheeky",
    "dissapointed", "blinking",
}
WEB_EMOTION_FALLBACK = {
    "happy": "smile",
    "playful": "cheeky",
    "confused": "thinking",
    "sleep": "idle",
    "thinking_happy": "thinking",
    "thinking_sad": "sad",
}


def clamp_emotion(emotion: str) -> str:
    if emotion in WEB_EMOTIONS:
        return emotion
    return WEB_EMOTION_FALLBACK.get(emotion, "idle")


def create_app(config=None) -> Flask:
    """Application factory: usable by gunicorn, waitress and __main__ alike."""
    config = config if config is not None else compat.load_config()
    compat.setup_logging(config)

    app = Flask(
        __name__,
        static_folder=str(compat.project_path("static")),
        template_folder=str(compat.project_path("templates")),
    )

    # An unbounded request body is buffered in full and then fed to the model.
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    @app.before_request
    def require_loopback_request():
        # Binding checks in main() do not protect application-factory users or
        # a WSGI server launched with its own --bind flag. Checking both values
        # blocks direct LAN clients and ordinary local tunnel/reverse-proxy
        # forwarding (loopback peer, public Host).
        if (not is_loopback_host(request.remote_addr)
                or not is_loopback_host(request.host, allow_port=True)):
            return jsonify({"error": _LOCAL_ONLY_ERROR}), 403

    # The web UI never opens a portrait window.
    lilith = LilithAI(None, config, compat.BASE_DIR)

    # No wildcard by default. The previous default of "*" meant any website
    # you visited could talk to a Lilith running on your machine and read your
    # conversation. Cross-origin access is now opt-in.
    requested_origins = (os.getenv("CORS_ORIGINS")
                         or config["web"].get("cors_origins", "")).strip()
    origins = loopback_cors_origins(requested_origins)
    if origins:
        try:
            from flask_cors import CORS

            CORS(app, resources={
                path: {"origins": origins}
                for path in (r"/chat", r"/nickname", r"/health")
            })
        except ImportError:
            logger.warning("flask-cors not installed; cross-origin requests will fail")
    elif origins is None:
        logger.error(
            "Ignoring unsafe [web] cors_origins=%r. Only explicit http(s) "
            "loopback origins are supported; wildcard/public origins are blocked.",
            requested_origins,
        )
    else:
        logger.info(
            "CORS disabled (same-origin only). Only loopback origins may be enabled."
        )

    app.config["LILITH"] = lilith

    # The debug panel renders the full persona and local file paths into the
    # page. That is ~14 KB of system prompt sent to the browser on every load,
    # and readable by any local browser that can reach the server. Opt in with
    # [web] debug_panel = true only while debugging.
    show_debug = config["web"].getboolean("debug_panel", fallback=False)

    @app.route("/")
    def home():
        history = lilith.get_history(limit=20)
        context = {
            "user_name": lilith.get_user_name(),
            "user_name_set": lilith.has_user_name(),
            "safety_consent_version": SAFETY_CONSENT_VERSION,
        }
        if show_debug:
            # "memory" is read only by the debug panel in index.html, but it
            # used to be set unconditionally -- so with debug_panel = false
            # the persona was correctly withheld while the last 20 turns of
            # conversation were still embedded in the page for every visitor,
            # hidden behind nothing but a CSS display:none.
            context["memory"] = history
            context["persona"] = lilith.persona
            context["debug"] = {
                "cwd": os.getcwd(),
                "base_dir": BASE_DIR,
                "persona_file": str(lilith.Lilith_mem.PERSONA_FILE),
                "memory_file": str(lilith.Lilith_mem.MEMORY_FILE),
                "persona_length": len(lilith.persona),
                "memory_count": len(history),
            }
        else:
            context["persona"] = None
        return render_template("index.html", **context)

    @app.route("/health")
    def health():
        return jsonify({
            "status": "ok",
            "platform": compat.describe_platform(),
            "backend": config["server"].get("server_ai"),
            "conversation": lilith.get_current_conversation_name(),
        })

    @app.route("/nickname", methods=["GET", "POST"])
    def nickname():
        if request.method == "GET":
            return jsonify({"user_name": lilith.get_user_name()})

        payload = request.get_json(silent=True) or {}
        new_name = str(payload.get("user_name") or "").strip()
        if not new_name:
            return jsonify({"error": "nickname required"}), 400
        lilith.set_user_name(new_name[:64])
        return jsonify({"user_name": lilith.get_user_name()})

    @app.route("/chat", methods=["POST"])
    def chat():
        # This is a per-browser acknowledgement, independent of the CLI's
        # persisted [safety] consent_version. A fresh config records 0 until
        # CLI consent, while the web disclosure separately issues the current
        # version from modules.safety.
        if request.headers.get(SAFETY_CONSENT_HEADER) != SAFETY_CONSENT_VERSION:
            return jsonify({
                "error": "Safety consent is required before chatting.",
                "consent_version": SAFETY_CONSENT_VERSION,
            }), 428

        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message") or "").strip()
        if not message:
            return jsonify({"reply": "", "emotion": "idle",
                            "error": "message required"}), 400
        if len(message) > 8000:
            # /nickname already clamps to 64; this one had no bound at all.
            return jsonify({"reply": "", "emotion": "idle",
                            "error": "message too long"}), 413

        try:
            reply = lilith.lilith_reply(message)
        except Exception:
            # Log the detail, return a generic message: backend exception text
            # can carry the configured base_url, local filesystem paths and,
            # in some client error strings, the api_key from config.ini.
            logger.exception("Reply failed")
            return jsonify({"reply": "...", "emotion": "sad",
                            "error": "Lilith could not answer. "
                                     "See app.log for details."}), 502

        emotion = lilith.get_current_emotion()
        if lilith.is_existence_question(message):
            # Asking what Lilith is must not be framed as emotionally harmful
            # or punished with a disappointed reaction.
            emotion = "thinking"

        return jsonify({"reply": reply, "emotion": clamp_emotion(emotion)})

    @app.errorhandler(500)
    def internal_error(exc):
        # Exception strings can contain local paths, backend URLs, or a
        # credential echoed by a client library. Keep detail in the local log,
        # never in the HTTP response.
        logger.error(
            "Unhandled web request error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return render_template(
            "error.html", error="Unexpected server error. See app.log for details."
        ), 500

    return app


def main(argv: list[str] | None = None) -> int:
    compat.enable_utf8_console()
    config = compat.load_config()

    parser = argparse.ArgumentParser(description="Lilith web interface")
    parser.add_argument("--host", default=config["web"].get("host", "127.0.0.1"),
                        help="loopback bind address (localhost only)")
    parser.add_argument("--port", type=int,
                        default=config["web"].getint("port", fallback=5000))
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    # None of the routes authenticate callers. Refuse every non-loopback bind,
    # not only the especially dangerous Werkzeug-debugger combination.
    if not is_loopback_host(args.host):
        print(f"Refusing --host {args.host}: Lilith's web interface has no\n"
              f"authentication and is localhost-only. Use --host 127.0.0.1.",
              file=sys.stderr)
        return 2

    try:
        app = create_app(config)
    except Exception as exc:
        # The terminal entry point catches this and prints a friendly hint;
        # here it used to dump a raw traceback for the identical failure.
        logger.exception("Could not initialise the AI backend")
        print(f"\nLilith could not wake up:\n\n{exc}\n", file=sys.stderr)
        print("Run 'python lilith.py doctor' for a setup check.", file=sys.stderr)
        return 1

    if args.debug:
        app.run(host=args.host, port=args.port, debug=True)
        return 0

    display_host = (f"[{args.host}]"
                    if ":" in args.host and not args.host.startswith("[")
                    else args.host)
    listen_url = f"http://{display_host}:{args.port}"

    # gunicorn is POSIX-only; waitress is the cross-platform equivalent.
    try:
        from waitress import serve

        print(f"Lilith is listening on {listen_url}")
        serve(app, host=args.host, port=args.port, threads=4)
    except ImportError:
        logger.info("waitress not installed; using Flask's development server")
        print(f"Lilith is listening on {listen_url}")
        app.run(host=args.host, port=args.port, debug=False)
    return 0


class _LazyWSGI:
    """WSGI entry point that builds the app on the first request.

    ``gunicorn web_lilith:app`` needs a module-level ``app``, but building it
    at import time would load the AI backend during import -- exactly the
    side-effect-on-import problem this rewrite removed from lilith.py. A
    failing backend would then surface as an opaque worker boot error instead
    of a request-time message.

    Usage:
        gunicorn --bind 127.0.0.1:5000 'web_lilith:app'  (Linux)
        waitress-serve --listen=127.0.0.1:5000 web_lilith:app
    """

    def __init__(self):
        self._app = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._app is None:
            with self._lock:
                if self._app is None:
                    self._app = create_app()
        return self._app

    def __call__(self, environ, start_response):
        # Enforce this before _ensure(): a remote request must not initialise a
        # model or receive backend/platform details while being rejected.
        if not _wsgi_request_is_loopback(environ):
            return _local_only_wsgi_response(start_response)
        return self._ensure()(environ, start_response)


app = _LazyWSGI()


if __name__ == "__main__":
    sys.exit(main())
