"""
Client side of the viewer protocol.

Wire format: 4-byte little-endian length, then a UTF-8 path, then a 1-byte ack.

Fixes over the previous version:
  * Sends are serialised with a lock. The blink thread, the revert timer and
    the main thread all call ``set_image_path`` on one socket; without a lock
    their writes interleave and desynchronise the length-prefixed stream,
    which showed up as the portrait freezing on a random frame.
  * ``struct.pack('I', ...)`` used native size *and* alignment. It is now
    explicitly ``'<I'`` so the protocol is defined rather than
    architecture-dependent.
  * Timeouts on connect and recv, so a dead viewer cannot hang Lilith.
  * ``wait_for_server`` lets the caller block until the viewer is actually
    listening instead of racing it.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time

logger = logging.getLogger(__name__)

_HEADER = struct.Struct("<I")
MAX_PATH_BYTES = 4096


class LilithClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8888, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.conn: socket.socket | None = None
        self._lock = threading.Lock()

    # -- connection -------------------------------------------------------

    def connect(self) -> bool:
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        self._close_locked()
        try:
            self.conn = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
            self.conn.settimeout(self.timeout)
            # Portrait updates are tiny and latency-sensitive.
            self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return True
        except OSError as exc:
            logger.debug("Viewer connect failed: %s", exc)
            self.conn = None
            return False

    def wait_for_server(self, timeout: float = 10.0, interval: float = 0.15) -> bool:
        """Poll until the viewer accepts a connection, or give up."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.connect():
                return True
            time.sleep(interval)
        logger.warning("Viewer did not start listening on %s:%s", self.host, self.port)
        return False

    def disconnect(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except OSError:
                pass
            self.conn = None

    # -- sending ----------------------------------------------------------

    def set_image_path(self, image_path: str) -> bool:
        payload = str(image_path).encode("utf-8")
        if len(payload) > MAX_PATH_BYTES:
            logger.error("Image path too long to send")
            return False

        with self._lock:
            for attempt in (1, 2):  # one transparent retry after a reconnect
                if self.conn is None and not self._connect_locked():
                    return False
                try:
                    self.conn.sendall(_HEADER.pack(len(payload)) + payload)
                    ack = self.conn.recv(1)
                    if ack == b"\x01":
                        return True
                    if ack == b"\x00":
                        logger.warning("Viewer could not load %s", image_path)
                        return False
                    self._close_locked()  # empty read: viewer went away
                except OSError as exc:
                    logger.debug("Viewer send failed (attempt %s): %s", attempt, exc)
                    self._close_locked()
            return False
