#!/usr/bin/env bash
# ==============================================================================
# Commit (commit-ai) — Self-Contained Installer for Linux and macOS
# ==============================================================================
# Installs Commit into an isolated environment using Python's built-in 'venv'
# and 'ensurepip'. Does NOT require pipx, uv, conda, or poetry.
# ==============================================================================

set -euo pipefail

MIN_PY_MAJOR=3
MIN_PY_MINOR=10
PACKAGE_NAME="commit-ai"
COMMAND_NAME="commit"

# Determine directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

if [[ "$(uname -s)" == "Darwin" ]]; then
    APP_DATA_DIR="$HOME/Library/Application Support/commit-ai"
else
    APP_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/commit-ai"
fi

VENV_DIR="$APP_DATA_DIR/venv"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
LAUNCHER_PATH="$BIN_DIR/$COMMAND_NAME"

# ------------------------------------------------------------------------------
# 1. Action: Uninstall Handler
# ------------------------------------------------------------------------------
do_uninstall() {
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

    # Clean up empty parent app data dir if empty
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
}

# ------------------------------------------------------------------------------
# 2. Argument Parsing
# ------------------------------------------------------------------------------
YES_TO_PATH=0
NO_TO_PATH=0

print_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --uninstall           Uninstall Commit and remove its isolated environment
  --yes-path            Automatically add $BIN_DIR to shell PATH if missing
  --no-path             Do not modify shell PATH configuration
  -h, --help            Show this help message and exit

Description:
  Creates an isolated Python virtual environment in:
    $VENV_DIR
  and creates a user launcher in:
    $LAUNCHER_PATH

  Requires only Python >= $MIN_PY_MAJOR.$MIN_PY_MINOR with built-in 'venv' support.
  Does not require pipx, uv, conda, or system administrator privileges.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall)
            do_uninstall
            ;;
        --yes-path)
            YES_TO_PATH=1
            shift
            ;;
        --no-path)
            NO_TO_PATH=1
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Error: Unknown option '$1'" >&2
            print_usage >&2
            exit 1
            ;;
    esac
done

# ------------------------------------------------------------------------------
# 3. Verify Project Directory
# ------------------------------------------------------------------------------
if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
    echo "Error: pyproject.toml not found in: $PROJECT_DIR" >&2
    echo "Please run install.sh from the root of the Commit repository or extracted source archive." >&2
    exit 1
fi

echo "======================================================="
echo " Commit ($PACKAGE_NAME) Installer"
echo "======================================================="
echo "Source directory: $PROJECT_DIR"
echo "Target venv:     $VENV_DIR"
echo "Target launcher: $LAUNCHER_PATH"
echo ""

# ------------------------------------------------------------------------------
# 4. Detect Compatible Python Interpreter (>= 3.10)
# ------------------------------------------------------------------------------
PYTHON_BIN=""
DETECTED_VER=""

for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        CAND_PATH="$(command -v "$candidate")"
        if "$CAND_PATH" -c "import sys; sys.exit(0 if sys.version_info >= ($MIN_PY_MAJOR, $MIN_PY_MINOR) else 1)" >/dev/null 2>&1; then
            PYTHON_BIN="$CAND_PATH"
            DETECTED_VER="$("$CAND_PATH" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo "")"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "Error: Python >= $MIN_PY_MAJOR.$MIN_PY_MINOR is required to install Commit." >&2
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            V="$("$(command -v "$candidate")" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo "unknown")"
            echo "Found $(command -v "$candidate") with version $V (too old)." >&2
        fi
    done
    echo "" >&2
    echo "Please install Python 3.10 or newer from your system package manager or:" >&2
    echo "  https://www.python.org/downloads/" >&2
    exit 1
fi

echo "Python interpreter: $PYTHON_BIN (version $DETECTED_VER)"

# ------------------------------------------------------------------------------
# 5. Verify Virtual Environment (venv) Support
# ------------------------------------------------------------------------------
if ! "$PYTHON_BIN" -c "import venv" 2>/dev/null; then
    echo "" >&2
    echo "Error: The Python 'venv' module is not installed or incomplete." >&2
    echo "" >&2
    echo "On Debian/Ubuntu and derivative distributions, virtual environment support" >&2
    echo "is provided in a separate package. Please install it with:" >&2
    echo "  sudo apt install python3-venv" >&2
    echo "" >&2
    echo "On Red Hat / Fedora:" >&2
    echo "  sudo dnf install python3" >&2
    echo "" >&2
    echo "After installing python3-venv, re-run this script:" >&2
    echo "  ./install.sh" >&2
    exit 1
fi

# ------------------------------------------------------------------------------
# 6. Create / Update Isolated Virtual Environment
# ------------------------------------------------------------------------------
mkdir -p "$APP_DATA_DIR"

if [[ -d "$VENV_DIR" && -x "$VENV_DIR/bin/python" ]]; then
    echo "==> Existing isolated environment detected at $VENV_DIR"
    echo "==> Updating installation..."
else
    echo "==> Creating isolated virtual environment in $VENV_DIR..."
    rm -rf "$VENV_DIR"

    # Try standard venv creation
    if ! "$PYTHON_BIN" -m venv "$VENV_DIR" 2>/dev/null; then
        # If standard venv failed (e.g. ensurepip missing from base python), try without pip and bootstrap
        echo "==> Standard venv creation failed; attempting with --without-pip..."
        "$PYTHON_BIN" -m venv --without-pip "$VENV_DIR"
        echo "==> Bootstrapping pip using ensurepip..."
        "$VENV_DIR/bin/python" -m ensurepip --upgrade --default-pip
    fi
fi

# Ensure pip is present inside the venv
if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "==> Bootstrapping pip inside isolated environment..."
    "$VENV_DIR/bin/python" -m ensurepip --upgrade --default-pip 2>/dev/null || {
        echo "Error: Could not bootstrap pip in $VENV_DIR." >&2
        echo "Please ensure 'ensurepip' or 'python3-pip' is available." >&2
        exit 1
    }
fi

# ------------------------------------------------------------------------------
# 7. Install Commit into Isolated Environment
# ------------------------------------------------------------------------------
echo "==> Installing Commit dependencies and package..."
"$VENV_DIR/bin/python" -m pip install --upgrade --no-warn-script-location "$PROJECT_DIR"

# ------------------------------------------------------------------------------
# 8. Create Launcher in User Binary Directory
# ------------------------------------------------------------------------------
mkdir -p "$BIN_DIR"

cat << EOF > "$LAUNCHER_PATH"
#!/usr/bin/env bash
# Commit (commit-ai) launcher
exec "$VENV_DIR/bin/$COMMAND_NAME" "\$@"
EOF

chmod +x "$LAUNCHER_PATH"
echo "==> Created launcher: $LAUNCHER_PATH"

# ------------------------------------------------------------------------------
# 9. Verify Installation & Version
# ------------------------------------------------------------------------------
echo ""
echo "-------------------------------------------------------"
echo " Verification"
echo "-------------------------------------------------------"

if [[ ! -x "$LAUNCHER_PATH" ]]; then
    echo "Error: Launcher was created but is not executable: $LAUNCHER_PATH" >&2
    exit 1
fi

VERSION_OUTPUT="$("$LAUNCHER_PATH" --version 2>&1 || true)"
echo "Launcher:   $LAUNCHER_PATH"
echo "Version:    $VERSION_OUTPUT"

# ------------------------------------------------------------------------------
# 10. PATH Verification & Consent-Based Configuration
# ------------------------------------------------------------------------------
ON_PATH=0
if command -v "$COMMAND_NAME" >/dev/null 2>&1; then
    RESOLVED_CMD="$(command -v "$COMMAND_NAME")"
    if [[ "$RESOLVED_CMD" == "$LAUNCHER_PATH" ]] || [[ "$RESOLVED_CMD" -ef "$LAUNCHER_PATH" ]]; then
        ON_PATH=1
    fi
fi

if [[ $ON_PATH -eq 0 ]]; then
    # Also check if directory is directly listed in PATH
    if [[ ":$PATH:" == *":$BIN_DIR:"* ]]; then
        ON_PATH=1
    fi
fi

echo ""
if [[ $ON_PATH -eq 1 ]]; then
    echo "✓ Commit is installed and immediately available in your PATH!"
    echo "  Run 'commit' in any Git repository to get started."
else
    echo "⚠️  Notice: The directory '$BIN_DIR' is not in your current PATH."
    echo ""

    # Determine shell profile file
    SHELL_NAME="$(basename "${SHELL:-bash}")"
    TARGET_RC=""
    case "$SHELL_NAME" in
        zsh)
            TARGET_RC="$HOME/.zshrc"
            ;;
        bash)
            if [[ -f "$HOME/.bashrc" ]]; then
                TARGET_RC="$HOME/.bashrc"
            elif [[ -f "$HOME/.bash_profile" ]]; then
                TARGET_RC="$HOME/.bash_profile"
            else
                TARGET_RC="$HOME/.bashrc"
            fi
            ;;
        *)
            TARGET_RC="$HOME/.profile"
            ;;
    esac

    CONFIGURE_PATH=0

    if [[ $YES_TO_PATH -eq 1 ]]; then
        CONFIGURE_PATH=1
    elif [[ $NO_TO_PATH -eq 1 ]]; then
        CONFIGURE_PATH=0
    elif [[ -t 0 ]]; then
        # Interactive prompt for consent
        echo "Would you like the installer to add '$BIN_DIR' to your PATH in $TARGET_RC?"
        read -r -p "Add to PATH? [y/N]: " USER_CHOICE
        case "$USER_CHOICE" in
            [yY]|[yY][eE][sS])
                CONFIGURE_PATH=1
                ;;
            *)
                CONFIGURE_PATH=0
                ;;
        esac
    fi

    if [[ $CONFIGURE_PATH -eq 1 && -n "$TARGET_RC" ]]; then
        echo "" >> "$TARGET_RC"
        echo "# Added by Commit installer" >> "$TARGET_RC"
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$TARGET_RC"
        echo "✓ Added '$BIN_DIR' to $TARGET_RC."
        echo "  Please restart your terminal or run: source $TARGET_RC"
    else
        echo "To run 'commit' from any terminal, add this line to your shell configuration file ($TARGET_RC):"
        echo "  export PATH=\"$BIN_DIR:\$PATH\""
    fi

    echo ""
    echo "To test Commit in your current terminal session right now without restarting:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    echo "  commit --version"
fi

echo ""
echo "Ollama Reminder:"
echo "  Commit requires Ollama to be running locally (or at a configured endpoint)."
echo "  Verify your Ollama service: curl http://localhost:11434/"
echo "  Recommended model:          ollama pull qwen2.5-coder:7b"
echo "======================================================="
exit 0
