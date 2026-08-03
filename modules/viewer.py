"""
Lilith's portrait window.

A small excuse from the original author, preserved because it is still true:
there is no clean way to push images into a running Tk mainloop from another
process, so the viewer runs a tiny socket server and the main process sends it
file paths.

Cross-platform work done here:
  * DPI awareness is enabled *before* Tk starts. Windows 11 scales displays at
    125-150% by default, which otherwise makes the window blurry and the wrong
    physical size.
  * The window position is clamped to the real desktop. The old hardcoded
    ``+1200+200`` put Lilith completely off-screen on a 1366x768 laptop.
  * The viewer exits when its parent exits. On Windows a child process is not
    reaped with its parent, so closing Lilith used to leave an orphan portrait
    window (holding port 8888) behind forever.
  * The port is checked before binding. SO_REUSEADDR means the *opposite*
    thing on Windows -- two processes can bind one port -- so relying on
    bind() to fail let two viewers silently fight over it.
  * Images are applied on the Tk thread. Tk is not thread-safe, and the old
    code called into widgets straight from the socket thread.
  * Works when launched as ``python modules/viewer.py`` from any directory.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import struct
import sys
import threading
import time
from pathlib import Path

# Launched as a script from modules/, so the project root is not importable yet.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import compat  # noqa: E402

_HEADER = struct.Struct("<I")
MAX_PATH_BYTES = 4096
_OFFSET_RE = re.compile(r"^([+-]\d+)([+-]\d+)$")


def recv_exact(conn: socket.socket, size: int) -> bytes | None:
    """Read exactly *size* bytes, or ``None`` if the peer closes early."""
    buffer = bytearray()
    while len(buffer) < size:
        chunk = conn.recv(size - len(buffer))
        if not chunk:
            return None
        buffer.extend(chunk)
    return bytes(buffer)


def _missing_gui_dependency(exc: Exception) -> None:
    """Explain how to get Tk working, per platform, then exit."""
    print(f"Lilith's viewer cannot start: {exc}\n", file=sys.stderr)
    if compat.IS_WINDOWS:
        print(
            "On Windows, tkinter ships with the python.org installer.\n"
            "If it is missing, re-run the installer and enable 'tcl/tk and IDLE'.\n"
            "Pillow is also required:  python -m pip install pillow",
            file=sys.stderr,
        )
    else:
        print(
            "Debian/Ubuntu:  sudo apt install python3-tk python3-pil.imagetk\n"
            "Fedora:         sudo dnf install python3-tkinter python3-pillow-tk\n"
            "Arch:           sudo pacman -S tk python-pillow",
            file=sys.stderr,
        )
    sys.exit(1)


def parent_alive(pid: int) -> bool:
    """Is the process that spawned us still running?

    Deliberately avoids ``os.kill(pid, 0)`` on Windows, where os.kill is
    implemented with TerminateProcess and would kill the parent rather than
    probe it.
    """
    if pid <= 0:
        return True

    if compat.IS_WINDOWS:
        import ctypes

        SYNCHRONIZE = 0x00100000
        WAIT_OBJECT_0 = 0x0
        ERROR_INVALID_PARAMETER = 87  # no such pid -- the parent really is gone

        # use_last_error=True is what makes ctypes.get_last_error() below
        # return this call's real GetLastError instead of a stale zero.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Default restype is c_int, which sign-extends a handle with the high
        # bit set into a bogus value on 64-bit. Declare the real types.
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            # A failure to OPEN the process is not proof it exited. If the
            # parent runs elevated or as another user we get ACCESS_DENIED for
            # a perfectly alive process -- and reporting "dead" here made the
            # portrait destroy itself about a second after startup. Only an
            # invalid pid means genuinely gone; fail safe otherwise, matching
            # the POSIX branch's PermissionError handling below.
            return ctypes.get_last_error() != ERROR_INVALID_PARAMETER
        try:
            # A process handle becomes signalled once the process exits.
            return kernel32.WaitForSingleObject(handle, 0) != WAIT_OBJECT_0
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def virtual_screen() -> tuple[int, int, int, int] | None:
    """(left, top, width, height) of the whole virtual desktop, Windows only.

    winfo_screenwidth() reports the PRIMARY monitor, so clamping to it drags
    the window off any secondary display -- a monitor to the left has negative
    X, and one to the right starts beyond the primary width.
    """
    if not compat.IS_WINDOWS:
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
        top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
        width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
        height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
        if width <= 0 or height <= 0:
            return None
        return (left, top, width, height)
    except Exception:
        return None


def clamp_geometry(screen_w: int, screen_h: int, width: int, height: int,
                   offset: str = "", origin_x: int = 0, origin_y: int = 0) -> str:
    """Build a Tk geometry string guaranteed to land on the visible desktop.

    origin_x/origin_y default to 0 (single-monitor behaviour) but accept the
    virtual desktop's top-left, which is negative when a second monitor sits
    above or to the left of the primary one.
    """
    width = max(160, min(width, screen_w))
    height = max(160, min(height, screen_h))

    x = y = None
    match = _OFFSET_RE.match((offset or "").strip())
    if match:
        x, y = int(match.group(1)), int(match.group(2))

    if x is None or y is None:
        # Default: right-hand side, vertically centred, small margin.
        x = origin_x + screen_w - width - 40
        y = origin_y + (screen_h - height) // 2

    x = max(origin_x, min(x, origin_x + max(0, screen_w - width)))
    y = max(origin_y, min(y, origin_y + max(0, screen_h - height)))
    return f"{width}x{height}+{x}+{y}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lilith portrait viewer")
    parser.add_argument("--parent-pid", type=int, default=0,
                        help="exit automatically when this process exits")
    args = parser.parse_args()

    # Must happen before Tk initialises, or the wrong scaling is baked in.
    scale = compat.enable_dpi_awareness()

    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except Exception as exc:  # ImportError, or Tk built without display support
        _missing_gui_dependency(exc)
        return

    config = compat.load_config()
    display = config["lilith_display"]
    sock_cfg = config["viewer_socket"]

    host = sock_cfg.get("host", "127.0.0.1")
    port = sock_cfg.getint("port", fallback=8888)

    if compat.port_in_use(host, port):
        print(f"A Lilith viewer already listens on {host}:{port}; exiting.")
        return

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Cannot open a window: {exc}", file=sys.stderr)
        if not compat.IS_WINDOWS:
            print("Set [lilith_display] enable = false to run headless.",
                  file=sys.stderr)
        sys.exit(1)

    root.title("Lilith")
    root.configure(bg="black")

    try:
        base_w, base_h = (int(v) for v in
                          display.get("window_geometry", "400x600").lower().split("x")[:2])
    except ValueError:
        base_w, base_h = 400, 600

    # Scale with the display so Lilith is the same physical size at 100% and 150%.
    bounds = virtual_screen()
    if bounds is None:
        origin_x, origin_y = 0, 0
        avail_w, avail_h = root.winfo_screenwidth(), root.winfo_screenheight()
    else:
        origin_x, origin_y, avail_w, avail_h = bounds
    root.geometry(clamp_geometry(
        avail_w, avail_h,
        int(base_w * scale), int(base_h * scale),
        display.get("window_offset", ""),
        origin_x, origin_y,
    ))
    root.minsize(160, 160)
    root.resizable(True, True)

    if display.getboolean("always_on_top", fallback=True):
        root.wm_attributes("-topmost", True)

    if display.getboolean("transparent", fallback=False) and compat.IS_WINDOWS:
        # Tk has no per-pixel alpha; colour-keying is the Windows-only stand-in.
        try:
            root.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass

    label = tk.Label(root, bg="black", borderwidth=0, highlightthickness=0)
    label.pack(fill=tk.BOTH, expand=True)

    state: dict = {"photo": None, "original": None, "path": None, "timer": None}

    def render() -> None:
        original = state["original"]
        if original is None:
            return
        w, h = label.winfo_width(), label.winfo_height()
        if w <= 1 or h <= 1:
            return
        iw, ih = original.size
        ratio = min(w / iw, h / ih)
        size = (max(1, int(iw * ratio)), max(1, int(ih * ratio)))
        state["photo"] = ImageTk.PhotoImage(original.resize(size, Image.Resampling.LANCZOS))
        label.config(image=state["photo"])

    def on_resize(event) -> None:
        if event.widget is not root:
            return
        if state["timer"]:
            root.after_cancel(state["timer"])
        state["timer"] = root.after(100, render)

    def apply_image(path: str) -> bool:
        """Tk-thread only."""
        try:
            image = Image.open(path)
            image.load()
            state["original"] = image.convert("RGBA")
            state["path"] = path
            render()
            return True
        except Exception:
            return False

    def load_image(path: str) -> bool:
        """Socket-thread entry point; marshals the work onto the Tk thread."""
        if not os.path.exists(path):
            return False

        result: list[bool] = []
        done = threading.Event()

        def task() -> None:
            try:
                result.append(apply_image(path))
            finally:
                done.set()

        try:
            root.after(0, task)
        except (RuntimeError, tk.TclError):
            # RuntimeError: no mainloop. TclError: root already destroyed --
            # which the old code did not catch, so it escaped into
            # handle_client (guarded only for OSError) and killed the thread.
            return False
        if not done.wait(timeout=5.0):
            return False
        return bool(result and result[0])

    def handle_client(conn: socket.socket) -> None:
        conn.settimeout(60.0)
        try:
            while True:
                header = recv_exact(conn, _HEADER.size)
                if header is None:
                    break
                (size,) = _HEADER.unpack(header)
                if size == 0 or size > MAX_PATH_BYTES:
                    break

                payload = recv_exact(conn, size)
                if payload is None:
                    return

                path = payload.decode("utf-8", errors="replace")
                conn.sendall(b"\x01" if load_image(path) else b"\x00")
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            if compat.IS_WINDOWS:
                try:
                    server.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                except (AttributeError, OSError):
                    pass
            else:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                server.bind((host, port))
            except OSError as exc:
                print(f"Viewer could not bind {host}:{port}: {exc}", file=sys.stderr)
                try:
                    root.after(0, root.destroy)
                except (RuntimeError, tk.TclError):
                    pass
                return

            server.listen(4)
            server.settimeout(0.5)
            while True:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

    def watch_parent() -> None:
        """Close the window once Lilith herself is gone."""
        while True:
            time.sleep(1.0)
            if not parent_alive(args.parent_pid):
                try:
                    root.after(0, root.destroy)
                except (RuntimeError, tk.TclError):
                    pass
                return

    def start_background() -> None:
        """Begin listening only once the mainloop is actually running.

        Starting the socket thread before mainloop() meant the port began
        accepting during the window between listen() and mainloop() -- and
        the client's wait_for_server() returns the instant listen() accepts,
        so the very first frame could arrive while load_image's root.after()
        had no loop to schedule onto. It raised, was swallowed, and the
        opening frame silently never appeared.
        """
        threading.Thread(target=serve, daemon=True).start()
        if args.parent_pid:
            threading.Thread(target=watch_parent, daemon=True).start()

    root.after(0, start_background)
    root.bind("<Configure>", on_resize)

    # Show something immediately rather than an empty black box.
    first = compat.project_path(
        display.get("assets_path", "assets"),
        display.get("place", "room"),
        f"{display.get('default_state', 'idle')}.png",
    )
    if first.exists():
        apply_image(str(first))

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
