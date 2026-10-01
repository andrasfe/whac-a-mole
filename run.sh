#!/usr/bin/env bash
# Quick launcher for Whac-A-Mole
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ -f "$VENV_PYTHON" ]; then
    exec "$VENV_PYTHON" -m whacamole "$@"
else
    exec python3 -m whacamole "$@"
fi
