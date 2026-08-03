# Lilith AI version history

The current version is read from [`VERSION`](VERSION). This file records what
changed in each release and, where the old repository only used commit names,
preserves those uploads as a dated development timeline.

## V0.1A - 2026-08-03

Major overhaul and refactoring release. This is a substantial architectural,
reliability, portability, and usability update over V0.01a.

### Architecture and startup

- Refactored the terminal entry point so importing `lilith.py` has no side
  effects. Argument parsing, display creation, and process startup now happen
  only when the application is run.
- Centralised paths, configuration loading, platform checks, atomic file
  writes, terminal capability detection, and compatibility helpers in
  `modules/compat.py`.
- Added clean shutdown and Ctrl+C handling so portrait processes, sockets, and
  background work are not left behind.
- Added first-run setup for the user's name, portrait scene, and llama.cpp
  GPU/CPU mode. Existing installations are left unchanged.
- Added structured logging and clearer, actionable errors throughout.

### AI backends

- Standardised backend selection behind a shared interface with normalised
  backend names and configuration.
- Repaired the Hugging Face backend: it now uses model chat templates, decodes
  only newly generated tokens, handles current library APIs, and supports
  symlink-free Windows downloads.
- Reworked llama.cpp model discovery and path handling, uses GGUF chat
  templates, defaults thread count to available CPUs, and gives actionable
  missing-model errors instead of silently downloading large files.
- Corrected LM Studio/OpenAI-compatible URLs to use `/v1`, added timeouts, and
  safely handles empty response content.
- Added Ollama host configuration, response controls, timeouts, and readable
  connection failures.
- Moved context trimming into the central AI layer so every backend respects
  context limits consistently.

### Persona, memory, and conversations

- Added multiple named conversations with create, switch, rename, and delete
  support in both interactive commands and the conversation manager.
- Made memory writes atomic and thread-safe, then added a cross-process lock and
  three-way merge so concurrent same-room appends survive. Corrupt memory is
  backed up rather than discarded, and legacy memory is migrated without
  repeating warnings.
- Added time awareness and elapsed-time context so Lilith can notice the hour
  and how long the user has been away.
- Added a persona diagnostic that flags generic assistant boilerplate without
  regenerating or replacing identity disclosures, capability limits, or safety
  refusals; the memory sanitiser supports both legacy and multi-conversation
  layouts.
- Expanded and refined persona material while keeping user data out of the
  repository through a memory template.

### Portrait and interface

- Rebuilt the portrait viewer protocol with explicit framing, serialised
  socket writes, timeouts, startup synchronisation, and clean shutdown.
- Fixed portrait startup races, frozen blink loops, stale revert timers, and
  missing-expression crashes with scene-aware emotion fallbacks.
- Added headless display support for the web UI and CI.
- Added a portable terminal UI layer with Windows curses support, plain-text
  fallbacks, bounded drawing, scrolling lists, and a muted adaptive theme.
- Reworked the configuration editor to validate values, resolve the project
  root correctly, enforce safe numeric ranges, and save only on explicit
  confirmation using atomic writes.

### Web interface and deployment

- Rebuilt the Flask application around an app factory so development,
  Waitress, and Gunicorn use the same startup path without launching Tk.
- Added safe JSON request handling and emotion fallbacks that prevent portrait
  404s.
- Added Waitress support on Windows.
- Fixed the static-site builder by supplying every required Jinja value and
  avoiding local debug-path leakage; generated assets now work below a Pages
  repository subpath and API configuration is JSON-encoded.
- Restricted the web boundary to loopback and added an adults-only fictional-AI
  disclosure plus explicit browser consent marker before chat requests.
- Added GitHub and GitLab CI coverage and documented the full project
  structure in `STRUCTURE.md`.

### Installation and tooling

- Reworked Windows batch, PowerShell, and Unix launchers to run from their own
  directory, locate a compatible Python, create the virtual environment,
  install changed requirements, pass command arguments through, and explain
  failures clearly.
- Added an explicit first-run adult fictional-roleplay, parasocial/tulpa-theme,
  plaintext-storage, and mental-health notice. Versioned consent is recorded
  only with the completed setup;
  ordinary second-file save failures trigger a best-effort memory rollback.
- Added `python lilith.py doctor` for platform-aware checks of Python, Tk,
  curses, assets, ports, configuration, backends, the web stack, and optional
  translation dependencies.
- Split heavyweight optional dependencies into backend-specific requirement
  files and documented CPU, CUDA, Vulkan, ROCm, SYCL, and Metal choices.
- Added a pinned development audit requirement and the exact core dependency
  resolution validated on Windows 11 / CPython 3.12. Other operating systems
  and Python minors do not yet have published constraints.
- Replaced the hard-coded compile watcher with project-wide Python discovery.
- Expanded the automated compatibility suite, including configuration,
  memory migration, backend, display, first-run, and static-build behavior.

### Verification at release review

- All project Python files compile successfully on Python 3.12.10 / Windows
  11.
- `doctor.py` completes without crashing; live backend reachability remains an
  environment-dependent check and is not claimed as release-verified.
- The repository's compatibility suite passes all 293 checks, plus 9 focused
  safety and backend tests.

## Development uploads after V0.01a

The original public repository did not publish formal releases or tags. The
following timeline preserves the meaningful upload history recorded on its
`main` branch between V0.01a and the V0.1A overhaul. Merge-only, deploy-only,
and README-only commits are condensed so this remains useful as a product
history rather than a raw Git log.

### 2026-01-14

- Merged the accumulated contributor overhaul into `main` (pull request #5).

### 2025-12-20 to 2025-12-28

- Added the terminal configuration interface and multiple conversations.
- Followed with general fixes, cleanup, and documentation updates.

### 2025-11-08

- Updated and refined Lilith's persona.

### 2025-11-07

- Changed the portrait viewer system and corrected memory handling.
- Added a new portrait scene.
- Applied follow-up bug fixes and documentation updates.

### 2025-11-06

- Added Ollama model/backend support.
- Removed an accidentally tracked virtual environment.

### 2025-11-03 to 2025-11-05

- Performed several rounds of code cleaning, simplification, debugging, and
  refactoring, then merged the result through pull requests #3 and #4.

### 2025-11-02

- Added nickname support.
- Removed personal memory from the repository and replaced it with a safe
  template.
- Added Windows improvements and follow-up bug fixes.

## V0.01a - 2025-10-26

- First alpha update after V0.01.
- Added deployment-related updates to the initial local companion release.

## V0.01 - 2025-10-25

- Initial Lilith AI implementation and README.
- Added the MIT license and refined the setup documentation.
