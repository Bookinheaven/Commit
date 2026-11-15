# Commit (`commit-ai`)

**AI-powered Conventional Commit message generator powered by Ollama models.**

Commit inspects your staged Git changes, understands your project structure and context, and generates high-quality, standardized [Conventional Commits](https://www.conventionalcommits.org/) messages directly on your machine.

---

## Features

- **Strict Conventional Commits**: Automatically detects commit types (`feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `chore`), identifies concise scopes, highlights breaking changes, and structures descriptive subjects and bullet points.
- **Local AI Inference**: Integrates with [Ollama](https://ollama.com/) (e.g., `qwen2.5-coder:7b`, `qwen2.5-coder:3b`, `deepseek-coder:6.7b`) with automatic context length detection and keep-alive optimization.
- **Two Distinct Appearance Modes**:
  - **Minimal (Default)**: Fast, clean, ordinary terminal stream output. Ideal for daily command-line workflows, terminal multiplexers, and scriptable environments.
  - **Rich**: An expressive, optional full-screen terminal interface with animated generation progress, styled metadata panels, and keyboard-driven shortcuts.
- **Flexible Workflow Modes**:
  - **Guided (Default)**: Interactive menu, live generation with elapsed timer, message review, editing, and single-key actions.
  - **Quick (`--quick` / `-q`)**: Streamlined flow that directly generates and prompts for quick confirmation.
- **Interactive Review & Editing**:
  - One-key commit (<kbd>Enter</kbd>), edit (<kbd>e</kbd>), regenerate (<kbd>r</kbd>), or cancel (<kbd>q</kbd> / <kbd>Esc</kbd>).
  - Structured field-by-field editing or external editor launching (`$EDITOR`, `nvim`, `code --wait`, `nano`, `vim`).
- **Git Safety Guarantees**:
  - Computes a SHA-256 snapshot fingerprint of staged changes and HEAD to detect any changes made while reviewing.
  - Analyzes only staged changes (`git diff --cached`).
  - Preserves standard Git hooks (`pre-commit`, `commit-msg`) and GPG/SSH signing.
  - Never stages, pushes, or executes destructive Git commands.
- **Large-Diff Handling**:
  - Smart chunking and token budgeting for repositories with large or multi-file diffs.
- **Pipeline & Non-Interactive Ready**:
  - `--stdout` pipes generated commit messages directly to stdout for shell scripts.
  - `--dry-run` previews messages without writing to Git.
  - `--yes` (`-y`) skips Commit confirmation prompts while preserving Git hooks.

---

## Requirements

- **Git**: 2.25 or later.
- **Python**: 3.10 or later.
- **Ollama**: Installed and running (locally or on an accessible network endpoint).

---

## Privacy & Network Behavior

Commit is designed with clear network boundaries:

- **Local Ollama Inference (Default)**: By default, Commit connects to `http://localhost:11434`. All model inference, prompt data, and staged code diffs remain strictly on your local machine over the loopback interface.
- **Remote Ollama Inference (Optional)**: If you explicitly configure a remote endpoint (e.g., setting `ollama_url = "https://ollama.internal.net:11434"` or `OLLAMA_URL`), staged diffs and prompt data will be transmitted over HTTP/HTTPS to that remote server.
- **Zero Telemetry or Analytics**: Commit contains no analytics, tracking, telemetry, crash reporting, or phone-home update checks. It never contacts external servers on its own.
- **Package Installation**: Installing or upgrading Commit and its dependencies downloads packages from the Python Package Index (PyPI) or your configured package index via standard package managers (`pip`, `pipx`, `uv`).

---

## Ollama Setup

Commit connects to Ollama at `http://localhost:11434` by default.

### 1. Install Ollama

If you do not have Ollama installed, install it for your platform:

- **Linux & macOS**:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```
- **Windows / macOS App**:
  Download installer from [ollama.com/download](https://ollama.com/download).

### 2. Pull a Recommended Model

We recommend `qwen2.5-coder:7b` for balanced speed and Conventional Commit accuracy:

```bash
# Recommended (balanced accuracy and speed)
ollama pull qwen2.5-coder:7b

# Lightweight alternative (low memory footprint)
ollama pull qwen2.5-coder:3b

# DeepSeek Coder alternative
ollama pull deepseek-coder:6.7b
```

### 3. Verify Ollama is Running

```bash
curl http://localhost:11434/
# Should return: "Ollama is running"
```

---

## Installation

Commit features a self-contained installation process using Python's standard library `venv` and `ensurepip`.

**It does NOT require pipx, uv, Conda, Poetry, or global pip.**

Commit is installed into an isolated virtual environment under your user application data directory so it never modifies your system Python or conflicts with other projects.

### Prerequisites

1. **Python 3.10 or newer** with standard `venv` support:
   - On Debian/Ubuntu: ensure `python3-venv` is installed (`sudo apt install python3-venv`).
   - On Windows: ensure Python is installed from [python.org](https://www.python.org/downloads/windows/) with standard library features enabled.
2. **Git 2.25+**.
3. **Internet access** (for pip downloading runtime dependencies into the isolated environment).
4. **[Ollama](https://ollama.com/)** running locally (see [Ollama Setup](#ollama-setup) above). *Note: The installer manages the Commit CLI tool itself; Ollama is an independent runtime prerequisite.*

---

### Windows Installation

1. Download and extract the Commit source archive (or clone via git):
   ```cmd
   git clone https://github.com/Bookinheaven/Commit.git
   cd Commit
   ```
2. Double-click `install.bat` (or run it from Command Prompt / PowerShell):
   ```cmd
   install.bat
   ```
   *(Or in PowerShell: `.\install.ps1`).*
3. If the installer asks for consent to add Commit's launcher directory to your User PATH, enter `Y`.
4. Open a new terminal window.
5. Run:
   ```cmd
   commit
   ```

---

### Linux & macOS Installation

1. Download and extract the Commit source archive (or clone via git):
   ```bash
   git clone https://github.com/Bookinheaven/Commit.git
   cd Commit
   ```
2. Run the installer script:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
3. If prompted to add `~/.local/bin` to your shell configuration (`~/.bashrc` or `~/.zshrc`), enter `y`.
4. Open a new terminal window (or run `source ~/.bashrc` / `source ~/.zshrc`).
5. Run:
   ```bash
   commit
   ```

*(Non-interactive flags: `./install.sh --yes-path` automatically consents to PATH configuration; `./install.sh --no-path` skips PATH modification).*

---

### How It Works

1. **Isolated Environment**: The installer creates a dedicated Python virtual environment:
   - **Linux**: `~/.local/share/commit-ai/venv`
   - **macOS**: `~/Library/Application Support/commit-ai/venv`
   - **Windows**: `%LOCALAPPDATA%\commit-ai\venv`
2. **Standard Pip Bootstrap**: Uses `ensurepip` to bootstrap pip inside the isolated virtual environment if missing, then installs Commit and its dependencies.
3. **User Command Launcher**: Creates a small wrapper script:
   - **Linux & macOS**: `~/.local/bin/commit` (a bash wrapper calling `<venv>/bin/commit`)
   - **Windows**: `%LOCALAPPDATA%\commit-ai\bin\commit.cmd` (calling `<venv>\Scripts\commit.exe`)
4. **Consent-Based PATH**: The installer checks if the launcher directory is on your PATH. It modifies shell configuration files or Windows User PATH **only with your explicit consent**.

---

### Upgrading

To update Commit to a new version, pull or extract the updated source and re-run the installer:

- **Linux & macOS**: `./install.sh`
- **Windows**: `install.bat`

The installer detects your existing isolated environment and upgrades Commit and its dependencies in place.

---

### Uninstallation

To remove Commit:

- **Linux & macOS**:
  ```bash
  ./uninstall.sh
  # or: ./install.sh --uninstall
  ```
- **Windows**:
  ```cmd
  uninstall.bat
  :: or in PowerShell: .\install.ps1 -Uninstall
  ```

This removes **only** Commit's isolated virtual environment and launcher. It does not touch your system Python, other packages, or user repository data.

*(Optional: To also delete saved settings and commit history, remove `~/.config/commit` and `~/.local/state/commit` on Linux/macOS, or `%APPDATA%\commit` and `%LOCALAPPDATA%\commit` on Windows).*

---

### Troubleshooting PATH Issues

If running `commit` gives a `command not found` or `'commit' is not recognized` error:

- **Linux / macOS**:
  - The launcher is located in `~/.local/bin/commit`.
  - Add `export PATH="$HOME/.local/bin:$PATH"` to your `~/.bashrc` or `~/.zshrc`, then restart your terminal.
- **Windows**:
  - The launcher is located in `%LOCALAPPDATA%\commit-ai\bin\commit.cmd`.
  - Add `%LOCALAPPDATA%\commit-ai\bin` to your User Environment Variables under `Path`, then restart Command Prompt or PowerShell.

---

### Verifying Installation

Verify that Commit is installed and accessible:

```bash
commit --version
commit doctor
```

---

## Quick Start

1. **Stage your changes in Git**:
   ```bash
   git add src/
   ```

2. **Run `commit`**:
   ```bash
   commit
   ```

3. **In Minimal mode (default)**:
   ```text
   ✔ Generated commit message in 00:04

   PROPOSED COMMIT MESSAGE

   Title: feat(auth): add session-based token authentication
   Description: Implement bearer token validation for incoming API requests.
   Tokens expire after 1 hour and are verified against Redis.

   - Add TokenAuthenticator middleware
   - Store session state in cache

   ? What would you like to do? (Enter: commit, e: edit, r: regenerate, q: quit)
    ❯  Commit with this message
       Edit message
       Regenerate
       Cancel
   ```

4. Press <kbd>Enter</kbd> to accept and commit, <kbd>e</kbd> to edit, <kbd>r</kbd> to regenerate, or <kbd>q</kbd> to cancel.

---

## Appearance Modes

Commit supports exactly two appearance modes:

### 1. Minimal (`minimal`) — Default
- Fast, clean, ordinary terminal stream.
- Zero screen clearing; leaves existing terminal scrollback intact.
- Suitable for standard terminal workflows, tmux/screen, and CI/scripts.
- Automatically respects `NO_COLOR` and dark/light backgrounds.

### 2. Rich (`rich`) — Optional Full-Screen UI
- Expressive, full-screen terminal interface powered by Prompt Toolkit.
- Live progress feedback with animated indicators, styled metadata panels, and split layout.
- Launch with the `-a rich` flag:
  ```bash
  commit -a rich
  ```
- Or set it as your persistent default:
  ```bash
  commit config set ui.appearance rich
  ```

*(Note: Standard mode has been completely removed in Commit 0.1.0 in favor of the fast Minimal default and immersive Rich mode).*

---

## Workflow Modes

| Workflow | Flag | Description |
|---|---|---|
| **Guided** | Default (`-g`) | Displays staged summary, main menu, live generation, review screen, and editing options. |
| **Quick** | `-q` / `--quick` | Bypasses the main menu, immediately generates the message, and prompts for quick confirmation. |
| **Stdout** | `--stdout` | Prints the generated commit message text to standard output without committing or interactive prompts. |
| **Dry Run** | `--dry-run` | Runs the full generation and preview workflow without writing anything to Git. |

---

## Configuration

Commit stores configuration in a standard TOML file:

- **Linux / macOS**: `~/.config/commit/config.toml`
- **Windows**: `%APPDATA%\commit\config.toml`

### CLI Configuration Commands

```bash
# View active configuration and source paths
commit config show

# Interactively edit settings via menu
commit config

# Set specific configuration keys
commit config set model qwen2.5-coder:7b
commit config set ui.appearance rich
commit config set ui.mode quick
commit config set ollama_url http://localhost:11434

# Get a configuration value
commit config get model

# Unset a configuration key (resets to default)
commit config unset model
```

### Supported Settings

| Configuration Key | Environment Variable | Default | Description |
|---|---|---|---|
| `model` | `COMMIT_MODEL` | `qwen2.5-coder:7b` | Generation model tag in Ollama |
| `provider` | `COMMIT_PROVIDER` | `ollama` | Provider backend (`ollama`) |
| `ollama_url` | `OLLAMA_URL` | `http://localhost:11434` | Ollama service API endpoint URL |
| `ui.mode` | `COMMIT_UI_MODE` | `guided` | Workflow mode: `guided` or `quick` |
| `ui.appearance` | `COMMIT_UI_APPEARANCE` | `minimal` | Appearance mode: `minimal` or `rich` |
| `editor.command` | `COMMIT_EDITOR_COMMAND` | `None` (uses `$EDITOR`) | External editor command (`nvim`, `code --wait`, `nano`) |
| `keep_alive` | `COMMIT_KEEP_ALIVE` | `5m` | Ollama model memory residency duration |
| `timeout` | `COMMIT_TIMEOUT` | `120.0` | Overall generation deadline in seconds |
| `connect_timeout` | `COMMIT_CONNECT_TIMEOUT` | `5.0` | HTTP connect timeout in seconds |
| `read_timeout` | `COMMIT_READ_TIMEOUT` | `60.0` | HTTP read inactivity timeout in seconds |

---

## CLI Reference

```text
Usage: commit [OPTIONS] COMMAND [ARGS]...

Options:
  -v, --version           Show version and exit.
  -q, --quick             Run quick commit workflow.
  -g, --guided            Run guided commit workflow.
  -a, --appearance <str>  Override appearance preset (minimal, rich).
  -m, --model <str>       Override generation model.
  --stdout                Output generated commit message to stdout without committing.
  --dry-run               Generate and display commit message without committing.
  -y, --yes               Skip confirmation prompts (Git hooks and GPG remain active).
  --debug-generation      Expose detailed generation diagnostics and context metrics.
  --help                  Show help message and exit.

Commands:
  doctor                  Run environment, Git, and configuration diagnostics.
  config                  Inspect and modify Commit configuration settings.
```

---

## Git Safety Guarantees

Commit is engineered to preserve the integrity of your Git repository:

1. **Only Staged Changes Are Analyzed**:
   Commit inspects only files currently staged in the index (`git diff --cached`). Working tree modifications that have not been staged and untracked files are never inspected or committed.
2. **Staged Snapshot Change Detection**:
   Commit does *not* lock the Git index (Git provides no exclusive index lock for user interactions). Instead, Commit computes a cryptographic SHA-256 fingerprint of the staged files and current `HEAD` commit before generating a message. Right before executing `git commit`, Commit re-checks this fingerprint. If any file was staged, unstaged, or altered in the index during review, Commit halts, displays an error, and prevents committing stale state.
3. **Explicit Authorization**:
   Commit never runs `git commit` without your explicit authorization (pressing <kbd>Enter</kbd> on the review screen or passing `--yes`).
4. **Git Hooks and Signing Preserved**:
   Commit commits through standard Git mechanisms (`git commit -m ...`). Your repository's `pre-commit`, `commit-msg`, and `prepare-commit-msg` hooks, as well as GPG/SSH commit signatures, run exactly as they would with a manual `git commit`.
5. **No Automatic Staging or Pushing**:
   Commit never runs `git add` to stage unstaged changes, and never runs `git push`. You maintain exclusive control over your staging area and remote repository.
6. **Zero Destructive Commands**:
   Commit never invokes destructive Git commands (`git reset`, `git checkout`, `git restore`, `git clean`).

---

## Diagnostics (`commit doctor`)

If you encounter any issues with Git, Python, or Ollama connectivity, run:

```bash
commit doctor
```

`doctor` inspects:
- Python version and interpreter executable path.
- Git installation, version, and repository root.
- Staged changes, unstaged changes, and untracked files count.
- Configuration and history file paths.
- Active model, provider, appearance, and Ollama endpoint connectivity.

---

## Manual Verification Checklist

Developers and contributors can use this manual checklist to verify Commit 0.1.0:

```bash
# 1. Fresh Installation Verification
./install.sh --no-path  # On Windows: install.bat
commit --version        # Should output: commit-ai version 0.1.0
commit --help           # Should list --appearance (minimal, rich)
commit doctor           # Should report environment, git, and config health

# 2. Appearance Preset Checks
commit config show                    # Verify UI Appearance defaults to 'Minimal'
commit --appearance standard          # Must be rejected: Error: Invalid appearance preset 'standard'
commit --appearance rich --dry-run    # Verify full-screen Rich interface initializes
commit --appearance minimal --dry-run # Verify in-place stream Minimal interface initializes

# 3. Local Ollama Connectivity & Generation
ollama list                           # Verify model is available (e.g. qwen2.5-coder:7b)
git add <file>
commit --dry-run                      # Verify message generates and renders preview

# 4. Stdout Pipeline Check
commit --stdout                       # Should output ONLY the generated commit message text

# 5. Interactive Review: Edit, Regenerate, Cancel
commit
# In review menu:
# - Press 'e': Verify structured or external editor opens and updates the message.
# - Press 'r': Verify prompt accepts optional feedback and regenerates a new message.
# - Press 'q' or Esc: Verify application exits cleanly without committing.

# 6. Successful Commit Verification
commit
# Press Enter to commit. Run 'git log -1' to verify commit was made with hooks/signing.

# 7. Stale Staged Snapshot Handling
commit
# While review prompt is open, in another terminal stage an additional change:
# git add <other-file>
# Return to Commit and press Enter:
# Verify Commit detects the index mismatch, aborts, and offers to refresh/regenerate.

# 8. Uninstallation Check
./uninstall.sh          # On Windows: uninstall.bat
which commit            # Should report not found (or removed launcher)
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
