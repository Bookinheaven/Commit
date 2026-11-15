#!/usr/bin/env bash
# ==============================================================================
# Commit (commit-ai) — Uninstaller for Linux and macOS
# ==============================================================================
# Removes Commit's isolated virtual environment and command launcher.
# Does NOT touch unrelated Python environments or user repository data.
# ==============================================================================

set -euo pipefail

PACKAGE_NAME="commit-ai"
COMMAND_NAME="commit"

if [[ "$(uname -s)" == "Darwin" ]]; then
    APP_DATA_DIR="$HOME/Library/Application Support/commit-ai"
else
    APP_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/commit-ai"
fi

VENV_DIR="$APP_DATA_DIR/venv"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
LAUNCHER_PATH="$BIN_DIR/$COMMAND_NAME"

echo "======================================================="
echo " Commit ($PACKAGE_NAME) Uninstaller"
echo "======================================================="

REMOVED_ANY=0

if [[ -f "$LAUNCHER_PATH" ]]; then
    echo "Removing launcher: $LAUNCHER_PATH"
    rm -f "$LAUNCHER_PATH"
    REMOVED_ANY=1
fi

if [[ -d "$VENV_DIR" ]]; then
    echo "Removing isolated environment: $VENV_DIR"
    rm -rf "$VENV_DIR"
    REMOVED_ANY=1
fi

if [[ -d "$APP_DATA_DIR" ]] && [[ -z "$(ls -A "$APP_DATA_DIR" 2>/dev/null)" ]]; then
    rmdir "$APP_DATA_DIR" 2>/dev/null || true
fi

echo ""
if [[ $REMOVED_ANY -eq 1 ]]; then
    echo "✓ Commit ($PACKAGE_NAME) has been successfully uninstalled."
else
    echo "No active Commit installation found in $APP_DATA_DIR or $BIN_DIR."
fi

echo ""
echo "Note: Configuration (~/.config/commit) and history (~/.local/state/commit) were preserved."
echo "To remove configuration and history data as well, run:"
echo "  rm -rf ~/.config/commit ~/.local/state/commit"
echo "======================================================="
exit 0
