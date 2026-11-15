"""Terminal size inspection and terminal suspension mechanics for full-screen UI."""

import shutil
from typing import Callable

from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.application.current import get_app


def get_terminal_size() -> tuple[int, int]:
    """Retrieve terminal dimensions (columns, rows) safely."""
    try:
        size = get_app().output.get_size()
        return size.columns, size.rows
    except Exception:
        cols, rows = shutil.get_terminal_size((80, 24))
        return cols, rows


def is_terminal_too_small(w: int, h: int, min_w: int = 50, min_h: int = 18) -> bool:
    """Return True if terminal dimensions are below the required minimums."""
    return w < min_w or h < min_h


def run_terminal_action(action: Callable[[], None]) -> None:
    """Suspend full-screen Prompt Toolkit application and execute an action in ordinary terminal."""
    run_in_terminal(action)
