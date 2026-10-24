# Commit

A simple CLI tool that writes Git commit messages for you using a local model through Ollama.

It inspects your staged changes, generates a Conventional Commit title, and puts together a short summary with bullet points. Everything runs locally on your machine with no API keys, no subscriptions, and your code never leaves your computer.

```
$ git add .
$ commit

=== STAGED FILES ===
  [-] src/auth.py
  [-] src/routes.py

[/] Generating commit message...

=== COMMIT PREVIEW ===
Title (48 chars):
feat(auth): add session-based authentication

Description:
Replaces basic authentication with token-based sessions across API routes.

- Add session validation middleware for authenticated endpoints.
- Store session tokens in memory with configurable TTL.

--------------------------------------------------
  [Y] Commit
  [P] Commit & Push
  [E] Edit
  [R] Regenerate
  [S] Settings
  [N] Cancel

Choice:
```

---

## Prerequisites

- **Git**
- **Python 3.8+**
- **[Ollama](https://ollama.com/)** installed and running

You will need a model pulled in Ollama. We recommend `qwen2.5-coder:7b`:

```bash
ollama pull qwen2.5-coder:7b
```

*(You can also let the tool download a model for you during first-time setup).*

---

## Installation

Clone the repo anywhere you want to keep it:

```bash
git clone https://github.com/Bookinheaven/Commit.git
cd Commit
```

### Linux & macOS

**Option 1: Symlink (recommended)**
```bash
sudo ln -s "$PWD/commit" /usr/local/bin/commit
```

**Option 2: Add to your PATH**
Add this to your `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="/path/to/Commit:$PATH"
```

Once installed, you can just type `commit` inside any git repo.

### Windows

**Option 1: Add to PATH (recommended)**
1. Press `Win + S` and search for **"Environment Variables"**.
2. Under **User variables**, select `Path` and click **Edit**.
3. Click **New** and paste the folder path where you saved this repo (for example `D:\Tools\Commit`).
4. Open a new terminal and type `commit`.

**Option 2: Run directly**
Double-click or run `commit.bat` from your terminal.

---

## How It Works

1. Stage the files you want to commit (or let `commit` prompt to stage modified files for you):
   ```bash
   git add .
   ```
2. Run `commit`:
   ```bash
   commit
   ```
3. Look over the preview and pick an action:
   - **`Y` (Commit)**: Commits the staged changes with the generated message and logs an entry to history.
   - **`P` (Commit & Push)**: Commits the changes and immediately runs `git push` in one step.
   - **`E` (Edit)**: Opens the message in your editor (Notepad, nano, VS Code, or whatever `$EDITOR` is set to) so you can make manual adjustments before committing.
   - **`R` (Regenerate)**: Re-runs generation. You can optionally give it quick instructions (such as *"make it a fix instead of feat"*, *"mention issue #42"*, or *"keep it to two bullets"*), or press Enter to just try again.
   - **`S` (Settings)**: Opens the settings menu to switch models or tweak memory preferences.
   - **`N` (Cancel)**: Quits without doing anything to git.

---

## CLI Commands

| Command | Description |
|---|---|
| `commit` | Generate commit message for staged changes |
| `commit -l`, `--history` | View the last 10 commits generated across your repositories |
| `commit -s`, `--settings` | Open interactive settings (model selection and memory cache) |
| `commit -h`, `--help` | Show command-line help and options |

---

## Features

- **Single-Pass Speed**: Generates both the title and bullet-point summary in one unified request, cutting wait times in half.
- **Concise Conventional Commits**: Titles stay under 70 characters with clean module scopes (e.g. `feat(auth): ...`), without listing filenames in parentheses.
- **Interactive Review**: Commit immediately (`Y`), commit and push (`P`), edit in your favorite editor (`E`), or regenerate with feedback (`R`).
- **Auto-Staging**: If you forget to run `git add`, `commit` detects modified files and asks if you would like to stage them on the spot.
- **Recent History**: Keep track of commits generated across projects using `commit -l`.
- **Repository Rules**: Drop a `.commitrules` file in any repository to enforce custom commit style or ticket prefixes.
- **Low RAM Friendly**: Choose how long the model stays in memory, including a 0-minute Game Mode that unloads the model immediately after generation.

---

## Commit History

View your recent commit history log from anywhere:

```bash
commit -l
# or
commit --history
```

---

## Custom Repository Rules (.commitrules)

If your project or team has specific commit guidelines, you can create a `.commitrules` file in your repository root. The tool will automatically detect it and enforce your rules:

```text
- Always start the title with a ticket reference if found (e.g. feat(JIRA-101): ...).
- Keep descriptions strictly to 3 bullet points or fewer.
```

---

## Settings

You can open settings anytime from the menu with `S`, or directly from the terminal:

```bash
commit --settings
```

From here you can manage:

### 1. Active Model & One-Click Downloads
Switch between any models you already have installed, or download one directly inside the tool with a progress bar:
- **`qwen2.5-coder:7b`** (Recommended: best accuracy for commit conventions)
- **`qwen2.5-coder:1.5b`** (Lightweight and very fast, great for older laptops)
- **`llama3.2:3b`** (Solid all-round model)
- **`deepseek-coder:6.7b`** (Alternative code model)
- Or enter any model name available on [ollama.com](https://ollama.com).

### 2. Memory & RAM Management
Local models can take 1 to 5 GB of RAM/VRAM while loaded. You can control how long Ollama keeps the model loaded after you commit:
- **Low RAM / Game Mode (`0m`)**: Drops the model from memory immediately after the message is generated. Perfect if you have limited RAM or play games while coding.
- **Standard (`5m`)**: The default Ollama behavior. Keeps the model loaded for 5 minutes of idle time before freeing memory.
- **Balanced (`15m`)**: Keeps the model ready during active work sessions.
- **Always Fast (`30m`)**: Keeps the model warm for 30 minutes so subsequent commits generate instantly with zero reload delay.

All settings are saved to `config.json` next to the script.

---

## Large Diffs & Lockfiles

If you stage a big update or run `npm install`, you do not have to worry about lockfile spam:
- **Noise filtering**: Files like `package-lock.json`, `yarn.lock`, `bun.lockb`, `.min.js`, and `.svg` are automatically trimmed down to their headers. This keeps prompts small and ensures the LLM focuses on your actual code changes.
- **Map-Reduce mode**: If your real code changes are unusually large, the tool breaks them down by file, summarizes each piece, and combines them into one coherent commit message without hitting model context limits.

---

## License

MIT
