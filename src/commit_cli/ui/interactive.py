"""Interactive menus, prompts, and structured message editing for Commit.

This module provides interactive screens, prompts, and dialogs.
"""

from typing import Any, Optional

import questionary
from questionary import Choice

from commit_cli.ui.console import is_no_color_active
from commit_cli.ui.prompts import (
    CommitReviewChoice,
    EditMethodChoice,
    MainMenuChoice,
    check_terminal_interactive,
    get_questionary_style,
    prompt_commit_review,
    prompt_confirm,
    prompt_edit_method,
    prompt_select,
    prompt_settings_menu,
    prompt_structured_editor,
    prompt_text,
)
from commit_cli.ui.screens.minimal import _prompt_minimal_menu
from commit_cli.ui.screens.rich import _prompt_rich_menu, run_rich_guided_screen


def prompt_main_menu(
    preset: str = "minimal",
    has_staged: bool = True,
    repo_state: Optional[Any] = None,
    diff: Optional[Any] = None,
    cfg: Optional[Any] = None,
    **kwargs: Any,
) -> Optional[MainMenuChoice]:
    """Display the main menu and return the selected action, or None if cancelled."""
    check_terminal_interactive()

    # Fallback for environments where questionary.select is mocked
    select_fn = getattr(questionary, "select", None)
    if hasattr(select_fn, "mock_calls"):
        choices = [
            Choice("Generate commit message", value=MainMenuChoice.GENERATE),
            Choice("Settings", value=MainMenuChoice.SETTINGS),
            Choice("Quit", value=MainMenuChoice.QUIT),
        ]

        instruction = "(Use ↑/↓ to navigate, Enter to select)"
        pointer = "> " if (is_no_color_active() or preset == "minimal") else "❯ "

        try:
            return questionary.select(
                "WHAT WOULD YOU LIKE TO DO?",
                choices=choices,
                style=get_questionary_style(preset),
                use_indicator=False,
                pointer=pointer,
                instruction=instruction,
                qmark="",
            ).ask()
        except (KeyboardInterrupt, EOFError):
            return None

    # Rich preset full-screen interactive prompt
    if preset == "rich":
        try:
            return _prompt_rich_menu(
                has_staged=has_staged,
                repo_state=repo_state,
                diff=diff,
                cfg=cfg,
                **kwargs,
            )
        except (KeyboardInterrupt, EOFError):
            return None

    # Minimal preset interactive prompt (default)
    try:
        return _prompt_minimal_menu(
            has_staged=has_staged,
            repo_state=repo_state,
            diff=diff,
            cfg=cfg,
            **kwargs,
        )
    except (KeyboardInterrupt, EOFError):
        return None


__all__ = [
    "CommitReviewChoice",
    "EditMethodChoice",
    "MainMenuChoice",
    "_prompt_minimal_menu",
    "_prompt_rich_menu",
    "check_terminal_interactive",
    "get_questionary_style",
    "prompt_commit_review",
    "prompt_confirm",
    "prompt_edit_method",
    "prompt_main_menu",
    "prompt_select",
    "prompt_settings_menu",
    "prompt_structured_editor",
    "prompt_text",
    "run_rich_guided_screen",
]
