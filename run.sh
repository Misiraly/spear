#!/usr/bin/env bash

# ── Spear launcher ───────────────────────────────────────────────────────────
# Activates the project venv and runs the app.
# Exit code 100 = update yt-dlp, then restart automatically.
#
# Venv resolution order:
#   1. SPEAR_VENV environment variable
#   2. .venv/ folder in the repo root

set -e

# Change to script directory (equivalent to cd /d "%~dp0")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Locate venv ──────────────────────────────────────────────────────────────
activate_venv() {
    # shellcheck disable=SC1090
    source "$1/bin/activate"
}
if [[ -n "$SPEAR_VENV" ]]; then
    if [[ ! -f "$SPEAR_VENV/bin/activate" ]]; then
        echo "ERROR: SPEAR_VENV is set but \"$SPEAR_VENV/bin/activate\" was not found."
        exit 1
    fi
    activate_venv "$SPEAR_VENV"

elif [[ -f ".venv/bin/activate" ]]; then
    activate_venv ".venv"

else
    echo "No virtual environment found. Creating .venv..."
    python3 -m venv .venv || {
        echo "ERROR: Failed to create virtual environment."
        echo "Make sure Python is installed and on your PATH."
        exit 1
    }

    activate_venv ".venv"

    echo "Installing dependencies..."
    pip install -r requirements.txt || {
        echo "ERROR: Failed to install dependencies."
        exit 1
    }

    echo
    echo "Environment ready."
    echo
fi

# ── Run loop ─────────────────────────────────────────────────────────────────
while true; do
    python main.py
    EC=$?

    if [[ $EC -eq 100 ]]; then
        echo
        echo "Updating yt-dlp..."
        pip install -U yt-dlp || {
            echo
            echo "WARNING: yt-dlp update failed. Check your internet connection."
            exit 1
        }
        echo
        echo "yt-dlp updated. Restarting Spear..."
        echo
        continue
    fi

    if [[ $EC -ne 0 ]]; then
        echo
        echo "Spear exited with error code $EC."
    fi

    exit $EC
done
