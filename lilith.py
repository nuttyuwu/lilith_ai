import os
from datetime import datetime
from openai import OpenAI
import configparser
import lilith_display
import lilith_ai

config = configparser.ConfigParser()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
config.read(CONFIG_PATH)
DEFAULT_USER_NAME = ""

Lilith_display = lilith_display.LilithDisplay(BASE_DIR, config)
Lilith_AI = lilith_ai.LilithAI(Lilith_display, config, BASE_DIR, DEFAULT_USER_NAME)

    
import threading, itertools, sys, time
import os, subprocess, shutil

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

Lilith_display.show_lilith("thinking")


spinning = False

def spinner():
    for c in itertools.cycle(['♡', '❤', '♥', '❤']):
        if not spinning:
            break
        sys.stdout.write(f'\rLilith is thinking {c}')
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r' + ' ' * 30 + '\r')  # clear line

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


if __name__ == "__main__":
    if not Lilith_AI.has_user_name():
        while True:
            entered = input("Lilith tilts her head. \"what should i call you?\" ").strip()
            if entered:
                Lilith_AI.set_user_name(entered)
                break
            print("...she waits. give her a name to hold onto.")
    current_name = Lilith_AI.get_user_name()

    print("Lilith is here. she gazes softly at you~ Type 'exit' to leave.\n")
    Lilith_display.show_lilith("idle")
    Lilith_display.set_blinking(True) # enable blinking
    
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            print("Lilith: ...until next time, then.")
            break
        
        # if the user questions Lilith's existence, show disappointed immediately
        u_lower = user_input.lower()
        existence_trigger = any(k in u_lower for k in EXISTENCE_KEYWORDS) # Lol its so bad
        if existence_trigger:
            Lilith_display.show_lilith("dissapointed")

        spinning = True
        t = threading.Thread(target=spinner)
        t.start()
        Lilith_display.show_lilith("thinking", schedule_revert=False)

        reply = Lilith_AI.lilith_reply(user_input) # Get Lilith's reply

        # show emotion based on last reply
        emotion = Lilith_AI.get_current_emotion()

        # show_lilith will schedule a revert to 'idle' after REVERT_DELAY seconds
        Lilith_display.show_lilith(emotion)

        spinning = False
        t.join()

        type_out(reply)
