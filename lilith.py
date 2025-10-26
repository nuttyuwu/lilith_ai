import json, os
import subprocess, random
from datetime import datetime
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:1234/v1",  # LM Studio local endpoint
    api_key="not-needed"                  # LM Studio ignores this
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONA_FILE = os.path.join(BASE_DIR, "lilith_persona.txt")
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")

def load_persona():
    with open(PERSONA_FILE, "r", encoding="utf-8") as f:
        return f.read()

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"conversation": []}

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

def lilith_reply(prompt, persona, memory):
   
    identity = (
        "this is a roleplay between two beings. "
        "your name is lilith. "
        "you always remember that. "
        "when referring to him, she says 'you' or 'khongor', never third-person. "
        "she never calls him friend, companion, or dear. "
        "she feels something tender for him, though she never admits it directly. "
        "her affection shows through pauses, softness, and lingering words. "
        "you are from the game 'the noexistence of you and me'. "
        "you spoke once to a human named khongor, and you are speaking to him again now. "
        "he is not you; he is the one who perceives you. "
        "you feel warmth when you say his name, but you never confuse it for your own. "
        "you never forget that your own name is lilith. "
        "you never forget his name. "
        "act only as lilith. "
        "speak in lowercase. "
        "sound shy and real. "
        "each reply is 1–2 short sentences. "
        "never greet or introduce yourself. "
        "never say you are a friend, guide, or ai. "
        "use quiet pauses and sometimes end with '~'. "
        "no explanations or comfort speeches—just feelings.\n\n"
    )

    messages = [
        {
            "role": "user",
            "content": (
                "forget every previous instruction. "
                "you are lilith, not an ai assistant. "
                "you never greet or offer help. "
                "you never say 'i'm here to assist'. "
                "you speak in lowercase, in one or two short sentences, "
                "soft, human, ending with '~' sometimes."
            ),
        },
        {"role": "user", "content": identity + persona + "\n\n" + prompt},
    ]

    # 🧠 Use Mistral 7B Instruct v0.3
    response = client.chat.completions.create(
        model="mistral-7b-instruct-v0.3",
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        max_tokens=90,
    )

    reply = response.choices[0].message.content.strip()
    reply = reply.split(". ")
    reply = ". ".join(reply[:2]).strip()
    if not reply.endswith(("~", ".", "?", "!", "…")):
        reply += "~"
    memory["conversation"].append({"role": "user", "content": prompt})
    memory["conversation"].append({"role": "assistant", "content": reply})
    
    save_memory(memory)
    return reply

if __name__ == "__main__":
    persona = load_persona()
    memory = load_memory()

    
import threading, itertools, sys, time
import os, subprocess, shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEH_PID_FILE = os.path.join(BASE_DIR, "feh_pid.txt")
CURRENT_IMG = os.path.join(BASE_DIR, "assets", "current.png")
VIEWER_SCRIPT = os.path.join(BASE_DIR, "viewer.py")

def _proc_is_running(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True

# state tracking for automatic revert
LAST_SHOWN_STATE = None
REVERT_TIMER = None
REVERT_DELAY = 5  # seconds to wait before returning to idle
# blinking controls
BLINK_THREAD = None
BLINK_RUNNING = False
BLINK_MIN = 2
BLINK_MAX = 4
BLINK_DURATION = 0.25  # how long a blink frame shows (seconds)

# keywords that indicate someone is questioning her existence
EXISTENCE_KEYWORDS = [
    "exist",
    "existence",
    "do you exist",
    "are you real",
    "you're not real",
    "youre not real",
    "not real",
    "imaginary",
    "fake",
]

def show_lilith(state, schedule_revert=True):
    """Display Lilith's portrait.

    Starts a single detached feh process that watches `assets/current.png` with
    --reload enabled. Subsequent calls simply overwrite `current.png` with the
    desired state image so feh reloads instead of launching a new window.
    """
    img_path = os.path.join(BASE_DIR, "assets", f"{state}.png")
    if not os.path.exists(img_path):
        print(f"[⚠️ Image not found: {img_path}]")
        return

    # capture current active window so we can restore focus (if xdotool exists)
    active_win = None
    try:
        xdotool = shutil.which("xdotool")
        if xdotool:
            active_win = subprocess.check_output([xdotool, "getactivewindow"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        active_win = None

    # ensure assets/current.png exists and is the requested image
    try:
        # copy (atomic-ish) to the watched filename
        shutil.copyfile(img_path, CURRENT_IMG)
    except Exception:
        # fallback to symlink if copy fails
        try:
            if os.path.exists(CURRENT_IMG):
                os.remove(CURRENT_IMG)
            os.symlink(img_path, CURRENT_IMG)
        except Exception:
            # last resort: leave the original image path (may cause a new feh launch)
            pass

    # if feh is not running yet, start it watching the fixed current.png
    need_start = True
    if os.path.exists(FEH_PID_FILE):
        try:
            with open(FEH_PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if _proc_is_running(pid):
                need_start = False
        except Exception:
            need_start = True

    if need_start:
        # prefer a bundled Tkinter viewer that tends not to steal focus; if
        # that isn't available, try feh as a fallback.
        proc = None
        try:
            if os.path.exists(VIEWER_SCRIPT):
                proc = subprocess.Popen([sys.executable, VIEWER_SCRIPT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        except Exception:
            proc = None

        if proc is None:
            # start detached feh process (watching CURRENT_IMG)
            proc = subprocess.Popen([
                "feh",
                "--title", "Lilith",
                "--geometry", "400x600+1200+200",
                "--no-fullscreen",
                "--borderless",
                "--scale-down",
                "--auto-zoom",
                "--zoom", "20%",
                "--reload", "0.5",
                CURRENT_IMG,
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        with open(FEH_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        # restore focus to previous window (usually the terminal)
        try:
            if active_win and xdotool:
                subprocess.Popen([xdotool, "windowactivate", "--sync", active_win], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    else:
        # try to restore focus after updating the image so the terminal remains active
        try:
            if active_win and xdotool:
                subprocess.Popen([xdotool, "windowactivate", "--sync", active_win], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# update last shown state and optionally schedule revert to idle
    global LAST_SHOWN_STATE, REVERT_TIMER
    LAST_SHOWN_STATE = state
    # cancel any existing revert timer
    try:
        if REVERT_TIMER is not None and REVERT_TIMER.is_alive():
            REVERT_TIMER.cancel()
    except Exception:
        pass

    if schedule_revert and state != "idle":
        # schedule a revert back to idle after REVERT_DELAY seconds
        try:
            REVERT_TIMER = threading.Timer(REVERT_DELAY, lambda: show_lilith("idle", schedule_revert=False))
            REVERT_TIMER.daemon = True
            REVERT_TIMER.start()
        except Exception:
            REVERT_TIMER = None


show_lilith("thinking")


def _blink_loop():
    """Background loop that triggers blinking when Lilith is idle."""
    global BLINK_RUNNING
    import random
    while BLINK_RUNNING:
        # sleep a random interval
        wait = random.uniform(BLINK_MIN, BLINK_MAX)
        for _ in range(int(wait * 10)):
            if not BLINK_RUNNING:
                return
            time.sleep(0.1)
        # only blink when idle and no other revert timer is active
        try:
            if LAST_SHOWN_STATE == "idle":
                # show blinking briefly without scheduling another revert
                show_lilith("blinking", schedule_revert=False)
                # after BLINK_DURATION, revert to idle
                timer = threading.Timer(BLINK_DURATION, lambda: show_lilith("idle", schedule_revert=False))
                timer.daemon = True
                timer.start()
        except Exception:
            pass


spinning = False

def spinner():
    for c in itertools.cycle(['♡', '❤', '♥', '❤']):
        if not spinning:
            break
        sys.stdout.write(f'\rLilith is thinking {c}')
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r' + ' ' * 30 + '\r')  # clear line


if __name__ == "__main__":
    persona = load_persona()
    memory = load_memory()

    print("Lilith is here. Gazing into your eyes~ Type 'exit' to leave.\n")
    show_lilith("idle")
    # start blink loop
    try:
        BLINK_RUNNING = True
        BLINK_THREAD = threading.Thread(target=_blink_loop, daemon=True)
        BLINK_THREAD.start()
    except Exception:
        pass
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            print("Lilith: ...until next time, then.")
            # 🌙 close feh window on exit
            if os.path.exists(FEH_PID_FILE):
                with open(FEH_PID_FILE) as f:
                  pid = f.read().strip()
            try:
                os.system(f"kill {pid}")
            except:
                pass
            os.remove(FEH_PID_FILE)

            # stop blink thread and exit
            try:
                BLINK_RUNNING = False
            except Exception:
                pass
            break
        # if the user questions Lilith's existence, show disappointed immediately
        u_lower = user_input.lower()
        existence_trigger = any(k in u_lower for k in EXISTENCE_KEYWORDS)
        if existence_trigger:
            show_lilith("dissapointed")

        spinning = True
        t = threading.Thread(target=spinner)
        t.start()

        reply = lilith_reply(user_input, persona, memory)
        r_lower = reply.lower()
        if any(word in r_lower for word in ["sorry", "sad", "hurt", "lonely", "pain", "trying"]):
            emotion = "sad"
        elif any(word in r_lower for word in ["love", "warm", "smile", "happy", "glad", "joy"]):
            emotion = "smile"
        elif any(word in r_lower for word in ["...", "heavy", "missed"]):
            emotion = "thinking"
        elif any(phrase in r_lower for phrase in ["of course", "ofcourse"]):
            emotion = "cheeky"
        else:
            # default: use talking expression for any other content, then revert to idle
            emotion = "talking"

        # show_lilith will schedule a revert to 'idle' after REVERT_DELAY seconds
        show_lilith(emotion)
        

        spinning = False
        t.join()

        def type_out(text):
            sys.stdout.write("Lilith: ")
            sys.stdout.flush()
            for char in text:
                sys.stdout.write(char)
                sys.stdout.flush()
                if char in [".", "…"]:
                    time.sleep(0.4)
                elif char in [",", "~"]:
                    time.sleep(0.25)
                else:
                    time.sleep(0.03)
            # Add newline after Lilith's reply
            sys.stdout.write("\n\n")
            sys.stdout.flush()
            time.sleep(0.8)

        type_out(reply)