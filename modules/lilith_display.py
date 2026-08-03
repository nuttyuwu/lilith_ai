"""
Drives the portrait window: which image, when, and for how long.

Fixes over the previous version:
  * The viewer process is started *before* the first connection attempt, and
    the client waits for it to listen. The old code connected first and
    launched second, so the initial connect always failed and the opening
    "thinking" frame silently never appeared.
  * Emotions resolve through a fallback chain instead of raising. Previously,
    ``place = glass`` combined with the CLI's extended emotions crashed the
    app outright: get_current_emotion(extended_emotions=True) can return
    happy/playful/confused/sleep/thinking_happy/thinking_sad, and none of
    those exist in assets/glass/.
  * The blink loop no longer dies permanently. It used
    ``while is_blinking and can_blink``, so the first 'smile' frame (which
    sets can_blink = False) ended the thread forever and Lilith never blinked
    again for the rest of the session.
  * Stale revert timers are cancelled with a token instead of a timestamp
    race, so a fast reply cannot be reverted to idle mid-sentence.
  * ``headless`` mode, so the web UI and CI can run with no display at all.
  * ``close()`` shuts the viewer down instead of orphaning it.
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import modules._viewer_iface as viewer_module
from modules import compat

logger = logging.getLogger(__name__)

# Preferred image for each emotion, then progressively safer substitutes.
# Lets 'room' and 'glass' share one emotion vocabulary despite having
# different asset sets, and makes adding a new place a drop-in operation.
EMOTION_FALLBACKS: dict[str, tuple[str, ...]] = {
    "idle":           ("idle",),
    "blinking":       ("blinking", "idle"),
    "smile":          ("smile", "happy", "idle"),
    "happy":          ("happy", "smile", "idle"),
    "playful":        ("playful", "cheeky", "smile", "idle"),
    "cheeky":         ("cheeky", "playful", "smile", "idle"),
    "talking":        ("talking", "smile", "idle"),
    "sad":            ("sad", "thinking_sad", "dissapointed", "idle"),
    "dissapointed":   ("dissapointed", "sad", "thinking_sad", "idle"),
    "confused":       ("confused", "thinking", "thinking_sad", "idle"),
    "sleep":          ("sleep", "idle"),
    "thinking":       ("thinking", "thinking_happy", "confused", "idle"),
    "thinking_happy": ("thinking_happy", "thinking", "smile", "idle"),
    "thinking_sad":   ("thinking_sad", "thinking", "sad", "idle"),
}


class LilithDisplay:
    def __init__(self, base_dir=None, config=None, headless: bool = False):
        config = config if config is not None else compat.load_config()
        self.config = config
        self.base_dir = Path(base_dir) if base_dir else compat.BASE_DIR

        section = config["lilith_display"]
        self.ASSETS_PATH = compat.project_path(section.get("assets_path", "assets"))
        self.VIEWER_SCRIPT = compat.project_path(
            section.get("display_path", "modules/viewer.py")
        )
        self.REVERT_DELAY = section.getint("revert_delay", fallback=5)
        self.BLINK_MIN = section.getfloat("blink_min_interval", fallback=4)
        self.BLINK_MAX = section.getfloat("blink_max_interval", fallback=8)
        self.BLINK_DURATION = section.getfloat("blink_duration", fallback=0.1)
        self.place = section.get("place", "room")
        self.default_state = section.get("default_state", "idle")

        self.LAST_SHOWN_STATE = None
        self.can_blink = True
        self.is_blinking = False

        self._revert_token = 0
        self._state_lock = threading.RLock()
        self._closed = False
        self._process: subprocess.Popen | None = None

        # Explicit config switch, or no GUI available at all.
        self.headless = (
            headless
            or not section.getboolean("enable", fallback=True)
            or self._no_display_available()
        )
        self._available_states = self._scan_assets()

        if self.headless:
            self.viewer = None
            logger.info("LilithDisplay running headless")
            return

        host = config["viewer_socket"].get("host", "127.0.0.1")
        port = config["viewer_socket"].getint("port", fallback=8888)
        timeout = config["viewer_socket"].getfloat("connect_timeout", fallback=10)

        self.viewer = viewer_module.LilithClient(host=host, port=port)

        # Start first, then wait -- the original did the reverse.
        if not compat.port_in_use(host, port):
            self._spawn_viewer()

        if not self.viewer.wait_for_server(timeout=timeout):
            logger.warning("Portrait viewer unavailable; continuing without it")
            print("(Lilith's portrait could not open -- continuing in text only.)")
            self.headless = True
            self.viewer = None
        else:
            logger.info("LilithDisplay connected to viewer on %s:%s", host, port)

    # -- environment ------------------------------------------------------

    @staticmethod
    def _no_display_available() -> bool:
        """On Linux, a missing DISPLAY/WAYLAND_DISPLAY means no GUI (e.g. SSH, WSL without WSLg)."""
        if compat.IS_WINDOWS or compat.IS_MACOS:
            return False
        return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def _scan_assets(self) -> set[str]:
        place_dir = self.ASSETS_PATH / self.place
        if not place_dir.is_dir():
            logger.error("Asset folder missing: %s", place_dir)
            return set()
        return {p.stem for p in place_dir.glob("*.png")}

    def _spawn_viewer(self) -> None:
        if not self.VIEWER_SCRIPT.exists():
            logger.error("Viewer script not found: %s", self.VIEWER_SCRIPT)
            return

        command = [
            compat.gui_python(),  # pythonw.exe on Windows: no console flash
            str(self.VIEWER_SCRIPT),
            "--parent-pid", str(os.getpid()),
        ]
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "cwd": str(compat.BASE_DIR),
        }
        if compat.IS_WINDOWS:
            # Keep a console window from flashing up beside the portrait.
            # DETACHED_PROCESS is deliberately not combined with this: the two
            # flags conflict, and detaching is unnecessary now that the viewer
            # watches its parent PID and exits on its own.
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True

        try:
            self._process = subprocess.Popen(command, **kwargs)
            logger.info("Viewer process started (pid=%s)", self._process.pid)
        except OSError as exc:
            logger.error("Could not start viewer: %s", exc)

    # -- state resolution -------------------------------------------------

    def resolve_state(self, state: str) -> str | None:
        """Map a requested emotion onto an image this place actually has."""
        for candidate in EMOTION_FALLBACKS.get(state, (state, "idle")):
            if candidate in self._available_states:
                if candidate != state:
                    logger.debug("Emotion %r not in %r; using %r",
                                 state, self.place, candidate)
                return candidate
        # Last resort: anything at all, so we never raise on a cosmetic detail.
        if self._available_states:
            return sorted(self._available_states)[0]
        return None

    def image_for(self, state: str) -> Path | None:
        resolved = self.resolve_state(state)
        if resolved is None:
            return None
        return self.ASSETS_PATH / self.place / f"{resolved}.png"

    # -- public API -------------------------------------------------------

    def show_lilith(self, state: str, schedule_revert: bool = True,
                    transient: bool = False) -> bool:
        """Show an emotion.

        ``transient`` marks a frame that is an overlay rather than a real
        change of mood -- a blink. Those must not touch the revert bookkeeping:
        bumping the token on every call meant any blink landing between an
        emotion and its revert silently cancelled the timer, and since the
        blink restores the previous state with schedule_revert=False, no new
        timer replaced it. With the default 5s revert and a 4-8s blink, that
        fired most turns and left her stuck on the last emotion.
        """
        if not state:
            return False
        with self._state_lock:
            if getattr(self, "_closed", False):
                return False
            if self.headless or self.viewer is None:
                self.LAST_SHOWN_STATE = state
                if not transient:
                    self._revert_token += 1
                return False

            image = self.image_for(state)
            if image is None:
                logger.warning(
                    "No usable asset for state %r in place %r", state, self.place
                )
                return False

            # Blinking on top of 'smile' looks wrong in the glass scene.
            self.can_blink = not (self.place == "glass" and state == "smile")

            # Keep the viewer reference valid through the send. close() takes
            # this same lock before disconnecting or clearing it.
            ok = self.viewer.set_image_path(str(image))
            self.LAST_SHOWN_STATE = state
            if not transient:
                self._revert_token += 1
            token = self._revert_token

            if ok and schedule_revert and state != self.default_state:
                def revert_after_delay() -> None:
                    time.sleep(self.REVERT_DELAY)
                    with self._state_lock:
                        if (token != self._revert_token
                                or getattr(self, "_closed", False)):
                            return  # superseded by a newer state or shutdown
                        # Validation and transition remain under one RLock, so
                        # a new mood cannot land in the gap before idle.
                        self.show_lilith(
                            self.default_state, schedule_revert=False
                        )

                threading.Thread(target=revert_after_delay, daemon=True).start()

            return ok

    def set_blinking(self, enable: bool) -> None:
        with self._state_lock:
            if not enable:
                self.is_blinking = False
                return
            if (self.headless or self.is_blinking
                    or getattr(self, "_closed", False)):
                return
            if "blinking" not in self._available_states:
                logger.info(
                    "No blinking asset in place %r; skipping blink loop", self.place
                )
                return

            self.is_blinking = True

        def blink_loop() -> None:
            while True:
                time.sleep(random.uniform(self.BLINK_MIN, self.BLINK_MAX))
                with self._state_lock:
                    if (not self.is_blinking
                            or getattr(self, "_closed", False)):
                        return
                    # Pause, don't exit, when blinking is temporarily suppressed.
                    if not self.can_blink:
                        continue
                    previous = self.LAST_SHOWN_STATE or self.default_state
                    if previous == "blinking":
                        continue
                    token = self._revert_token
                    self.show_lilith(
                        "blinking", schedule_revert=False, transient=True
                    )
                time.sleep(self.BLINK_DURATION)
                with self._state_lock:
                    if (self.is_blinking
                            and not getattr(self, "_closed", False)
                            and token == self._revert_token
                            and self.LAST_SHOWN_STATE == "blinking"):
                        # Restore only if no real state arrived during the blink.
                        self.show_lilith(
                            previous, schedule_revert=False, transient=True
                        )

        threading.Thread(target=blink_loop, daemon=True).start()

    def close(self) -> None:
        """Disconnect and stop the viewer instead of leaving it orphaned."""
        with self._state_lock:
            self._closed = True
            self.is_blinking = False
            self._revert_token += 1
            viewer = self.viewer
            self.viewer = None
            process = self._process
            self._process = None

        if viewer is not None:
            viewer.disconnect()
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False
