# Reliable hosting and storage evidence

Scope: three priorities accepted in the conversation: production server,
process crash recovery, and reliable memory storage. Existing UI, artwork,
personas, and earlier working-tree edits were preserved.

## Tests before implementation

`python -m unittest discover -s tests -p test_sqlite_memory.py` initially
failed migration/preservation/schema tests because the store treated SQLite
paths as JSON. The supervisor tests failed to import the missing `hosting`
module. The SQLite test's separate Windows connection-cleanup issue was
corrected using explicit connection closure before GREEN.

RED checkpoint: `657c59f`. Initial implementation checkpoint: `458b69e`.
Final integration is recorded in the next checkpoint on this same branch.

## Verified guarantees

| Guarantee | Evidence | Result |
|---|---|---|
| JSON import preserves rooms, metadata, original file | `tests/test_sqlite_memory.py` | PASS |
| Same-process and separate-process saves preserve both appends | `tests/test_sqlite_memory.py` | PASS |
| Invalid saves retain the committed state | `tests/test_sqlite_memory.py` | PASS |
| Future schema and invalid legacy memory refuse migration | `tests/test_sqlite_memory.py` | PASS |
| Daily backups are valid SQLite snapshots; retain seven | `tests/test_sqlite_memory.py` | PASS |
| Cleanup supports SQLite with JSON export backup | `tests/test_sqlite_memory.py` | PASS |
| Process restarts use bounded backoff and stop disables restart | `tests/test_hosting.py` | PASS |
| Windows monitors actual server interpreter; shutdown failures are isolated | `tests/test_hosting.py` | PASS |
| Duplicate supervisor refused; public/debug and missing-Waitress refused | `tests/test_hosting.py` | PASS |
| Live Lilith and Mira migration matches original complete documents | Deployment comparison | PASS |
| Forced app and tunnel exit recovers public HTTPS health | Live recovery experiment | PASS |
| Mira chat survives the forced restart | Database read after recovery | PASS |

Final suite: `python -m unittest discover -s tests`: 61 tests passed.
Compatibility suite: `python tests/test_compat.py`: 310 checks passed.
Coverage command: `python -m coverage run --source=hosting,modules.sqlite_memory -m unittest discover -s tests`
followed by `python -m coverage report -m`: supervisor 88%, SQLite 98%, total 91%.

Live experiment: web PID 5732 restarted as 2032; tunnel PID 16460 restarted as
30896. Public authenticated `/health` returned `ok`, and the pre-restart Mira
message remained in SQLite. A public Mira reply was generated on the upgraded
server. Password and hostname are unchanged. Startup shortcut uses supervisor.

Limits: process exit recovery does not diagnose arbitrary hangs. Startup is
at Windows user sign-in, and the host PC must remain online. Backups are daily
recovery snapshots rather than after each message. Supervisor-module coverage
includes simulated failures and a real Windows recovery experiment; POSIX-only
lock/shutdown branches were not exercised on this Windows host.
