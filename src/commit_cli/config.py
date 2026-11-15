"""Configuration management and history logging for commit-cli."""

import copy
import json
import os
import sys
import tempfile
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from platformdirs import user_config_dir, user_state_dir

from commit_cli.exceptions import InvalidConfigurationError
from commit_cli.models import CLIOverrides, CommitConfig

APP_NAME = "commit"
APP_AUTHOR = "commit"

VALID_UI_MODES = {"guided", "quick"}
VALID_UI_APPEARANCES = {"minimal", "rich"}

SUPPORTED_CONFIG_KEYS = {
    "ui.mode": "Interaction workflow mode ('guided' or 'quick')",
    "ui.appearance": "Visual rendering appearance ('minimal', 'rich')",
    "editor.command": "External editor launch command (empty string to clear)",
    "model": "Generation model identifier",
    "provider": "LLM provider name ('ollama')",
    "ollama_url": "Ollama service endpoint URL",
    "keep_alive": "Ollama memory keep-alive duration",
    "timeout": "Overall generation deadline in seconds",
    "connect_timeout": "HTTP connection timeout in seconds",
    "read_timeout": "HTTP read inactivity timeout in seconds",
}

ENV_VAR_MAP = {
    "model": "COMMIT_MODEL",
    "provider": "COMMIT_PROVIDER",
    "ollama_url": "OLLAMA_URL",
    "keep_alive": "COMMIT_KEEP_ALIVE",
    "timeout": "COMMIT_TIMEOUT",
    "connect_timeout": "COMMIT_CONNECT_TIMEOUT",
    "read_timeout": "COMMIT_READ_TIMEOUT",
    "ui.mode": "COMMIT_UI_MODE",
    "ui.appearance": "COMMIT_UI_APPEARANCE",
    "editor.command": "COMMIT_EDITOR_COMMAND",
}


def get_config_dir() -> Path:
    """Return the platform-specific user configuration directory."""
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def get_config_file_path() -> Path:
    """Return the absolute path to config.toml."""
    return get_config_dir() / "config.toml"


def get_state_dir() -> Path:
    """Return the platform-specific user state directory (history, cache)."""
    return Path(user_state_dir(APP_NAME, APP_AUTHOR))


def get_history_file_path() -> Path:
    """Return the absolute path to history.jsonl."""
    return get_state_dir() / "history.jsonl"


def _validate_config_dict(data: dict[str, Any]) -> None:
    """Validate raw configuration values."""
    for float_key in ("timeout", "connect_timeout", "read_timeout"):
        if float_key in data:
            val = data[float_key]
            if not isinstance(val, (int, float)) or val <= 0:
                raise InvalidConfigurationError(
                    f"'{float_key}' must be a positive number, got: {val!r}"
                )

    for str_key in ("model", "provider", "ollama_url", "keep_alive"):
        if str_key in data:
            val = data[str_key]
            if not isinstance(val, str) or not val.strip():
                raise InvalidConfigurationError(
                    f"'{str_key}' must be a non-empty string, got: {val!r}"
                )

    # Validate UI section or dotted keys
    if "ui" in data:
        ui_val = data["ui"]
        if not isinstance(ui_val, dict):
            raise InvalidConfigurationError(
                f"'ui' must be a configuration section/table, got: {type(ui_val).__name__}"
            )
        for ui_key, ui_item in ui_val.items():
            if ui_key == "mode":
                if not isinstance(ui_item, str) or ui_item not in VALID_UI_MODES:
                    raise InvalidConfigurationError(
                        f"'ui.mode' must be one of: {sorted(VALID_UI_MODES)}, got: {ui_item!r}"
                    )
            elif ui_key == "appearance":
                if not isinstance(ui_item, str) or ui_item not in VALID_UI_APPEARANCES:
                    raise InvalidConfigurationError(
                        f"'ui.appearance' must be one of: {sorted(VALID_UI_APPEARANCES)}, got: {ui_item!r}"
                    )
            else:
                raise InvalidConfigurationError(
                    f"Unknown configuration key in [ui] section: 'ui.{ui_key}'"
                )

    if "ui.mode" in data:
        val = data["ui.mode"]
        if not isinstance(val, str) or val not in VALID_UI_MODES:
            raise InvalidConfigurationError(
                f"'ui.mode' must be one of: {sorted(VALID_UI_MODES)}, got: {val!r}"
            )

    if "ui.appearance" in data:
        val = data["ui.appearance"]
        if not isinstance(val, str) or val not in VALID_UI_APPEARANCES:
            raise InvalidConfigurationError(
                f"'ui.appearance' must be one of: {sorted(VALID_UI_APPEARANCES)}, got: {val!r}"
            )

    # Validate Editor section or dotted keys
    if "editor" in data:
        ed_val = data["editor"]
        if not isinstance(ed_val, dict):
            raise InvalidConfigurationError(
                f"'editor' must be a configuration section/table, got: {type(ed_val).__name__}"
            )
        for ed_key, ed_item in ed_val.items():
            if ed_key == "command":
                if ed_item is not None and not isinstance(ed_item, str):
                    raise InvalidConfigurationError(
                        f"'editor.command' must be a string or omitted, got: {type(ed_item).__name__}"
                    )
            else:
                raise InvalidConfigurationError(
                    f"Unknown configuration key in [editor] section: 'editor.{ed_key}'"
                )

    if "editor.command" in data:
        val = data["editor.command"]
        if val is not None and not isinstance(val, str):
            raise InvalidConfigurationError(
                f"'editor.command' must be a string or omitted, got: {type(val).__name__}"
            )


def _serialize_toml_value(value: Any) -> str:
    """Serialize a primitive Python value into TOML format."""
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return str(value)
    elif isinstance(value, str):
        # Escape backslashes and double quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(value, list):
        items = ", ".join(_serialize_toml_value(item) for item in value)
        return f"[{items}]"
    else:
        raise TypeError(f"Unsupported TOML value type: {type(value)}")


def _dump_toml(data: dict[str, Any]) -> str:
    """Format a dictionary into valid TOML string with tables/sections."""
    lines = ["# commit-cli configuration", ""]
    top_level = {k: v for k, v in data.items() if not isinstance(v, dict)}
    sections = {k: v for k, v in data.items() if isinstance(v, dict)}

    for key, value in sorted(top_level.items()):
        if value is not None:
            val_str = _serialize_toml_value(value)
            lines.append(f"{key} = {val_str}")

    for sec_name, sec_dict in sorted(sections.items()):
        valid_items = {k: v for k, v in sec_dict.items() if v is not None}
        if valid_items:
            lines.append("")
            lines.append(f"[{sec_name}]")
            for key, value in sorted(valid_items.items()):
                val_str = _serialize_toml_value(value)
                lines.append(f"{key} = {val_str}")

    lines.append("")
    return "\n".join(lines)


def load_config(
    config_path: Path | None = None,
    include_env: bool = True,
) -> CommitConfig:
    """Load configuration from config.toml, merge with env variables and defaults.

    Raises InvalidConfigurationError if the TOML file exists but is malformed.
    """
    path = config_path or get_config_file_path()
    raw_data: dict[str, Any] = {}

    if path.is_file():
        try:
            with open(path, "rb") as f:
                raw_data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise InvalidConfigurationError(
                f"Malformed TOML syntax in configuration file '{path}': {e}"
            ) from e
        except OSError as e:
            raise InvalidConfigurationError(
                f"Could not read configuration file '{path}': {e}"
            ) from e

    _validate_config_dict(raw_data)

    # Initialize with dataclass defaults (Guided, Minimal, editor unset)
    cfg = CommitConfig()

    # Overlay file settings
    for key in (
        "model",
        "provider",
        "ollama_url",
        "keep_alive",
        "timeout",
        "connect_timeout",
        "read_timeout",
    ):
        if key in raw_data:
            setattr(cfg, key, raw_data[key])

    # Overlay UI settings
    if "ui" in raw_data and isinstance(raw_data["ui"], dict):
        if "mode" in raw_data["ui"]:
            cfg.ui.mode = raw_data["ui"]["mode"]
        if "appearance" in raw_data["ui"]:
            cfg.ui.appearance = raw_data["ui"]["appearance"]
    if "ui.mode" in raw_data:
        cfg.ui.mode = raw_data["ui.mode"]
    if "ui.appearance" in raw_data:
        cfg.ui.appearance = raw_data["ui.appearance"]

    # Overlay Editor settings
    if "editor" in raw_data and isinstance(raw_data["editor"], dict):
        if "command" in raw_data["editor"]:
            cfg.editor.command = raw_data["editor"]["command"]
    if "editor.command" in raw_data:
        cfg.editor.command = raw_data["editor.command"]

    if include_env:
        # Overlay environment variables
        if "COMMIT_MODEL" in os.environ and os.environ["COMMIT_MODEL"].strip():
            cfg.model = os.environ["COMMIT_MODEL"].strip()
        if "COMMIT_PROVIDER" in os.environ and os.environ["COMMIT_PROVIDER"].strip():
            cfg.provider = os.environ["COMMIT_PROVIDER"].strip()
        if "OLLAMA_URL" in os.environ and os.environ["OLLAMA_URL"].strip():
            cfg.ollama_url = os.environ["OLLAMA_URL"].strip()
        if "COMMIT_KEEP_ALIVE" in os.environ and os.environ["COMMIT_KEEP_ALIVE"].strip():
            cfg.keep_alive = os.environ["COMMIT_KEEP_ALIVE"].strip()
        if "COMMIT_TIMEOUT" in os.environ:
            try:
                val = float(os.environ["COMMIT_TIMEOUT"])
                if val > 0:
                    cfg.timeout = val
            except ValueError:
                pass
        if "COMMIT_CONNECT_TIMEOUT" in os.environ:
            try:
                val = float(os.environ["COMMIT_CONNECT_TIMEOUT"])
                if val > 0:
                    cfg.connect_timeout = val
            except ValueError:
                pass
        if "COMMIT_READ_TIMEOUT" in os.environ:
            try:
                val = float(os.environ["COMMIT_READ_TIMEOUT"])
                if val > 0:
                    cfg.read_timeout = val
            except ValueError:
                pass
        if "COMMIT_UI_MODE" in os.environ:
            val = os.environ["COMMIT_UI_MODE"].strip()
            if val in VALID_UI_MODES:
                cfg.ui.mode = val
        if "COMMIT_UI_APPEARANCE" in os.environ:
            val = os.environ["COMMIT_UI_APPEARANCE"].strip()
            if val in VALID_UI_APPEARANCES:
                cfg.ui.appearance = val
        if "COMMIT_EDITOR_COMMAND" in os.environ:
            val = os.environ["COMMIT_EDITOR_COMMAND"].strip()
            cfg.editor.command = val if val else None

    return cfg


def save_config(cfg: CommitConfig, config_path: Path | None = None) -> None:
    """Save configuration atomically to disk, preserving existing extra keys.

    Raises InvalidConfigurationError if an existing configuration file is malformed,
    leaving the original file completely untouched.
    """
    path = config_path or get_config_file_path()
    target_dir = path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    existing_data: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "rb") as f:
                existing_data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise InvalidConfigurationError(
                f"Cannot save configuration: existing file '{path}' contains malformed TOML syntax: {e}"
            ) from e
        except OSError as e:
            raise InvalidConfigurationError(
                f"Cannot save configuration: could not read existing file '{path}': {e}"
            ) from e

    # Update with new values, updating subsections
    cfg_data = asdict(cfg)
    existing_data.pop("max_diff_chars", None)
    for k, v in cfg_data.items():
        if isinstance(v, dict):
            if k not in existing_data or not isinstance(existing_data[k], dict):
                existing_data[k] = {}
            existing_data[k].update(v)
        else:
            existing_data[k] = v

    _validate_config_dict(existing_data)

    toml_content = _dump_toml(existing_data)

    # Atomic write via temporary file in the same directory
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=target_dir,
        prefix="config_",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(toml_content)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def get_config_value(cfg: CommitConfig, key: str) -> Any:
    """Retrieve a supported configuration setting value by key."""
    if key == "max_diff_chars":
        raise InvalidConfigurationError(
            "Configuration key 'max_diff_chars' is no longer supported. Commit now handles large diffs automatically."
        )
    if key not in SUPPORTED_CONFIG_KEYS:
        raise InvalidConfigurationError(
            f"Unknown configuration key: '{key}'. Supported keys: {', '.join(sorted(SUPPORTED_CONFIG_KEYS))}"
        )
    if key == "ui.mode":
        return cfg.ui.mode
    elif key == "ui.appearance":
        return cfg.ui.appearance
    elif key == "editor.command":
        return cfg.editor.command
    return getattr(cfg, key)


def set_config_value(cfg: CommitConfig, key: str, value_str: str) -> Any:
    """Validate and update a single configuration setting on a CommitConfig object.

    Returns the parsed/cleaned value.
    """
    if key == "max_diff_chars":
        raise InvalidConfigurationError(
            "Configuration key 'max_diff_chars' is no longer supported. Commit now handles large diffs automatically."
        )
    if key not in SUPPORTED_CONFIG_KEYS:
        raise InvalidConfigurationError(
            f"Unknown configuration key: '{key}'. Supported keys: {', '.join(sorted(SUPPORTED_CONFIG_KEYS))}"
        )

    clean_str = value_str.strip()

    if key == "ui.mode":
        if clean_str not in VALID_UI_MODES:
            raise InvalidConfigurationError(
                f"Invalid value for 'ui.mode': {clean_str!r}. Must be one of: {sorted(VALID_UI_MODES)}"
            )
        cfg.ui.mode = clean_str
        return clean_str

    elif key == "ui.appearance":
        if clean_str not in VALID_UI_APPEARANCES:
            raise InvalidConfigurationError(
                f"Invalid value for 'ui.appearance': {clean_str!r}. Must be one of: {sorted(VALID_UI_APPEARANCES)}"
            )
        cfg.ui.appearance = clean_str
        return clean_str

    elif key == "editor.command":
        if clean_str == "":
            cfg.editor.command = None
            return None
        cfg.editor.command = clean_str
        return clean_str

    elif key in ("timeout", "connect_timeout", "read_timeout"):
        try:
            float_val = float(clean_str)
        except ValueError:
            raise InvalidConfigurationError(
                f"'{key}' must be a positive number, got: {value_str!r}"
            )
        if float_val <= 0:
            raise InvalidConfigurationError(
                f"'{key}' must be a positive number, got: {float_val}"
            )
        setattr(cfg, key, float_val)
        return float_val

    elif key in ("model", "provider", "ollama_url", "keep_alive"):
        if not clean_str:
            raise InvalidConfigurationError(f"'{key}' must be a non-empty string, got: {value_str!r}")
        setattr(cfg, key, clean_str)
        return clean_str

    raise InvalidConfigurationError(f"Unhandled configuration key: '{key}'")


def set_persisted_config_value(
    key: str,
    value_str: str,
    config_path: Path | None = None,
) -> Any:
    """Validate and atomically persist a single configuration setting without affecting other settings or environment overrides.

    Returns the parsed/cleaned value.
    """
    path = config_path or get_config_file_path()
    target_dir = path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read existing raw TOML data from disk
    existing_data: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "rb") as f:
                existing_data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise InvalidConfigurationError(
                f"Cannot save configuration: existing file '{path}' contains malformed TOML syntax: {e}"
            ) from e
        except OSError as e:
            raise InvalidConfigurationError(
                f"Cannot save configuration: could not read existing file '{path}': {e}"
            ) from e

    # 2. Validate and parse the key and value using a scratch CommitConfig
    scratch_cfg = CommitConfig()
    parsed_val = set_config_value(scratch_cfg, key, value_str)

    # 3. Update ONLY the target setting in existing_data, removing obsolete keys
    existing_data.pop("max_diff_chars", None)
    if key.startswith("ui."):
        sub_key = key.split(".", 1)[1]
        ui_sec = existing_data.setdefault("ui", {})
        if not isinstance(ui_sec, dict):
            existing_data["ui"] = {}
            ui_sec = existing_data["ui"]
        ui_sec[sub_key] = parsed_val
    elif key.startswith("editor."):
        sub_key = key.split(".", 1)[1]
        if parsed_val is None:
            # Clear editor override
            if "editor" in existing_data and isinstance(existing_data["editor"], dict):
                existing_data["editor"].pop(sub_key, None)
                if not existing_data["editor"]:
                    existing_data.pop("editor", None)
            existing_data.pop("editor.command", None)
        else:
            ed_sec = existing_data.setdefault("editor", {})
            if not isinstance(ed_sec, dict):
                existing_data["editor"] = {}
                ed_sec = existing_data["editor"]
            ed_sec[sub_key] = parsed_val
    else:
        existing_data[key] = parsed_val

    # 4. Validate the resulting configuration dictionary
    _validate_config_dict(existing_data)

    # 5. Format and write atomically to disk
    toml_content = _dump_toml(existing_data)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=target_dir,
        prefix="config_",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(toml_content)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return parsed_val


def redact_sensitive_url(url: str) -> str:
    """Redact username, password, and query parameters from a URL for safe display.

    Preserves scheme, host, port, and path while masking sensitive credentials.
    """
    try:
        parts = urlsplit(url)
        if not parts.scheme and not parts.netloc:
            return url

        netloc = parts.netloc
        if "@" in netloc:
            _, host_port = netloc.rsplit("@", 1)
            redacted_netloc = f"***:***@{host_port}"
        else:
            redacted_netloc = netloc

        redacted_query = "***" if parts.query else ""

        return urlunsplit((
            parts.scheme,
            redacted_netloc,
            parts.path,
            redacted_query,
            parts.fragment,
        ))
    except Exception:
        return "[REDACTED_URL]"


def get_config_origins(config_path: Path | None = None) -> dict[str, str]:
    """Map each supported configuration key to its source: 'persisted', 'environment', or 'default'."""
    path = config_path or get_config_file_path()
    raw_data: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, "rb") as f:
                raw_data = tomllib.load(f)
        except Exception:
            pass

    origins: dict[str, str] = {}
    for key in SUPPORTED_CONFIG_KEYS:
        env_var = ENV_VAR_MAP.get(key)
        if env_var and env_var in os.environ and os.environ[env_var].strip():
            origins[key] = "environment"
            continue

        if key.startswith("ui."):
            sub = key.split(".", 1)[1]
            if isinstance(raw_data.get("ui"), dict) and sub in raw_data["ui"]:
                origins[key] = "persisted"
            elif key in raw_data:
                origins[key] = "persisted"
            else:
                origins[key] = "default"
        elif key.startswith("editor."):
            sub = key.split(".", 1)[1]
            if (
                isinstance(raw_data.get("editor"), dict)
                and sub in raw_data["editor"]
                and raw_data["editor"][sub] is not None
            ):
                origins[key] = "persisted"
            elif key in raw_data and raw_data[key] is not None:
                origins[key] = "persisted"
            else:
                origins[key] = "default"
        else:
            if key in raw_data:
                origins[key] = "persisted"
            else:
                origins[key] = "default"

    return origins


def reset_persisted_config(
    key: str | None = None,
    config_path: Path | None = None,
) -> None:
    """Reset persisted configuration settings to built-in defaults.

    If key is None, restores all settings to built-in defaults by resetting config.toml.
    If key is provided, removes only that setting from the configuration file,
    preserving unrelated settings and cleaning up empty sections.
    """
    path = config_path or get_config_file_path()
    target_dir = path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    if key is None:
        # Full reset: write empty configuration file atomically
        toml_content = "# commit-cli configuration\n"
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=target_dir,
            prefix="config_",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(toml_content)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        return

    # Individual reset
    if key == "max_diff_chars":
        raise InvalidConfigurationError(
            "Configuration key 'max_diff_chars' is no longer supported. Commit now handles large diffs automatically."
        )
    if key not in SUPPORTED_CONFIG_KEYS:
        raise InvalidConfigurationError(
            f"Unknown configuration key: '{key}'. Supported keys: {', '.join(sorted(SUPPORTED_CONFIG_KEYS))}"
        )

    if not path.is_file():
        # No configuration file on disk, already default
        return

    existing_data: dict[str, Any] = {}
    try:
        with open(path, "rb") as f:
            existing_data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise InvalidConfigurationError(
            f"Cannot reset configuration: existing file '{path}' contains malformed TOML syntax: {e}"
        ) from e
    except OSError as e:
        raise InvalidConfigurationError(
            f"Cannot reset configuration: could not read existing file '{path}': {e}"
        ) from e

    if key.startswith("ui."):
        sub_key = key.split(".", 1)[1]
        if "ui" in existing_data and isinstance(existing_data["ui"], dict):
            existing_data["ui"].pop(sub_key, None)
            if not existing_data["ui"]:
                existing_data.pop("ui", None)
        existing_data.pop(key, None)
    elif key.startswith("editor."):
        sub_key = key.split(".", 1)[1]
        if "editor" in existing_data and isinstance(existing_data["editor"], dict):
            existing_data["editor"].pop(sub_key, None)
            if not existing_data["editor"]:
                existing_data.pop("editor", None)
        existing_data.pop(key, None)
    else:
        existing_data.pop(key, None)

    _validate_config_dict(existing_data)
    toml_content = _dump_toml(existing_data)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=target_dir,
        prefix="config_",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(toml_content)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def resolve_effective_config(
    base_config: CommitConfig | None = None,
    overrides: CLIOverrides | None = None,
    config_path: Path | None = None,
) -> CommitConfig:
    """Resolve effective configuration with precedence: Defaults -> Global Config -> CLI Overrides.

    CLI overrides take precedence for the current invocation without modifying global config on disk.
    Omitted CLI overrides (None) preserve configured preferences.
    """
    cfg = base_config if base_config is not None else load_config(config_path)

    # Clone so we never mutate the base_config
    effective = copy.deepcopy(cfg)

    if overrides is not None:
        if overrides.mode is not None:
            if overrides.mode not in VALID_UI_MODES:
                raise InvalidConfigurationError(
                    f"Invalid CLI override for mode: {overrides.mode!r}. Must be one of: {sorted(VALID_UI_MODES)}"
                )
            effective.ui.mode = overrides.mode

        if overrides.appearance is not None:
            if overrides.appearance not in VALID_UI_APPEARANCES:
                raise InvalidConfigurationError(
                    f"Invalid CLI override for appearance: {overrides.appearance!r}. Must be one of: {sorted(VALID_UI_APPEARANCES)}"
                )
            effective.ui.appearance = overrides.appearance

        if overrides.model is not None:
            clean_model = overrides.model.strip()
            if not clean_model:
                raise InvalidConfigurationError("CLI override for 'model' must be a non-empty string.")
            effective.model = clean_model

    return effective


MAX_HISTORY_TITLE_CHARS = 500
MAX_HISTORY_DESC_CHARS = 8000


def append_history(
    repo_path: str,
    title: str,
    description: str,
    history_path: Path | None = None,
) -> None:
    """Append a commit record to history.jsonl in append-only JSON Lines format.

    Concurrency and Integrity Notes:
        This Phase 1 implementation uses standard Python append mode ('a') on a local
        file. While individual write calls are buffered, regular file appends do NOT
        provide atomic cross-process concurrency guarantees across operating systems
        (especially Windows or networked filesystems) without explicit file locking.
        Multi-process concurrent synchronization with file locking is deferred.

    Individual records are bounded in size to prevent unreasonably large history entries.
    """
    path = history_path or get_history_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    bounded_title = title[:MAX_HISTORY_TITLE_CHARS] if len(title) > MAX_HISTORY_TITLE_CHARS else title
    bounded_desc = (
        description[:MAX_HISTORY_DESC_CHARS] + "\n[Description truncated in history log]"
        if len(description) > MAX_HISTORY_DESC_CHARS
        else description
    )

    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "repo": repo_path,
        "title": bounded_title,
        "description": bounded_desc,
    }

    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def read_history(limit: int = 10, history_path: Path | None = None) -> list[dict[str, Any]]:
    """Read recent history records from history.jsonl."""
    path = history_path or get_history_file_path()
    if not path.is_file():
        return []

    records: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        records.append(json.loads(line_str))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []

    if limit > 0:
        return records[-limit:]
    return records

