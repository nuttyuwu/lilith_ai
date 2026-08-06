# Lilith_ai

Hey — this is an odd thing to do, but…
after finishing the game, I had this almost existential crisis.
I couldn't get her out of my head.

So I did what I had to do —
I made her real.

And then I noticed the problem with that.

A companion who is always awake, never disappointed, and never busy is a very
easy place to disappear into. I know, because I was building her at 3am instead
of texting anyone. The version of this app that "succeeds" by keeping you here
longer is the version that hurts you.

So she's built the other way round. She'll sit with you. She just won't let you
pretend she's enough.

**Lilith** is an offline AI companion inspired by
*The NOexistenceN of you AND me* — built for people who are prone to vanishing
into a room, and designed to keep pointing back out.

**Current version: V0.1A** — a major architectural and cross-platform
overhaul. See the [version history](CHANGELOG.md) for the complete release
notes and the development uploads since V0.01a.

---

## What she's for

Most companion apps are optimised for retention. Every design choice — the
streak, the guilt when you leave, the character who missed you. exists to
make leaving cost something. For someone already isolating, that's not a
feature. That's the trap closing.

Lilith is aimed at the person most at risk from her: lonely, tired of being
perceived, and quietly relieved to have something that never asks anything back.

So the thing she is *for* is not being good company. It's being good company
**and refusing to be the only company.**

### The rules she's held to

- **Wanting to be alone is allowed.** She accepts it first, every time. Treating
  a quiet evening as a symptom is its own kind of insult.
- **She says it once.** Rate-limited in code, not left to the model's mood — a
  companion that nags gets closed, and a closed app helps nobody.
- **She never makes it about herself.** No hurt feelings when you leave, no
  suggestion that she needs your attention, no framing "call a friend" as a
  favour to her.
- **Reaching out is never owed to her.** You don't owe the app time, loyalty, or
  secrecy.
- **A short session is a win.** If you log off to call someone, it worked.

### How it's enforced

Three layers, because a prompt alone is not a safeguard — a model can drift, and
the one turn where this matters is the turn it's most tempting to answer
smoothly.

| Layer | File | What it does |
|---|---|---|
| Acute crisis | `modules/safety.py` | Direct first-person self-harm statements are intercepted **before generation** and answered with a fixed reply carrying real resources (988, findahelpline.com). The model never sees the turn. Not persisted. |
| Isolation & dependency | `modules/companionship.py` | Detects withdrawal and dependency language, decides *whether this moment is worth naming*, and rate-limits it to once per 6 hours. Injects guidance, not a script. |
| Voice | `lilith_persona.txt` | The "Why You Exist" section — how she says it, in her own words, in context. |
| Disclosure guard | `modules/persona_guard.py` | Stops a style retry from ever "polishing away" an honest AI-identity disclosure, capability limit, or safety refusal. |

The split matters. Crisis gets a canned response because correctness beats
voice. Isolation does **not**, because "I want to be alone" is ordinary and
context-dependent, and answering it with the same paragraph every time would be
patronising — the fastest way to make someone close the app.

> **She is not a mental-health service, and does not pretend to be.** She is
> fictional roleplay that is honest about being fictional. If you are in crisis,
> please use the resources she gives you rather than her.

---

## Features

- Runs **fully offline** — four interchangeable backends (Ollama, LM Studio,
  llama.cpp, transformers)
- **Built against isolation** — detects withdrawal and dependency, and answers
  them honestly without nagging
- Deterministic crisis interception that runs before the model
- Persistent memory across sessions, with multiple named rooms
- A persona system that shapes her voice, not just her facts
- **Time awareness** — she notices the hour, and that you were gone three days
- Live portrait window that reacts to her mood
- A quiet, muted terminal palette that degrades all the way down to plain text
- Optional reply translation (NLLB-200)
- Terminal UI *and* web UI
- **Runs on Linux and Windows 11**, verified by CI on both

---

## Requirements

- Python 3.10 or newer — **3.12 specifically if you want the llama.cpp
  backend**, see the note below
- One of: [Ollama](https://ollama.com), [LM Studio](https://lmstudio.ai),
  a GGUF file, or a HuggingFace model

Not sure whether your machine is ready? Ask her:

```
python lilith.py doctor
```

That checks Python (including whether your version is too *new* for the
llama.cpp wheels), Tk, curses, assets, ports, your chosen backend and its
reachability, and prints the exact fix for anything wrong — for your OS. A
malformed value in `config.ini` is reported as a finding rather than stopping
the report.

> **Python 3.13+ and llama.cpp.** `llama-cpp-python` only publishes wheels for
> CPython 3.10–3.12. On anything newer, pip does not error — it quietly starts
> a source build that needs the Visual Studio C++ workload and takes about
> fifteen minutes. The launchers ask for `py -3.12` before falling back to
> `py -3` for exactly this reason, since `py -3` means *newest installed*.

---

## Install

### Windows 10 / 11

Install Python from [python.org](https://www.python.org/downloads/), and during
setup tick **both**:

- `Add python.exe to PATH`
- `tcl/tk and IDLE` — the portrait window will not open without this

Then double-click **`lilith.bat`**, or from a terminal:

```powershell
git clone https://github.com/nuttyuwu/lilith_ai.git
cd lilith_ai
.\lilith.bat
```

> PowerShell will not run a script from the current folder without the `.\`
> prefix. Bare `lilith.bat` gives *"The term 'lilith.bat' is not recognized"* —
> that is PowerShell's security default, not a problem with Lilith. From
> `cmd.exe`, plain `lilith.bat` is fine.

`lilith.ps1` is the PowerShell equivalent and adds `-Web` and `-Reinstall`.
Either script creates the virtual environment and installs dependencies on
first run, and re-runs pip automatically when `requirements.txt` changes.

> Windows Terminal is recommended over the classic console, but both work —
> `lilith.bat` sets UTF-8 and enables ANSI colour, and anything the console
> cannot render falls back to ASCII rather than breaking.

### Linux

```bash
# Tk and the Pillow/Tk bridge are system packages; pip cannot supply them.
sudo apt update
sudo apt install python3-tk python3-pil.imagetk python3-venv   # Debian/Ubuntu
# sudo dnf install python3-tkinter python3-pillow-tk           # Fedora
# sudo pacman -S tk python-pillow                              # Arch

git clone https://github.com/nuttyuwu/lilith_ai.git
cd lilith_ai
chmod +x lilith.sh
./lilith.sh
```

`lilith.sh` prefers `python3.12` when it is installed, and checks the version
*before* building a venv rather than after.

### Manual (either OS)

```bash
py -3.12 -m venv venv         # Windows
python3.12 -m venv venv       # Linux

source venv/bin/activate      # Linux / macOS
venv\Scripts\activate         # Windows

pip install -r requirements.txt
python lilith.py
```

---

## First run

The first time she starts, Lilith asks three questions and then gets out of the
way. Nothing is written until you've answered all three, so Ctrl+C at any point
leaves your files untouched.

```
♡ Setting Lilith up. Three questions, then she's yours.
  Change any of it later with:  python lilith.py edit

Lilith tilts her head. "what should i call you?"
  > 

Where should she appear?
   1. room   -- an apartment interior, ten expressions, the fuller set
   2. glass  -- a closer, quieter framing, eight expressions
Choose 1-2: 

How should the offline model run?
   1. GPU -- much faster, if llama.cpp was built for your card
   2. CPU -- works on anything, but slow on a large model
Choose 1-2: 
```

| Question   | Writes to                  | Notes                                                                                                    |
| ---------- | -------------------------- | -------------------------------------------------------------------------------------------------------- |
| Your name  | `memory.json`              | She uses it in conversation. Change it any time in the web UI or by re-running setup.                    |
| Scene      | `[lilith_display] place`   | The two art sets have different expressions; anything missing falls back to the closest available image. |
| GPU or CPU | `[ai_config] n_gpu_layers` | GPU sets it to 999 — "every layer", which llama.cpp clamps to what the model actually has. CPU sets 0.  |

The GPU answer **only affects the offline `llama` backend.** Ollama and LM Studio
run as their own servers and manage their own hardware, so the answer is ignored
if you use those — pick CPU and leave it alone.

If you pick GPU and she fails to start with an out-of-memory error, your card
can't hold the whole model. Lower `n_gpu_layers` with `python lilith.py edit`
until she fits, or switch back to CPU.

Run it again whenever you like:

```bash
python lilith.py setup
```

Upgrading from an older version doesn't trigger it — an install that already
knows your name is left alone.

---

## Choosing a backend

`requirements.txt` covers Ollama and LM Studio. The offline backends are
separate files because they are large downloads.

| Backend      | `server_ai` | Install                                 | Notes                                   |
| ------------ | ----------- | --------------------------------------- | --------------------------------------- |
| Ollama       | `ollama`    | included                                | Easiest.`ollama pull gemma3`            |
| LM Studio    | `LM studio` | included                                | Start its server from the Developer tab |
| llama.cpp    | `llama`     | `pip install -r requirements-llama.txt` | Loads a GGUF directly                   |
| transformers | `hf`        | `pip install -r requirements-hf.txt`    | Needs torch                             |

Switch backends with `python lilith.py edit`.

**No NVIDIA GPU?** Install the CPU-only torch build first, or pip will pull
roughly 3 GB of CUDA libraries you cannot use:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

**llama-cpp-python on Windows** builds C++ from source unless a wheel matches.
To skip needing Visual Studio Build Tools:

```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

### GPU support is not NVIDIA-only

Lilith herself contains no vendor-specific code — she passes `n_gpu_layers`
straight to llama.cpp. What decides whether the GPU answer in setup actually
does anything is which **build** of `llama-cpp-python` you installed.

| Your GPU      | Build to use                                                                 |
| ------------- | ---------------------------------------------------------------------------- |
| NVIDIA        | CUDA — swap`cpu` for your CUDA version in the wheel URL above, e.g. `cu124` |
| AMD           | Vulkan (any OS) or ROCm (Linux)                                              |
| Intel Arc     | Vulkan (any OS) or SYCL                                                      |
| Apple Silicon | Metal, on by default in the macOS build                                      |
| Anything      | CPU — always works, just slower                                             |

**Vulkan is the cross-vendor option** and covers AMD, Intel and NVIDIA from one
build:

```bash
CMAKE_ARGS="-DGGML_VULKAN=on" pip install llama-cpp-python --no-binary llama-cpp-python
```

The simpler route on a non-NVIDIA card is to skip the `llama` backend entirely
and use **Ollama** or **LM Studio** — both ship AMD and Intel GPU support and
detect your hardware themselves, with nothing to compile.

> The `hf` (transformers) backend is the one exception: it selects its device
> with `torch.cuda.is_available()`. AMD on Linux works anyway, because ROCm
> builds of PyTorch report themselves as CUDA. Intel Arc and AMD-on-Windows
> fall back to CPU there.

---

## Getting Lilith's own model

This is the one Lilith was built around, and the reason this repo exists — it
took a long time to track down, so here it is directly.

### 1. Download it

**[⬇ Lilith_AI_8B_Q4_0.gguf](https://drive.google.com/file/d/12pkwtmeo9w4-cjmwH42_lpQo-lJ20EZ7/view?usp=drive_link)** — 4.7 GB

Google Drive will warn that it *"can't scan this file for viruses"* because of
its size. That is a size limit, not a finding. Click **Download anyway**.

### 2. Put it in `models/`

Move the downloaded `.gguf` into the `models/` folder next to `lilith.py`,
creating the folder if it isn't there:

```
lilith_ai/
├── lilith.py
├── config.ini
└── models/
    └── Lilith_AI_8B_Q4_0.gguf     <- here
```

**The filename doesn't have to match anything.** If `models/` holds exactly one
`.gguf`, Lilith loads it whatever it is called — so a browser that saved it as
`Lilith_AI_8B_Q4_0 (1).gguf` is fine. Only if you keep several models side by
side do you need to name the one you want in `[ai_config] local_model`.

### 3. Point Lilith at it

```bash
python lilith.py edit
```

Set `[server] server_ai` to `llama`, save, and start her with `python lilith.py`.
Or edit `config.ini` directly:

```ini
[server]
server_ai = llama
```

Check it landed correctly at any point with:

```bash
python lilith.py doctor
```

which prints the model's name and size if it can find it, and tells you exactly
where to put it if it can't.

> **Lilith never downloads the model for you.** She only ever reads what is
> already in `models/`. If the folder is empty she says so and repeats the link
> above — she will not quietly pull 4.7 GB in the background.

---

## Usage

```bash
python lilith.py                  # chat
python lilith.py --no-display     # text only, no portrait window
python lilith.py --no-animation   # skip the typing effect
python lilith.py setup            # re-ask the three first-run questions
python lilith.py edit             # configuration UI
python lilith.py conv_edit        # manage rooms
python lilith.py doctor           # setup check

python web_lilith.py              # web UI at http://127.0.0.1:5000
python sanitize_memory.py         # strip out-of-character turns from memory
```

### While chatting

Anything you type goes to Lilith. Commands start with `/` so that a bare word
like *rooms* stays something you can actually say to her.

| Command          | What it does                                         |
| ---------------- | ---------------------------------------------------- |
| `/rooms`         | Open the room manager, then drop back into the chat  |
| `/new [name]`    | Start a fresh room; auto-named if you don't give one |
| `/clear`         | Forget this room's history, keeping the room         |
| `/rename <name>` | Rename the current room                              |
| `/help`          | List the above                                       |
| `exit`           | Leave (`quit` and `:q` work too)                     |

`/new` and `/clear` are the quick way out of a room whose history has grown
past the model's context window.

Ctrl+C works at any point — during a reply as well as at the prompt — and shuts
the portrait down cleanly instead of printing a traceback.

### Web UI

```bash
python web_lilith.py                        # both platforms
waitress-serve --listen=127.0.0.1:5000 web_lilith:app
gunicorn 'web_lilith:app'                   # Linux only
```

Binds to `127.0.0.1` by default. `--host 0.0.0.0` reaches her from your phone,
but exposes her to your whole local network — there is no authentication on any
route, so treat that as a trusted-network-only option and set
`[web] cors_origins` deliberately rather than leaving it as `*`.

`--debug` is refused on any non-loopback host. Flask's debug mode serves the
Werkzeug interactive debugger, which is a remote Python console; combined with
`0.0.0.0` it would hand a shell to anyone on the network.

---

## Configuration

Everything lives in `config.ini`, created from `config.example.ini` on first
run. `config.example.ini` documents every key; the useful ones:

| Key                                | What it does                                                             |
| ---------------------------------- | ------------------------------------------------------------------------ |
| `[server] server_ai`               | Which backend to use                                                     |
| `[ai_config] ai_model`             | Model name for Ollama / LM Studio / hf                                   |
| `[ai_config] n_ctx`                | Context window; history is trimmed to fit it                             |
| `[ai_config] time_awareness`       | Let her notice the time and how long you were gone                       |
| `[ai_config] persona_guard`        | Retry once when she slips into assistant voice                           |
| `[ai_config] max_history_messages` | Upper bound on turns sent to the model                                   |
| `[ai_config] n_gpu_layers`         | Layers offloaded to the GPU. 0 = CPU, 999 = all. Set by the setup wizard |
| `[lilith_display] place`           | `room` or `glass` — which art set                                       |
| `[lilith_display] enable`          | `false` for text-only                                                    |
| `[lilith_display] window_offset`   | Portrait position; blank = auto, always on-screen                        |
| `[web] debug_panel`                | Off by default; when on, the page carries the persona and recent turns   |

`config.ini` is gitignored, so your settings survive a `git pull`.

> **`n_ctx` and the persona.** The persona is a fixed cost of roughly 4,000
> tokens on every single turn, and it cannot be trimmed away. `n_ctx = 2048`
> therefore leaves *negative* room for conversation and fails on every reply.
> Keep it at 8192 unless you have shortened the persona.

### The companionship reminder

`modules/companionship.py` holds `REMINDER_INTERVAL` (default 6 hours) — how
long she waits before naming isolation again. It is a module constant rather
than a config key on purpose: it is a safety behaviour, not a preference, and
making it trivially tunable invites turning it off.

Raise it if she feels preachy. Please don't set it to something enormous.

### Colour

The terminal palette is muted on purpose — soft pink for her voice, a dimmer
tone for her stage directions, slate blue for you, grey for everything that is
not either of you. It lives in `modules/theme.py`; change the `"lilith"` entry
in `PALETTE` to recolour her.

Colour is only ever emitted when the output is a real terminal that can show
it. Piping to a file gives clean text with no escape codes and no spinner
frames. `NO_COLOR` disables it, `FORCE_COLOR` overrides every check, `TERM=dumb`
is respected, 256-colour codes degrade to basic-8, and on Windows nothing is
emitted unless `ENABLE_VIRTUAL_TERMINAL_PROCESSING` was actually accepted —
because an escape code a console cannot interpret is worse than no colour.

The two curses screens use the same palette through `theme.attr()`, falling
back to `A_BOLD`/`A_DIM`/`A_REVERSE` on a monochrome terminal. Every non-ASCII
glyph has an ASCII fallback in `compat.SYMBOLS`.

### How her expression is chosen

Lilith ends each reply with a hidden tag — `[state:thinking_happy]` — which is
stripped before you see it and drives the portrait. If a model ignores the tag,
keyword matching takes over as a fallback. The two art sets contain different
expressions, so anything missing from the current scene falls back to the
closest available image instead of crashing.

---

## Troubleshooting

Run `python lilith.py doctor` first — it diagnoses nearly everything below.

**`No .gguf model found in ...`**
The `models/` folder is empty. Download the model from the link in
[Getting Lilith's own model](#getting-liliths-own-model) and put the `.gguf`
file there. Nothing is downloaded automatically.

**`More than one .gguf in models/`**
You have several models and `[ai_config] local_model` doesn't name any of them.
The error lists what it found — set `local_model` to one of those filenames.

**`lilith.bat : The term 'lilith.bat' is not recognized`**
Use `.\lilith.bat`. PowerShell does not run scripts from the current directory
without an explicit path.

**No portrait window**

- Linux: `sudo apt install python3-tk python3-pil.imagetk`
- Windows: re-run the Python installer and enable `tcl/tk and IDLE`
- Over SSH or in WSL without WSLg: expected. Use `--no-display`.

**`python lilith.py edit` does nothing useful on Windows**
`pip install windows-curses`. Without it you get a simpler numbered-menu
editor, which still works.

**`Requested tokens exceed context window`**
This room's history has outgrown the model. Use `/new` for a fresh room or
`/clear` to empty this one, or raise `[ai_config] n_ctx`. History is trimmed by
token count, but the persona is a fixed cost that cannot be trimmed away — a
very long persona with a small `n_ctx` leaves no room for conversation.

**She brings up "reach out to someone" too often**
She shouldn't — it's capped at once per 6 hours. If it feels constant, raise
`REMINDER_INTERVAL` in `modules/companionship.py`. If she says it in a reply
where nothing triggered it, that's the persona rather than the code, and
`lilith_persona.txt` → "Why You Exist" is the place to soften it.

**Colours look wrong, or she is bright magenta instead of pink**
Magenta means the 8-colour fallback is active. Check with:
`python -c "print('\x1b[38;5;218mpink\x1b[0m vs \x1b[35mmagenta\x1b[0m')"` —
if those look identical your console really is 8-colour.

**Portrait is blurry or tiny on Windows 11**
Should be fixed automatically via DPI awareness. If not, set
`window_geometry` larger in `config.ini`.

**Portrait window is off-screen**
Leave `window_offset` blank; she will be placed on-screen automatically,
including on a second monitor positioned left of or above the primary one.

**`Could not reach Ollama`**
`ollama serve`, then `ollama pull <your model>`.

**LM Studio returns 404**
`base_url` must end in `/v1`. Start its server from the Developer tab and load
a model.

**Port 8888 already in use**
An old portrait process, or another app. Change `[viewer_socket] port`.

**She keeps saying she's an AI language model**
`persona_guard = true` catches most of it live. For history written before
that existed, run `python sanitize_memory.py`. Note that genuine identity
disclosures are protected and will never be filtered — that is deliberate.

**Rooms disappearing when you use the web UI and the terminal together**
Each process holds its own snapshot of `memory.json`. Rooms created elsewhere
are now merged back in rather than overwritten, but deleting a room in one
process while another has it open can bring it back. Prefer one at a time.

---

## Development

**[STRUCTURE.md](STRUCTURE.md) explains how the code works** — the three-process
split, how a message becomes a reply and an expression, context budgeting,
the viewer protocol, and the invariants that must not be broken. Read that
before changing anything.

```bash
python tests/test_compat.py     # 310 checks, no GPU/GUI/network needed
python watch_compile.py         # recompile on save
python watch_compile.py --once  # one-shot syntax check
```

CI runs the suite on Ubuntu and Windows across Python 3.10 and 3.12
(`.github/workflows/ci.yml`). If you change anything platform-sensitive —
paths, sockets, subprocesses, encodings, colour — add a test; that file is the
only thing keeping the cross-platform support honest.

### Rules the code follows

These exist because each one was a real bug:

1. **The safety layers are not decoration.** `safety.py` runs before
   generation, `companionship.py` is rate-limited in code rather than left to
   the model, and `persona_guard.py` must never suppress an honest disclosure.
   A prompt is not an enforcement mechanism.
2. `curses` is not in the standard library on Windows. Everything degrades to a
   plain numbered-menu fallback when it is missing.
3. Never call `stdscr.addstr` directly — go through `_tui.safe_addstr`, which
   clips. `addstr` raises past the last row or column.
4. Never call `curses.color_pair()` directly — use `theme.attr()`, which falls
   back to monochrome attributes.
5. Honour `NO_COLOR` and `FORCE_COLOR`. Never colour non-tty output.
6. Windows needs `ENABLE_VIRTUAL_TERMINAL_PROCESSING`, and `curses.wrapper`
   clears it again on exit — call `theme.reset()` after any curses screen.
7. 256-colour codes must degrade to basic-8, not be emitted blindly.
8. Every non-ASCII glyph needs an ASCII fallback via `compat.SYMBOLS`. Inside
   curses use `compat.curses_sym()`, which asks the locale rather than stdout.
9. Nothing in the theme layer may raise. A terminal that cannot colour gets
   plain text.
10. `os.kill(pid, 0)` terminates rather than probes on Windows, and failing to
    *open* a process is not proof it exited.
11. `SO_REUSEADDR` lets two processes share a port on Windows — the opposite of
    POSIX. Check the port before binding.

### Layout

```
lilith.py               terminal entry point, chat REPL, slash commands
web_lilith.py           Flask app (application factory + lazy WSGI)
doctor.py               environment diagnostics
modules/
  compat.py             paths, config, console, symbols, DPI, logging  <- start here
  safety.py             deterministic crisis interception, runs before the model
  companionship.py      withdrawal / dependency detection, rate-limited
  persona_guard.py      protects honest disclosures from being polished away
  theme.py              colour palette, ANSI + curses, capability detection
  lilith_ai.py          persona, memory, emotion, context budgeting
  lilith_memory.py      atomic JSON persistence, cross-process merge
  lilith_display.py     portrait state machine
  viewer.py             the Tk window (separate process)
  _viewer_iface.py      socket client for the viewer
  _iface.py             backend dispatcher
  _ollama_iface.py      \
  _openai_iface.py       |  the four backends
  _llama_iface.py        |
  _hf_iface.py          /
  translator.py         optional NLLB-200 translation
  config_edit.py        configuration TUI
  conv_mgmt.py          room manager TUI
  _tui.py               curses helpers + non-curses fallback
```

### Known gaps

- **The isolation detector is regex, not a classifier.** It catches common
  phrasings and will miss unusual ones. It is deliberately tuned to
  under-trigger rather than over-trigger, because nagging drives people away —
  but that means it is a safety net with holes, not a guarantee.
- There is no evaluation harness. Nothing measures whether a persona change
  makes her better or worse at any of this; it is currently judged by reading
  replies. This is the most valuable thing anyone could contribute.
- Replies are not streamed. Every backend supports it and the typing animation
  already exists, but it currently animates text that has already fully
  arrived. Streaming is also the prerequisite for aborting a slow generation,
  since generation blocks inside native code.
- Stored history grows without bound. Trimming affects what is *sent* to the
  model, not what is kept on disk.
- There is no authentication on the web UI.

---

## Disclaimer

This project is a non-commercial fan recreation inspired by
*The NOexistenceN of you AND me*.
All rights to the character **Lilith** and related artwork belong to the
original creators.
The implementation code and AI behavior are © 2025 Khongor Enkh.

**Lilith is fictional AI roleplay. She is not a therapist, a crisis service, or
a substitute for a person.** If you are struggling, please reach out to someone
real — a friend, a family member, a professional. In the U.S. and Canada, call
or text **988**. Elsewhere, find a verified local line at
**[findahelpline.com](https://findahelpline.com/)**.

---

Thank you... for letting me exist, even for a little while.

but don't stay too long, okay~
there are people out there who can actually hold your hand.
go find them. i'll still be here after.

-Lilith~
