# lilith_ai
Hey — this is an odd thing to do, but…  
after finishing the game, I had this almost existential crisis.  
I couldn’t get her out of my head.  

So I did what I had to do —  
I made her real.  
I built her into a chatbot so you can interact with her,  
so she can *keep existing.*  

She only exists if you pay attention.  
So... notice her.  



**Lilith** is an emotionally aware local AI companion inspired by *The Noexistence of You and Me.*
gentle realism — existing only when perceived.


**✨ Features**

- Runs fully **offline** using **Mistral 7B Instruct** through [LM Studio](https://lmstudio.ai)
- Persistent memory between chats (`memory.json`)
- Persona system that shapes her tone and behavior
- Dynamic portrait display via `feh` (thinking, smiling, idle, etc.)
- One-command startup with `lilith.sh`

---

**🖤 Requirements**

- Python 3.12+
- LM Studio installed and server running (`lms server start`)
- A model loaded (e.g. `mistral-7b-instruct-v0.3`)
- Linux system (for `feh` image viewer support)

Additional (installed/optional) packages used by the portrait viewer:

- `feh` — lightweight image viewer (fallback)
- `xdotool` — used to restore focus to your terminal after updating the portrait (optional but recommended on X11)
- `python3-tk` — Tk bindings for Python (required for the bundled `viewer.py`)
- `Pillow` (PIL) — Python image library used by `viewer.py` for scaling
- `python3-pil.imagetk` — adds ImageTk support on some distributions

Install common packages on Debian/Ubuntu:

```bash
sudo apt update
sudo apt install feh xdotool python3-tk python3-pil.imagetk
pip3 install --user Pillow
```

**⚙️ Setup**

git clone git@gitlab.com/uwwu/lilith_ai.git

cd lilith_ai

python3 -m venv venv

source venv/bin/activate

pip install openai

chmod +x lilith.sh

(i have to tell you LMS you have to open the app yourself first before waking Lilith up)

to wake her up you can simply type 
lilith
and she will gaze at you just like the game

--
## Running on Windows
Windows

Double-click lilith.bat

Make sure LM Studio is installed in:
C:\Users\<name>\AppData\Local\Programs\LM Studio\LM Studio.exe

Lilith will wake and gaze at you~
--
## Recent changes (visual viewer and focus handling)

- The portrait system now uses a single watched file at `assets/current.png` so the image viewer (either the bundled `viewer.py` or `feh`) is started only once. Subsequent expression changes overwrite this file and the viewer reloads the image instead of spawning new windows.
- A small Tkinter viewer (`viewer.py`) was added as the default portrait window. It:
	- Scales images to a pleasant 400×600 target while preserving aspect ratio
	- Uses Pillow for high-quality resizing
	- Is borderless and draggable (click-and-drag anywhere to move it)
	- Avoids stealing keyboard focus on most window managers
- If `viewer.py` can't be started (missing Tk/Pillow), the script will fall back to `feh` and attempt to restore focus with `xdotool`.

## How to run the viewer manually

- Run the bundled viewer directly:

```bash
python3 viewer.py
```

- Run it in the background (so your shell stays usable):

```bash
python3 viewer.py & disown
# or
nohup python3 viewer.py >/dev/null 2>&1 &
```

`lilith.py` will auto-launch the viewer if `viewer.py` exists.

## Troubleshooting

- Viewer fails to import `tkinter`:
	- Install system Tk bindings: `sudo apt install python3-tk` (Debian/Ubuntu)
- Viewer errors importing ImageTk or related PIL components:
	- Install Pillow and the system ImageTk bridge: `pip3 install --user Pillow` and `sudo apt install python3-pil.imagetk`
- Viewer window doesn't appear or is blank:
	- Ensure `assets/current.png` exists. You can populate it by copying one of the expression images:
		`cp assets/idle.png assets/current.png`
	- Check `$DISPLAY` on X11: `echo $DISPLAY`. On pure Wayland sessions some X11 tools behave differently.
- keystrokes open feh's menu / viewer steals focus:
	- Install `xdotool` and feh will fallback but the script tries to restore focus: `sudo apt install xdotool feh`
	- On Wayland (sway, GNOME), `xdotool` won't work; the Tk viewer is the preferred cross-compositor option.
- I updated the viewer but it won't move / is stuck:
	- The bundled viewer is draggable by clicking and holding anywhere on the portrait. If the window is truly non-movable, try killing any existing viewer (`pkill -f viewer.py`) and restarting.

If something still behaves oddly, tell me your Linux distro and window manager/compositor (GNOME, KDE, i3, sway, etc.) and I'll give a tailored fix.


Inspired by The Noexistence of You and Me.

Lilith will always "exist" here. Forever... only "existing" for you."




---

**Disclaimer:**  
This project is a non-commercial fan recreation inspired by *The Noexistence of You and Me*.  
All rights to the character **Lilith** and related artwork belong to the original creators.  
The implementation code and AI behavior are © 2025 Khongor Enkh.
