"""Centralized styles, semantic themes, and appearance presets for Commit."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from rich import box
from rich.theme import Theme


class AppearancePreset(str, Enum):
    """Supported UI appearance presets."""

    MINIMAL = "minimal"
    RICH = "rich"


# Semantic themes mapping functional UI roles to Rich styles
MINIMAL_THEME = Theme(
    {
        "heading": "bold",
        "subheading": "bold",
        "label": "dim",
        "key": "bold",
        "value": "default",
        "success": "bold",
        "warning": "bold",
        "error": "bold",
        "info": "default",
        "muted": "dim",
        "path": "default",
        "status.added": "bold",
        "status.modified": "default",
        "status.deleted": "dim",
        "status.renamed": "default",
        "status.binary": "dim",
        "status.untracked": "dim",
        "commit.type": "bold",
        "commit.scope": "dim",
        "commit.bang": "bold",
        "commit.subject": "default",
        "commit.body": "default",
        "commit.breaking": "bold",
        "diff.header": "bold",
        "diff.addition": "default",
        "diff.deletion": "dim",
        "provisional": "dim italic",
    }
)

RICH_THEME = Theme(
    {
        "heading": "bold magenta",
        "subheading": "bold cyan",
        "label": "cyan",
        "key": "bold cyan",
        "value": "bold green",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "info": "bold blue",
        "muted": "dim",
        "path": "bold blue",
        "status.added": "bold green",
        "status.modified": "bold yellow",
        "status.deleted": "bold red",
        "status.renamed": "bold cyan",
        "status.binary": "bold magenta",
        "status.untracked": "dim italic",
        "commit.type": "bold magenta",
        "commit.scope": "bold cyan",
        "commit.bang": "bold red",
        "commit.subject": "bold white",
        "commit.body": "default",
        "commit.breaking": "bold white on red",
        "diff.header": "bold magenta",
        "diff.addition": "bold green",
        "diff.deletion": "bold red",
        "provisional": "bold yellow",
    }
)


@dataclass(frozen=True)
class PresetStyle:
    """Visual presentation configuration for an appearance preset."""

    name: str
    theme: Theme
    syntax_theme: str
    box_style: Any
    use_panels: bool
    show_line_numbers: bool
    icon_success: str
    icon_warning: str
    icon_error: str
    icon_info: str


PRESET_CONFIGS: dict[str, PresetStyle] = {
    AppearancePreset.MINIMAL.value: PresetStyle(
        name="minimal",
        theme=MINIMAL_THEME,
        syntax_theme="bw",
        box_style=None,
        use_panels=False,
        show_line_numbers=False,
        icon_success="Success:",
        icon_warning="Warning:",
        icon_error="Error:",
        icon_info="Info:",
    ),
    AppearancePreset.RICH.value: PresetStyle(
        name="rich",
        theme=RICH_THEME,
        syntax_theme="monokai",
        box_style=box.ROUNDED,
        use_panels=True,
        show_line_numbers=True,
        icon_success="✔",
        icon_warning="⚠",
        icon_error="✖",
        icon_info="ℹ",
    ),
}


def get_preset_style(preset: str | None = None) -> PresetStyle:
    """Retrieve visual presentation configuration for a given preset name.

    Defaults to 'minimal' if None or an unrecognized preset is provided.
    """
    if not preset:
        return PRESET_CONFIGS[AppearancePreset.MINIMAL.value]
    cleaned = preset.strip().lower()
    return PRESET_CONFIGS.get(cleaned, PRESET_CONFIGS[AppearancePreset.MINIMAL.value])


def get_theme(preset: str | None = None) -> Theme:
    """Retrieve the Rich Theme associated with a preset name."""
    return get_preset_style(preset).theme
