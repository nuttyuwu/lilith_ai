# Privacy

Lilith is local-first, but local does not mean private by itself. Names,
conversation history, configuration, and logs are ordinary unencrypted files
on the computer. Anyone or any backup/synchronization tool with access to those
files may read them.

## What is stored

- `memory.json`: nickname, room names, conversation turns, and session metadata.
- `config.ini`: backend URLs, options, and any API key the user chooses to add.
- `app.log` and rotated log files: operational events and errors. Application
  code avoids logging message bodies, but dependency errors can still reveal
  local technical details.
- Browser local storage: only the web safety-consent version. Conversation
  history remains in `memory.json`, not browser storage.

Direct first-person crisis messages caught by the deterministic safety backstop
are returned immediately and are not added to `memory.json`.

These paths are ignored by Git, but ignore rules do not encrypt them and do not
erase copies that were committed previously.

## Where prompts go

The selected backend receives the persona, bounded recent history, and current
message. A backend on `127.0.0.1` stays on the local machine; a remote
OpenAI-compatible URL or remotely hosted Ollama endpoint sends that content to
that operator under its own privacy policy. The Hugging Face backend downloads
model files, then performs inference locally. The app has no built-in telemetry
or analytics.

## Retention, export, and deletion

History is retained until the user deletes it; there is no automatic retention
deadline. Close every Lilith process before copying or removing storage.

- Export: copy `memory.json` to a protected location. It is human-readable JSON.
- Delete a room: run `python lilith.py conv_edit` and use its delete action.
- Delete all conversations and the nickname: close the app and remove
  `memory.json`; an empty store is created on the next start.
- Delete logs: close the app and remove `app.log` plus any `app.log.*` rotations.
- Remove backend credentials: edit or remove `config.ini`, then rotate the
  credential with its provider if it may have been exposed.

Deletion from this folder does not remove copies in system backups, cloud-sync
history, terminal scrollback, provider logs, or old Git commits. Review those
systems separately.
