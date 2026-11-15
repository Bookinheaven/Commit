"""Interactive action handlers for Rich screen (editing, feedback, and regeneration)."""

from typing import Any, Optional

from commit_cli.exceptions import CommitValidationError
from commit_cli.models import CommitMessage
from commit_cli.ui.prompts import (
    EditMethodChoice,
    prompt_edit_method,
    prompt_structured_editor,
    prompt_text,
)


def handle_rich_edit(
    candidate_msg: Optional[CommitMessage],
    cfg: Optional[Any],
    err_console: Optional[Any],
) -> Optional[CommitMessage]:
    """Execute message editing in Rich mode via structured or external editor."""
    if candidate_msg is None:
        return None

    edit_method = prompt_edit_method(preset="rich")
    if edit_method == EditMethodChoice.STRUCTURED:
        try:
            edited = prompt_structured_editor(candidate_msg, preset="rich")
            if edited is not None:
                return edited
        except CommitValidationError as err:
            if err_console:
                err_console.print(f"Error: {err}")
    elif edit_method == EditMethodChoice.EXTERNAL:
        try:
            from commit_cli.ui.editor import edit_message_externally
            cmd = cfg.editor.command if cfg and getattr(cfg, "editor", None) else None
            edited = edit_message_externally(candidate_msg, editor_command=cmd)
            if edited is not None:
                return edited
        except Exception as err:
            if err_console:
                err_console.print(f"Error: {err}")

    return candidate_msg


def handle_rich_regenerate() -> Optional[str]:
    """Prompt user for optional regeneration feedback in Rich mode."""
    import commit_cli.ui.screens.rich as rich_mod
    prompt_fn = getattr(rich_mod, "prompt_text", prompt_text)
    return prompt_fn("Regeneration feedback / instructions (optional):", preset="rich")
