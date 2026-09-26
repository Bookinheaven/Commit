# AI Git Commit Generator

A powerful, intelligent, and zero-dependency Git commit generator powered by local LLMs (via [Ollama](https://ollama.com/)). It analyzes your staged files and generates highly structured, professional Conventional Commit messages.

## Features

- **Local & Private**: Runs entirely locally using Ollama. No data is sent to external APIs.
- **Map-Reduce Architecture**: Intelligently handles massive diffs (up to hundreds of thousands of characters) by splitting them by file, filtering out noise (`package-lock.json`, minified assets), summarizing chunks, and synthesizing a final cohesive commit.
- **Semantic Grouping**: It doesn't just list what files changed. It analyzes the technical context, groups related components, APIs, and database changes together, and outputs a semantic summary of the feature.
- **Conventional Commits**: Automatically detects the correct type (`feat`, `fix`, `refactor`, `chore`, etc.) and determines the correct scope.
- **Beautiful Terminal UI**: Features a clean, colorful ANSI terminal interface for previewing, regenerating, or manually editing your commit messages.
- **Zero Dependencies**: Built entirely with Python standard libraries. Just install Python and run it!

## Prerequisites

1. **Python 3.8+**
2. **Git**
3. **Ollama**: You must have Ollama installed and running on your local machine.

The script defaults to using the `qwen2.5-coder:7b` model. Make sure you have pulled it:
```bash
ollama run qwen2.5-coder:7b
```

## Usage

1. Stage the files you want to commit using standard Git commands:
   ```bash
   git add src/ app/
   ```

2. Run the commit generator:
   ```bash
   python /path/to/Commit/commit.py
   ```

3. The script will analyze your staged changes and present a preview:
   - **[Y] Commit**: Accept the generated message and commit immediately.
   - **[E] Edit**: Opens the generated message in your default text editor (`$EDITOR` or Notepad/Nano) so you can make manual adjustments.
   - **[R] Regenerate**: Ask the AI to write a completely new title and description.
   - **[N] Cancel**: Abort the commit.

## Configuration

You can easily change the model or tweak the diff size limits by modifying `core/config.py`:

```python
MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"
MAX_DIFF_CHARS = 20000
```

## How It Works (Large Diffs)

When you stage a massive change (e.g., thousands of lines), the generator automatically switches into **Map-Reduce** mode:
1. **Noise Filtering**: Automatically drops the content of auto-generated files (lockfiles, maps, minified scripts) so they don't pollute the AI's context.
2. **Chunking**: Splits the remaining diff into optimal chunks without breaking files in half.
3. **Mapping**: Asks the LLM to write 1-3 bullet points summarizing each chunk.
4. **Reducing**: Combines the summaries and asks the LLM to synthetically group them into a maximum of 5 high-level logical features.
