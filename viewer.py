#!/usr/bin/env python3
"""
Lightweight Tkinter image viewer that watches `assets/current.png` and reloads
when it changes. Designed to avoid stealing keyboard focus from the terminal.

Run alongside `lilith.py`. Uses PIL/Pillow for proper image scaling.
"""
import os
import sys
import time
import tkinter as tk
from PIL import Image, ImageTk  # for better image handling

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CURRENT_IMG = os.path.join(BASE_DIR, "assets", "current.png")
TARGET_WIDTH = 400   # desired window width
TARGET_HEIGHT = 600  # desired window height

def main():
    root = tk.Tk()
    root.title("Lilith")
    root.configure(bg='black')
    
    # allow the window to be resizable and use native decorations so users can
    # resize it with the window manager. Keep always-on-top behavior.
    try:
        root.overrideredirect(False)
    except Exception:
        pass
    try:
        root.wm_attributes("-topmost", True)
    except Exception:
        pass

    # Start position and allow resizing
    root.geometry("400x600+1200+200")
    root.resizable(True, True)

    lbl = tk.Label(root, bg='black', borderwidth=0, highlightthickness=0)
    lbl.pack(fill=tk.BOTH, expand=True)

    # Track resize events and rescale the current image to fit the window
    resize_job = None
    def on_resize(event):
        nonlocal resize_job
        # debounce rapid resize events
        if resize_job:
            root.after_cancel(resize_job)
        resize_job = root.after(100, lambda: rescale_to_window())

    def rescale_to_window():
        nonlocal img_obj, orig_img
        try:
            w = lbl.winfo_width()
            h = lbl.winfo_height()
            if w <= 1 or h <= 1:
                return
            if orig_img is None:
                return
            # scale orig_img to fit within w,h
            iw, ih = orig_img.size
            scale = min(w/iw, h/ih)
            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))
            img = orig_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            img_obj = ImageTk.PhotoImage(img)
            lbl.config(image=img_obj)
        except Exception:
            pass

    root.bind('<Configure>', on_resize)

    last_mtime = None
    img_obj = None
    orig_img = None

    def scale_image(img_path, target_w=TARGET_WIDTH, target_h=TARGET_HEIGHT):
        """Return a PhotoImage scaled to target_w x target_h preserving aspect."""
        with Image.open(img_path) as img:
            width, height = img.size
            scale_w = target_w / width
            scale_h = target_h / height
            scale = min(scale_w, scale_h)
            new_width = max(1, int(width * scale))
            new_height = max(1, int(height * scale))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)

    def load_image():
        nonlocal last_mtime, img_obj, orig_img
        if not os.path.exists(CURRENT_IMG):
            return
        try:
            mtime = os.path.getmtime(CURRENT_IMG)
            if last_mtime is None or mtime != last_mtime:
                last_mtime = mtime
                # load original PIL image into memory
                try:
                    pil_img = Image.open(CURRENT_IMG).convert('RGBA')
                except Exception:
                    pil_img = Image.open(CURRENT_IMG)
                orig_img = pil_img.copy()
                pil_img.close()
                # if the window is still default size, create a nicely scaled photo
                w = lbl.winfo_width()
                h = lbl.winfo_height()
                if w <= 1 or h <= 1:
                    # use target-based scale for initial sizing
                    photo = scale_image(CURRENT_IMG)
                    img_obj = photo
                    lbl.config(image=img_obj)
                    # set window size to image size
                    try:
                        root.geometry(f"{photo.width()}x{photo.height()}")
                    except Exception:
                        pass
                else:
                    # rescale to current window
                    rescale_to_window()
        except Exception:
            # if image loading fails, keep current image
            print("Failed to load image:", sys.exc_info()[1])

    def poll():
        load_image()
        # schedule next check
        root.after(200, poll)

    # Initial load + start polling
    load_image()
    root.after(200, poll)

    # Start the Tk mainloop. Do not force focus; keep terminal usable.
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
