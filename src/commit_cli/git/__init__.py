"""Git abstraction layer for commit-cli."""

from commit_cli.git.commit import execute_commit
from commit_cli.git.diff import get_staged_diff, get_staged_snapshot
from commit_cli.git.repository import (
    get_commit_context_fingerprint,
    get_custom_rules,
    get_repo_root,
    get_repo_state,
    get_staged_files,
    get_staged_fingerprint,
    get_staged_stats,
    get_unstaged_files,
    get_untracked_files,
)
from commit_cli.git.runner import (
    run_git_captured,
    run_git_captured_raw,
    run_git_interactive,
)

__all__ = [
    "run_git_captured",
    "run_git_captured_raw",
    "run_git_interactive",
    "get_repo_root",
    "get_repo_state",
    "get_staged_files",
    "get_staged_fingerprint",
    "get_commit_context_fingerprint",
    "get_staged_stats",
    "get_unstaged_files",
    "get_untracked_files",
    "get_custom_rules",
    "get_staged_diff",
    "get_staged_snapshot",
    "execute_commit",
]

