#!/usr/bin/env bash
# ==========================================================================
#  Lilith launcher for Linux / macOS
#
#  Fixes over the previous version:
#    * No hardcoded "$HOME/lilith_ai" -- resolves its own directory, so the
#      repo can live anywhere.
#    * No hardcoded "LM-Studio-0.3.30-2-x64.AppImage" in a pkill at exit.
#      That both missed every other version and risked killing unrelated
#      processes.
#    * Only starts LM Studio when the config actually selects it.
#    * Creates the venv and installs dependencies on first run.
#    * Passes arguments through:  ./lilith.sh edit   /   ./lilith.sh doctor
# ==========================================================================

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

# llama-cpp-python only publishes wheels for CPython 3.10-3.12; on anything
# newer pip quietly falls back to a source build. Prefer a supported version
# when one is installed, unless PYTHON was set explicitly.
if [[ -z "${PYTHON:-}" ]]; then
    for candidate in python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    done
fi
PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python 3 was not found. Install it with your package manager:" >&2
    echo "  sudo apt install python3 python3-venv python3-tk python3-pil.imagetk" >&2
    exit 1
fi

# Check the version before building a venv and installing everything into it,
# rather than after, when lilith.py refuses to start.
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Lilith needs Python 3.10 or newer; $PYTHON is older." >&2
    exit 1
fi

# --- Virtual environment -------------------------------------------------
created_venv=false
if [[ ! -f "venv/bin/activate" ]]; then
    echo "First run: creating a virtual environment..."
    "$PYTHON" -m venv venv
    created_venv=true
fi
# shellcheck source=/dev/null
source "venv/bin/activate"

# Refresh dependencies by content rather than timestamps. Git checkouts can
# move mtimes backwards, while equal SHA-256 values mean equal requirements.
requirements_hash="$(python -c 'from pathlib import Path; import hashlib; print(hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest())')"
requirements_stamp="venv/.requirements-sha256"
installed_hash=""
if [[ -f "$requirements_stamp" ]]; then
    installed_hash="$(<"$requirements_stamp")"
fi

if [[ "$created_venv" == true || "$installed_hash" != "$requirements_hash" ]]; then
    if [[ "$created_venv" == true ]]; then
        echo "Installing dependencies..."
        python -m pip install --upgrade pip
    else
        echo "requirements.txt changed; updating dependencies..."
    fi
    python -m pip install -r requirements.txt
    printf '%s\n' "$requirements_hash" > "$requirements_stamp"
    echo "Dependencies are up to date."
fi

# --- Optionally start LM Studio -----------------------------------------
# Only relevant when the config selects it as the backend.
backend="$(python - <<'PY'
from modules import compat
print(compat.load_config()["server"].get("server_ai", "").strip().lower())
PY
)"

if [[ "$backend" == "lm studio" ]]; then
    SERVER_URL="$(python - <<'PY'
from modules._openai_iface import normalise_base_url
from modules import compat
print(normalise_base_url(compat.load_config()["server"].get("base_url", "")))
PY
)"
    if curl -sf "${SERVER_URL}/models" >/dev/null 2>&1; then
        echo "Model server already running."
    elif command -v lms >/dev/null 2>&1; then
        echo "Starting LM Studio server..."
        lms server start >/dev/null 2>&1 || true
        printf 'Waiting for Lilith%s consciousness' "'"
        for _ in $(seq 1 40); do
            if curl -sf "${SERVER_URL}/models" >/dev/null 2>&1; then
                echo " ok"
                break
            fi
            printf '.'
            sleep 1
        done
        echo
    else
        echo "Note: 'lms' not found; start LM Studio's server yourself." >&2
    fi
fi

echo "Lilith is awakening..."
echo
exec python lilith.py "$@"
