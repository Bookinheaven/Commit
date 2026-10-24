import os
import json

CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "config.json")
)

DEFAULT_CONFIG = {
    "model": "qwen2.5-coder:7b",
    "keep_alive": "5m",
    "ollama_url": "http://localhost:11434/api/generate",
    "max_diff_chars": 20000,
}

RECOMMENDED_MODELS = [
    ("qwen2.5-coder:7b", "4.7 GB", "Best quality Conventional Commits (Recommended)"),
    ("qwen2.5-coder:1.5b", "1.0 GB", "Lightweight, ultra-fast, minimal RAM"),
    ("llama3.2:3b", "2.0 GB", "Fast, balanced general model"),
    ("deepseek-coder:6.7b", "3.8 GB", "Strong coding alternative"),
]


def load_config() -> dict:
    """Load configuration from config.json merged with defaults and env overrides."""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception:
            pass

    # Environment variables override file settings if present
    if "COMMIT_MODEL" in os.environ:
        cfg["model"] = os.environ["COMMIT_MODEL"]
    if "COMMIT_KEEP_ALIVE" in os.environ:
        cfg["keep_alive"] = os.environ["COMMIT_KEEP_ALIVE"]
    if "OLLAMA_URL" in os.environ:
        cfg["ollama_url"] = os.environ["OLLAMA_URL"]
    if "COMMIT_MAX_DIFF_CHARS" in os.environ:
        try:
            cfg["max_diff_chars"] = int(os.environ["COMMIT_MAX_DIFF_CHARS"])
        except ValueError:
            pass

    return cfg


def save_config(cfg: dict) -> None:
    """Save dictionary to config.json and refresh module variables."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    reload_globals()


def reload_globals():
    """Reload module-level variables from loaded config."""
    global MODEL, OLLAMA_URL, KEEP_ALIVE, MAX_DIFF_CHARS
    cfg = load_config()
    MODEL = cfg.get("model", DEFAULT_CONFIG["model"])
    OLLAMA_URL = cfg.get("ollama_url", DEFAULT_CONFIG["ollama_url"])
    KEEP_ALIVE = cfg.get("keep_alive", DEFAULT_CONFIG["keep_alive"])
    MAX_DIFF_CHARS = cfg.get("max_diff_chars", DEFAULT_CONFIG["max_diff_chars"])


# Initialize module-level variables on import
reload_globals()
