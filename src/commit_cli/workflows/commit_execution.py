"""Commit execution, fingerprint validation, and history recording workflows."""

from pathlib import Path
from typing import Callable, Optional

from rich.console import Console

from commit_cli.exceptions import (
    GitCommandError,
    InvalidRepositoryStateError,
    StagedStateChangedError,
)
from commit_cli.git import execute_commit
from commit_cli.config import append_history
from commit_cli.models import CommitMessage, StagedSnapshot
from commit_cli.ui import render_error, render_success, render_warning


def record_history_safe(
    repo_root: Path,
    message: CommitMessage,
    console: Optional[Console] = None,
    append_history_fn: Optional[Callable] = None,
) -> None:
    """Record a commit entry in history.jsonl using repository name without leaking full path.

    If history logging fails, a warning is emitted but the successful commit is preserved.
    """
    repo_identifier = repo_root.name
    history_recorder = append_history_fn or append_history
    try:
        history_recorder(
            repo_path=repo_identifier,
            title=message.title(),
            description=message.body or "",
        )
    except Exception as e:
        render_warning(f"Failed to record commit in history: {e}", console=console)


def execute_commit_safe(
    repo_root: Path,
    candidate_msg: CommitMessage,
    snapshot: StagedSnapshot,
    console: Console,
    err_console: Console,
    preset: str,
    execute_commit_fn: Optional[Callable] = None,
    record_history_fn: Optional[Callable] = None,
) -> int:
    """Execute commit with fingerprint check, handle errors without tracebacks, and record history."""
    committer = execute_commit_fn or execute_commit
    recorder = record_history_fn or record_history_safe

    try:
        committer(
            root=repo_root,
            message=candidate_msg,
            expected_fingerprint=snapshot.fingerprint,
        )
    except StagedStateChangedError as e:
        render_error(
            "Staged changes (Git index) or HEAD commit changed before commit could be executed.",
            detail=str(e),
            console=err_console,
            preset=preset,
        )
        return 3
    except GitCommandError as e:
        render_error("Git commit failed", detail=str(e), console=err_console, preset=preset)
        return 3
    except InvalidRepositoryStateError as e:
        render_error("Invalid repository state", detail=str(e), console=err_console, preset=preset)
        return 1

    recorder(repo_root, candidate_msg, console=err_console)
    render_success(f"Committed: {candidate_msg.title()}", console=console, preset=preset)
    return 0
