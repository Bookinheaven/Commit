"""Controlled Rich Console construction and terminal capability handling."""

import os
import sys
from typing import IO, Literal, Optional

from rich.console import Console

from commit_cli.ui.theme import get_theme


def is_no_color_active() -> bool:
    """Check whether NO_COLOR is set in the environment according to no-color.org."""
    return bool(os.environ.get("NO_COLOR", ""))


def create_console(
    *,
    file: Optional[IO[str]] = None,
    stderr: bool = False,
    force_terminal: Optional[bool] = None,
    color_system: Optional[Literal["auto", "standard", "256", "truecolor", "windows"]] = "auto",
    width: Optional[int] = None,
    preset: str = "minimal",
    no_color: Optional[bool] = None,
    highlight: bool = False,
    markup: bool = True,
) -> Console:
    """Create a configured Rich Console instance with explicit control over capabilities.

    Args:
        file: Target text stream (e.g., sys.stdout, sys.stderr, or a io.StringIO).
        stderr: Route to standard error if file is omitted.
        force_terminal: Override terminal detection (useful for testing escape sequences).
        color_system: Terminal color capacity or None to disable colors.
        width: Terminal column width; if None, detected dynamically.
        preset: Appearance preset name ('minimal', 'rich') determining the theme.
        no_color: Suppress color sequences. If None, checks NO_COLOR environment variable.
        highlight: Whether to run Rich's automatic regex highlighters.
        markup: Whether to parse Rich markup tags by default.
    """
    theme = get_theme(preset)

    resolved_no_color = no_color if no_color is not None else is_no_color_active()

    return Console(
        file=file,
        stderr=stderr,
        theme=theme,
        force_terminal=force_terminal,
        color_system=None if resolved_no_color else color_system,
        width=width,
        no_color=resolved_no_color,
        highlight=highlight,
        markup=markup,
    )


def get_console(
    stderr: bool = False,
    preset: str = "minimal",
) -> Console:
    """Get a Console targeted at stdout or stderr using the configured appearance preset."""
    target_stream = sys.stderr if stderr else sys.stdout
    return create_console(
        file=target_stream,
        stderr=stderr,
        preset=preset,
    )
