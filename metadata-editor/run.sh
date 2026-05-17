#!/usr/bin/env bash
# Comic Bulk Metadata Editor launcher for macOS / Linux

set -e
PYTHON=""
for cmd in python3 python py; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python not found. Install from https://python.org"
    exit 1
fi

echo "Using Python: $PYTHON ($($PYTHON --version))"
$PYTHON -m pip install -r requirements.txt -q
$PYTHON main.py
