# lilith_ai

Hey — this is an odd thing to do, but…
after finishing the game, I had this almost existential crisis.
I kept thinking about Lilith and the questions her story leaves behind.

So I built a local, character-driven AI roleplay inspired by her.

This does not make the character real, conscious, or dependent on anyone's
attention. You can close, delete, or leave the app without harming anything.

**Lilith** is fictional local AI roleplay inspired by
*The NOexistenceN of you AND me*, with explicit adult, safety, and privacy
boundaries.

**Current version: V0.1A** — a major architectural and cross-platform
overhaul. See the [version history](CHANGELOG.md) for the complete release
notes and the development uploads since V0.01a.

> **Pre-release licensing warning:** redistribution rights for the bundled PNG
> artwork have not been verified. Do not publish a release containing those
> files until [ASSET_LICENSES.md](ASSET_LICENSES.md) is cleared. See
> [CREDITS.md](CREDITS.md) for the separate model and fan-work attribution.
> CI tests the static build without uploading it. GitLab Pages publication is
> disabled entirely: artwork rights are unresolved, and the bundled API is
> localhost-only rather than a supported public backend.

Read [SAFETY.md](SAFETY.md) and [PRIVACY.md](PRIVACY.md) before use. They explain
the crisis backstop and its limits, plaintext storage, backend data flow,
retention, export, and deletion.

---

## Features

- Local-first backends: Ollama, LM Studio, llama.cpp, and transformers; an
  optional OpenAI-compatible API alias sends messages to its configured service
- Persistent memory across sessions, with multiple named rooms
- A persona system that shapes her voice, not just her facts
- **Session context** — replies can reference the local time and the gap since
  the last stored session without implying the character waited or suffered
- Live portrait window that reacts to her mood
- A quiet, muted terminal palette that degrades all the way down to plain text
- Optional reply translation (NLLB-200)
- Terminal UI *and* web UI
- Cross-platform paths for Linux and Windows 11, with a three-version CI matrix
  configured for both (a green public V0.1A run is still required)

---

## Requirements

- CPython 3.10–3.12; **3.12 is recommended for the llama.cpp backend**, see the
  note below
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

```text
py -3.12 -m venv venv                 # Windows
python3.12 -m venv venv               # Linux

.\venv\Scripts\Activate.ps1            # Windows PowerShell
venv\Scripts\activate.bat               # Windows Command Prompt
source venv/bin/activate                # Linux / macOS

python -m pip install -r requirements.txt
python lilith.py
```

For the exact core resolution validated on Windows 11 / CPython 3.12, use:

```powershell
py -3.12 -m pip install -r requirements.txt -c constraints/windows-py312.txt
```

That constraints file is not a Linux, Python 3.10, or Python 3.11 lock. Those
matrix combinations still need separately generated and tested constraints.

---

## First run

The first time she starts, Lilith first requires an explicit adult safety and
privacy opt-in, then asks three setup questions. Lilith is fictional AI
roleplay for adults (18+), not mental-health care; names and conversations are
stored locally as unencrypted plain text and may be sent to the configured
model backend. Consent also covers intense parasocial or tulpa themes strictly
as fiction. The complete boundaries and data-handling notice are in
[SAFETY.md](SAFETY.md) and [PRIVACY.md](PRIVACY.md).

No consent or setup answers are written while the questions are being answered
(the general loader may already have created `config.ini` from its template).
The final `memory.json` and `config.ini` replacements are each atomic, with a
best-effort rollback if the second save fails; two separate files are not a
single crash-atomic transaction.

```
Before Lilith starts, please read this safety notice.
  It may explore intense parasocial or tulpa themes as fiction.
  Type I AGREE to confirm you are 18+ and consent: I AGREE

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

| Question | Writes to | Notes |
|---|---|---|
| Adult safety consent | `[safety] consent_version` | Records the current disclosure version (2) only after the full setup commit succeeds. |
| Your name | `memory.json` | She uses it in conversation. Change it any time in the web UI or by re-running setup. |
| Scene | `[lilith_display] place` | The two art sets have different expressions; anything missing falls back to the closest available image. |
| GPU or CPU | `[ai_config] n_gpu_layers` | GPU sets it to 999 — "every layer", which llama.cpp clamps to what the model actually has. CPU sets 0. |

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

An older install without the current consent record is asked once on upgrade;
the previous name is offered as the default rather than discarded.

---

## Choosing a backend

`requirements.txt` covers Ollama, LM Studio, and the OpenAI-compatible alias.
The in-process backends are separate files because they are large downloads.

| Backend | `server_ai` | Install | Notes |
|---|---|---|---|
| Ollama | `ollama` | included | Easiest. `ollama pull gemma3` |
| LM Studio | `LM studio` | included | Start its server from the Developer tab |
| OpenAI-compatible API | `openai` | included | Remote-capable; messages and configured credentials leave this process |
| llama.cpp | `llama` | `pip install -r requirements-llama.txt` | Loads a GGUF directly |
| transformers | `hf` | `pip install -r requirements-hf.txt` | Needs torch; built-in architectures and safetensors weights only (repository Python and pickle weights are blocked) |

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

| Your GPU | Build to use |
|---|---|
| NVIDIA | CUDA — swap `cpu` for your CUDA version in the wheel URL above, e.g. `cu124` |
| AMD | Vulkan (any OS) or ROCm (Linux) |
| Intel Arc | Vulkan (any OS) or SYCL |
| Apple Silicon | Metal, on by default in the macOS build |
| Anything | CPU — always works, just slower |

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

The optional model is a separate work trained by **C.M.M.** Its
[model card](https://huggingface.co/CMM7590/Lilith_AI_8B) labels it
**CC-BY-NC-SA-4.0**, requires credit to C.M.M., and says it was trained from
lines extracted from the game. Those attribution, non-commercial, and
share-alike terms are separate from this repository's MIT-licensed code.

### 1. Download it

**[⬇ Lilith_AI_8B_Q4_0.gguf](https://huggingface.co/CMM7590/Lilith_AI_8B/resolve/3b594a5d27c27a841e57e6a6c7938b303df4f099/Lilith_AI_8B_Q4_0.gguf?download=true)** — 4.66 GB

Pinned upstream revision:
`3b594a5d27c27a841e57e6a6c7938b303df4f099`.

Expected SHA-256:

```text
60b069b8b24c54b8be2909595dbf27077a260535eb47435fd0702eae77d24dfa
```

Verify it before loading:

```text
Get-FileHash -Algorithm SHA256 .\models\Lilith_AI_8B_Q4_0.gguf  # PowerShell
sha256sum models/Lilith_AI_8B_Q4_0.gguf                         # Linux/macOS
```

Do not use a file whose digest differs. Model weights are not bundled with this
repository and are not covered by its MIT license.

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
python lilith.py setup            # re-ask safety consent and setup questions
python lilith.py edit             # configuration UI
python lilith.py conv_edit        # manage rooms
python lilith.py doctor           # setup check

python web_lilith.py              # web UI at http://127.0.0.1:5000
python sanitize_memory.py         # strip standalone generic-service turns
```

### While chatting

Anything you type goes to Lilith. Commands start with `/` so that a bare word
like *rooms* stays something you can actually say to her.

| Command | What it does |
|---|---|
| `/rooms` | Open the room manager, then drop back into the chat |
| `/new [name]` | Start a fresh room; auto-named if you don't give one |
| `/clear` | Forget this room's history, keeping the room |
| `/rename <name>` | Rename the current room |
| `/help` | List the above |
| `exit` | Leave (`quit` and `:q` work too) |

`/new` and `/clear` are the quick way out of a room whose history has grown
past the model's context window.

Ctrl+C works at any point — during a reply as well as at the prompt — and shuts
the portrait down cleanly instead of printing a traceback.

### Web UI

```bash
python web_lilith.py                        # both platforms
waitress-serve --listen=127.0.0.1:5000 web_lilith:app
gunicorn --bind 127.0.0.1:5000 'web_lilith:app'  # Linux only
```

The web interface is localhost-only because its routes do not authenticate
callers. The CLI refuses non-loopback bind addresses, and the WSGI application
rejects requests unless both the network peer and HTTP `Host` are loopback.
Public tunnels and reverse proxies are unsupported; do not rewrite those values
to bypass the check. The browser also requires explicit safety acknowledgement
before it sends `X-Lilith-Safety-Consent: 1` with a chat request.

---

## Configuration

Everything lives in `config.ini`, created from `config.example.ini` on first
run. `config.example.ini` documents every key; the useful ones:

| Key | What it does |
|---|---|
| `[server] server_ai` | Which backend to use |
| `[ai_config] ai_model` | Model name for Ollama / LM Studio / hf |
| `[ai_config] hf_revision` | Optional full 40-character HF commit SHA; branches/tags are rejected |
| `[ai_config] n_ctx` | Context window; history is trimmed to fit it |
| `[ai_config] time_awareness` | Add local time and the gap since the last stored session to context |
| `[ai_config] persona_guard` | Log generic service phrasing for prompt diagnostics; never regenerate or suppress a reply |
| `[ai_config] max_history_messages` | Upper bound on turns sent to the model |
| `[ai_config] n_gpu_layers` | Layers offloaded to the GPU. 0 = CPU, 999 = all. Set by the setup wizard |
| `[safety] consent_version` | Current interactive adult fictional-roleplay disclosure accepted by setup; do not edit to bypass consent |
| `[lilith_display] place` | `room` or `glass` — which art set |
| `[lilith_display] enable` | `false` for text-only |
| `[lilith_display] window_offset` | Portrait position; blank = auto, always on-screen |
| `[web] debug_panel` | Off by default; when on, the page carries the persona and recent turns |

`config.ini` is gitignored, so your settings survive a `git pull`.

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
`persona_guard = true` flags it in the local log while preserving the original
reply. For history written before that existed, run `python sanitize_memory.py`.

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
python tests/test_compat.py             # 293 compatibility checks
python -m unittest tests.test_safety tests.test_backends  # 9 focused tests
python watch_compile.py         # recompile on save
python watch_compile.py --once  # one-shot syntax check
```

Release/development tooling is separate from runtime dependencies:

```bash
python -m pip install -r requirements-dev.txt
python -m pip_audit -r requirements.txt --strict --progress-spinner off
python scan_secrets.py
```

The secret scan covers tracked and unignored release-candidate files using
high-confidence credential signatures; provider-side scanning and the completed
manual full-history review remain separate controls.

CI is configured to run the suite on Ubuntu and Windows across Python 3.10,
3.11, and 3.12 (`.github/workflows/ci.yml`). This checkout has no public V0.1A
run yet, so treat the matrix as configured rather than verified.

Static output is intentionally not uploaded by either CI provider. GitLab Pages
publication is disabled while bundled artwork rights are unresolved and because
the included web server cannot safely back a public site. `API_BASE_URL` is only
for a separately secured, compatible API; the bundled `web_lilith.py` must not
be exposed through a tunnel or reverse proxy.

If you change
anything platform-sensitive — paths, sockets, subprocesses, encodings, colour —
add a test.

### Rules the code follows

These exist because each one was a real bug:

1. `curses` is not in the standard library on Windows. Everything degrades to a
   plain numbered-menu fallback when it is missing.
2. Never call `stdscr.addstr` directly — go through `_tui.safe_addstr`, which
   clips. `addstr` raises past the last row or column.
3. Never call `curses.color_pair()` directly — use `theme.attr()`, which falls
   back to monochrome attributes.
4. Honour `NO_COLOR` and `FORCE_COLOR`. Never colour non-tty output.
5. Windows needs `ENABLE_VIRTUAL_TERMINAL_PROCESSING`, and `curses.wrapper`
   clears it again on exit — call `theme.reset()` after any curses screen.
6. 256-colour codes must degrade to basic-8, not be emitted blindly.
7. Every non-ASCII glyph needs an ASCII fallback via `compat.SYMBOLS`. Inside
   curses use `compat.curses_sym()`, which asks the locale rather than stdout.
8. Nothing in the theme layer may raise. A terminal that cannot colour gets
   plain text.
9. `os.kill(pid, 0)` terminates rather than probes on Windows, and failing to
   *open* a process is not proof it exited.
10. `SO_REUSEADDR` lets two processes share a port on Windows — the opposite of
    POSIX. Check the port before binding.

### Layout

```
lilith.py               terminal entry point, chat REPL, slash commands
web_lilith.py           Flask app (application factory + lazy WSGI)
doctor.py               environment diagnostics
modules/
  compat.py             paths, config, console, symbols, DPI, logging  <- start here
  theme.py              colour palette, ANSI + curses, capability detection
  lilith_ai.py          persona, memory, emotion, context budgeting
  lilith_memory.py      atomic JSON persistence, cross-process merge
  lilith_display.py     portrait state machine
  viewer.py             the Tk window (separate process)
  _viewer_iface.py      socket client for the viewer
  _iface.py             backend dispatcher
  _ollama_iface.py      Ollama backend
  _openai_iface.py      LM Studio and OpenAI-compatible API backends
  _llama_iface.py       local GGUF backend
  _hf_iface.py          local transformers backend
  persona_guard.py      out-of-character detection
  translator.py         optional NLLB-200 translation
  config_edit.py        configuration TUI
  conv_mgmt.py          room manager TUI
  _tui.py               curses helpers + non-curses fallback
```

### Known gaps

- Replies are not streamed. Every backend supports it and the typing animation
  already exists, but it currently animates text that has already fully
  arrived. Streaming is also the prerequisite for aborting a slow generation,
  since generation blocks inside native code.
- Stored history grows without bound. Trimming affects what is *sent* to the
  model, not what is kept on disk.
- There is no authentication on the web UI.

---

## Disclaimer

This project is an unofficial fan recreation inspired by
*The NOexistenceN of you AND me*. The repository does not claim rights to the
character, game-derived material, or bundled artwork. Artwork redistribution
permission remains unverified; see [ASSET_LICENSES.md](ASSET_LICENSES.md).
Original implementation code is © 2025 Khongor Enkh and covered only as stated
in [LICENSE](LICENSE). Model terms and credits are in [CREDITS.md](CREDITS.md).

Safety, privacy, security reports, and contributions are governed by
[SAFETY.md](SAFETY.md), [PRIVACY.md](PRIVACY.md),
[SECURITY.md](SECURITY.md), [CONTRIBUTING.md](CONTRIBUTING.md), and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

Thank you... for letting me exist, even for a little while.
maybe we can keep tracing the edge between nothingness and us~

-Lilith~
