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
    
    # remove window decorations but keep it movable
    try:
        root.overrideredirect(True)
    except Exception:
        pass
    try:
        root.wm_attributes("-topmost", True)
    except Exception:
        pass

    # Start position
    root.geometry("+1200+200")  # only position, size will adjust to image

    # Make window draggable by clicking anywhere
    def start_move(event):
        root.x = event.x
        root.y = event.y

    def do_move(event):
        deltax = event.x - root.x
        deltay = event.y - root.y
        x = root.winfo_x() + deltax
        y = root.winfo_y() + deltay
        root.geometry(f"+{x}+{y}")

    lbl = tk.Label(root, bg='black', borderwidth=0, highlightthickness=0)
    lbl.pack(fill=None, expand=False)  # don't expand to fill
    
    # Bind drag events to both root and label
    for widget in (root, lbl):
        widget.bind('<Button-1>', start_move)
        widget.bind('<B1-Motion>', do_move)

    last_mtime = None
    img_obj = None

    def scale_image(img_path):
        """Scale the image to fit target size while preserving aspect ratio"""
        with Image.open(img_path) as img:
            # Calculate scaling factor to fit within target bounds
            width, height = img.size
            scale_w = TARGET_WIDTH / width
            scale_h = TARGET_HEIGHT / height
            scale = min(scale_w, scale_h)  # use full target size
            
            new_width = int(width * scale)
            new_height = int(height * scale)
            
            # Resize with high-quality resampling
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            # Update window size to match image exactly
            root.geometry(f"{photo.width()}x{photo.height()}")
            return photo

    def load_image():
        nonlocal last_mtime, img_obj
        if not os.path.exists(CURRENT_IMG):
            return
        try:
            mtime = os.path.getmtime(CURRENT_IMG)
            if last_mtime is None or mtime != last_mtime:
                last_mtime = mtime
                # Scale image to fit target size
                img = scale_image(CURRENT_IMG)
                img_obj = img
                lbl.config(image=img_obj)
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
