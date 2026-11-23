#!/usr/bin/env bash
# ==============================================================================
# Commit (commit-ai) — Quick Updater for Linux and macOS
# ==============================================================================
# Pulls latest updates from Git and updates the isolated environment.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================="
echo " Commit Updater"
echo "======================================================="

# If inside a git repository, pull latest changes
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "==> Pulling latest changes from Git repository..."
    if ! git pull --ff-only; then
        echo "Warning: Fast-forward pull failed. Continuing with local source."
    fi
fi

# Run installer script to update isolated virtual environment
./install.sh "$@"
