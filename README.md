# AI Git Commit Generator

Generate structured, professional [Conventional Commit](https://www.conventionalcommits.org/) messages from your staged changes — powered by a local LLM via [Ollama](https://ollama.com/). No internet required.

## Requirements

- Python 3.8+
- Git
- [Ollama](https://ollama.com/) running locally

Pull the default model before first use:

```bash
ollama pull qwen2.5-coder:7b
```

## Setup

Clone or copy this repo anywhere on your machine. No installation needed — it's just Python.

```
Commit/
├── commit.py           ← main script
├── commit.bat          ← Windows shortcut
├── commit_history.json ← auto-created after first commit
└── core/
    ├── config.py       ← model & settings
    ├── llm.py          ← Ollama calls & prompts
    ├── parser.py       ← diff parsing & cleanup
    ├── git_utils.py    ← git subprocess wrappers
    ├── ui.py           ← terminal output & editor
    └── history.py      ← commit history logger
```

## Usage

### Option 1 — Add to PATH (recommended)

Add the `Commit/` folder to your system `PATH`. Then from any Git repo:

```bash
git add .
commit
```

### Option 2 — Run directly

```bash
git add src/ app/
python C:\path\to\Commit\commit.py
```

### Option 3 — Double-click or call the `.bat`

```bat
commit.bat
```

## What it does on each run

1. **Checks Ollama** is reachable before doing anything
2. **Lists your staged files** so you know exactly what's being analyzed
3. **Generates** a title and description using the LLM (animated spinner while waiting)
4. **Shows a preview** with an interactive menu

## Interactive Menu

| Key | Action |
|-----|--------|
| `Y` | Accept and commit |
| `E` | Open in editor (`$EDITOR`, Notepad, or nano) |
| `R` | Regenerate a new message |
| `N` | Cancel without committing |

## Commit History

Every successful commit is appended to `commit_history.json` in the tool's directory:

```json
[
  {
    "timestamp": "2026-10-16T09:45:00",
    "repo": "D:/GitHub/MyProject",
    "title": "feat(auth): add session-based login",
    "description": "Implements cookie-based sessions...\n\n- Add login/logout endpoints\n- ..."
  }
]
```

## Configuration

Edit [`core/config.py`](core/config.py):

```python
MODEL = "qwen2.5-coder:7b"   # any model available in Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
MAX_DIFF_CHARS = 20000        # diffs larger than this trigger Map-Reduce mode
```

## Large Diffs

For large staged changes the tool automatically switches to **Map-Reduce** mode:

1. **Filter** — drops auto-generated files (`package-lock.json`, lockfiles, `.min.js`, etc.)
2. **Split** — divides the remaining diff into chunks without breaking files apart
3. **Summarise** — asks the model to bullet-point each chunk (with per-chunk spinner)
4. **Synthesise** — combines summaries into one coherent commit message
