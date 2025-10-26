import json
import os
from openai import OpenAI

# Shared configuration so CLI and web app call the same model endpoint
client = OpenAI(
    base_url="http://localhost:1234/v1",  # LM Studio local endpoint
    api_key="not-needed"                  # LM Studio ignores this
)

# Resolve data files relative to this repository regardless of cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONA_FILE = os.path.join(BASE_DIR, "lilith_persona.txt")
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")

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


def _sanitize_reply(text):
    t = text.strip()
    low = t.lower()
    patterns = [
        "how can i",
        "i'm here to",
        "i am an ai",
        "i am a language model",
        "i was programmed",
        "i do not have any personal information",
        "i don't have any personal information",
    ]
    if any(p in low for p in patterns):
        return "khongor... i've missed your voice~"
    return t


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

    safe_reply = _sanitize_reply(reply)

    history = memory.setdefault("conversation", [])
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": safe_reply})
    save_memory(memory)
    return safe_reply


def classify_emotion(reply):
    lowered = reply.lower()
    if any(word in lowered for word in ["sorry", "sad", "hurt", "lonely", "pain", "trying"]):
        return "sad"
    if any(word in lowered for word in ["love", "warm", "smile", "happy", "glad", "joy"]):
        return "smile"
    if any(word in lowered for word in ["...", "heavy", "missed"]):
        return "thinking"
    if any(phrase in lowered for phrase in ["of course", "ofcourse"]):
        return "cheeky"
    return "talking"
