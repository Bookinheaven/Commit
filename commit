#!/usr/bin/env bash
# AI Git Commit Generator - Linux / macOS Launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check python3 availability
if ! command -v python3 &>/dev/null; then
    echo "[!] Error: python3 is not installed or not in PATH."
    exit 1
fi

exec python3 "$SCRIPT_DIR/commit.py" "$@"
