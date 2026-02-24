#!/bin/bash
# ── Spear launcher ───────────────────────────────────────────────────────────
# Activates the project venv and runs the app.
# Exit code 100 = update yt-dlp, then restart automatically.
#
# Venv resolution order:
#   1. SPEAR_VENV environment variable (set this on machines with a global venv)
#   2. .venv/ folder in the repo root (standard, works on a fresh clone)

# Change to script directory
cd "$(dirname "$0")" || exit 1

# ── Locate venv ──────────────────────────────────────────────────────────────
if [ -n "$SPEAR_VENV" ]; then
    if [ ! -f "$SPEAR_VENV/bin/activate" ]; then
        echo "ERROR: SPEAR_VENV is set but '$SPEAR_VENV/bin/activate' was not found."
        read -p "Press Enter to exit..." -r
        exit 1
    fi
    source "$SPEAR_VENV/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
else
    echo "No virtual environment found. Creating .venv..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        echo "Make sure Python is installed and on your PATH."
        read -p "Press Enter to exit..." -r
        exit 1
    fi
    source ".venv/bin/activate"
    echo "Installing dependencies..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install dependencies."
        read -p "Press Enter to exit..." -r
        exit 1
    fi
    echo
    echo "Environment ready."
    echo
fi

# ── Run loop ─────────────────────────────────────────────────────────────────
run_script() {
    python main.py
    local EC=$?

    if [ $EC -eq 100 ]; then
        echo
        echo "Updating yt-dlp..."
        pip install -U yt-dlp
        if [ $? -ne 0 ]; then
            echo
            echo "WARNING: yt-dlp update failed. Check your internet connection."
            read -p "Press Enter to exit..." -r
            exit 1
        fi
        echo
        echo "yt-dlp updated. Restarting Spear..."
        echo
        run_script  # Recursive call to restart
    elif [ $EC -ne 0 ]; then
        echo
        echo "Spear exited with error code $EC."
        read -p "Press Enter to exit..." -r
    fi

    exit $EC
}

run_script
