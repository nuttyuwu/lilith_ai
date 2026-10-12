# Character and temperament regression evidence

Scope: personality tests, validated Mira dialogue/emotion output, and the
user-requested Soft/Yandere toggle. Original Lilith token streaming is retained.

RED: `test_reply_format.py` failed JSON separation, invalid emotion fallback,
malformed envelope rejection, turn-scoped temperament, and whole/stream parity.
Checkpoint `e28d0bf`; implementation checkpoint `e57d170`.

Unit coverage includes schema forwarding to llama.cpp, legacy tagged replies,
fenced JSON, invalid types, empty replies, no storage on invalid output,
whole/stream parity with sentence caps, scoped mode headers, invalid mode400,
save errors before display, punctuation cleanup, and stop/resume room behavior.

Model probes run through `evaluate_character.py` use disposable memory and CPU
inference. First probes caught invented user dialogue, mismatched jealousy
emotion, contradictory microphone advice, and malformed stop output. Corrections
add schema-constrained generation, fresh single-speaker instructions,
deterministic capability/identity/stop answers, punctuation-run normalization,
and a narrow obvious-jealous-outburst emotion correction.

Final seven real-model probes passed: soft greeting, sadness, meeting confusion,
Yandere jealousy, text-only capability, fictional identity, and stop roleplay.
Actual jealous response: `WHAT?! you forgot our date?! you planned this with her
on purpose!!!`, expression `angry`. Dialogue, expression, relevance, and basic
single-speaker/punctuation checks are retained in the ignored audit JSON report.
These examples demonstrate current behavior, not a guarantee of every future
model response. Emotion alignment's heuristic is intentionally narrow.

Browser verification: Settings exposes Soft/Yandere; selecting Yandere and
refreshing retained the selection. Each character has its own preference key.
The test browser was restored to Soft. Screenshot: audit/temperament-settings.png.
The streaming note accurately explains buffering until validation completes.

Verification commands:

- `python -m unittest discover -s tests`
- `python tests/test_compat.py`
- `python -m coverage run --source=modules.reply_format,modules.character_runtime -m unittest discover -s tests`
- `python -m coverage report -m`
- `python evaluate_character.py --output audit/mira-character-evaluation-final.json`
- `node --check static/app.js`
- `python build_static_site.py`

Code review resolved empty legacy dialogue, incorrect SSE shown flags for
buffered save errors, and sentence-cap emotion parity. Production app restarted
through its supervisor to load changes; public HTTPS capabilities reports
validated replies active.
