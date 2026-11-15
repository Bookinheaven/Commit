"""Shared infrastructure and mechanics for full-screen Prompt Toolkit screens."""

from commit_cli.ui.screens.shared.application import (
    create_fullscreen_app,
    safe_exit,
    safe_invalidate,
)
from commit_cli.ui.screens.shared.keybindings import (
    build_guided_keybindings,
    build_menu_keybindings,
)
from commit_cli.ui.screens.shared.terminal import (
    get_terminal_size,
    is_terminal_too_small,
    run_terminal_action,
)

__all__ = [
    "create_fullscreen_app",
    "safe_exit",
    "safe_invalidate",
    "build_guided_keybindings",
    "build_menu_keybindings",
    "get_terminal_size",
    "is_terminal_too_small",
    "run_terminal_action",
]
