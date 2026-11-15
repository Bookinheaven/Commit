"""Safe Git commit execution engine.

Concurrency and Atomic Locking Notice:
A fingerprint verification performed immediately prior to `git commit` is a
snapshot comparison, not a POSIX atomic lock on the Git index. Another process
(such as an IDE, background watcher, or concurrent terminal command) could
theoretically modify the index in the narrow window between fingerprint
re-calculation and Git acquiring its index lock. Furthermore, standard user
Git hooks (e.g. pre-commit hooks, formatters, or linters) may deliberately modify
staged files during commit execution.

Commit CLI explicitly preserves standard Git hook execution and does not claim
that pre-commit fingerprint verification eliminates concurrent filesystem race
conditions. It provides strict defense against stale generation commits while
respecting the Git ecosystem's standard commit lifecycle.
"""

from pathlib import Path

from commit_cli.exceptions import (
    GitCommandError,
    InvalidRepositoryStateError,
    StagedStateChangedError,
)
from commit_cli.git.repository import (
    get_commit_context_fingerprint,
    get_repo_root,
    get_repo_state,
    get_staged_files,
)
from commit_cli.git.runner import run_git_interactive
from commit_cli.models import CommitMessage
from commit_cli.parser.commit import validate_commit_message


def execute_commit(
    root: Path | str,
    message: CommitMessage,
    expected_fingerprint: str,
) -> None:
    """Execute a Git commit after verifying index integrity and repository state.

    Invariants:
    - Never stages files (`git add` is never executed).
    - Never pushes to a remote (`git push` is never executed).
    - Never bypasses Git hooks (`--no-verify` is never passed).
    - Never alters working-tree files (`git checkout/restore/reset` is never executed).
    - Verifies that the staged index fingerprint matches expected_fingerprint
      immediately before invoking the Git commit subprocess.

    Args:
        root: Path to the repository or worktree root.
        message: Validated CommitMessage instance to commit.
        expected_fingerprint: SHA-256 fingerprint from the generation snapshot.

    Raises:
        StagedStateChangedError: If the index changed after snapshot capture.
        InvalidRepositoryStateError: If repository is bare, in conflict, or index is empty.
        CommitValidationError: If the message fails Conventional Commit validation.
        GitCommandError: If the git commit subprocess exits with non-zero status.
    """
    repo_root = get_repo_root(root)

    # 1. Defense-in-depth: Validate commit message model
    validate_commit_message(message)

    # 2. Validate repository state
    repo_state = get_repo_state(repo_root)
    if repo_state.is_bare:
        raise InvalidRepositoryStateError("Cannot commit in a bare repository.")
    if repo_state.has_unmerged_paths:
        raise InvalidRepositoryStateError("Cannot commit: repository has unresolved merge conflicts.")

    # 3. Snapshot Verification: Recalculate and verify composite commit context fingerprint immediately before commit
    current_fp = get_commit_context_fingerprint(repo_root)
    if current_fp != expected_fingerprint:
        raise StagedStateChangedError(
            expected_fingerprint=expected_fingerprint,
            actual_fingerprint=current_fp,
            message="Staged changes, HEAD, or commit context were modified after generation snapshot was captured. Commit aborted.",
        )

    # 4. Verify staging area is not empty
    staged = get_staged_files(repo_root)
    if not staged:
        raise InvalidRepositoryStateError("Cannot commit: Git staging area is empty.")

    # 5. Build commit command arguments without losing title, body, or formatting
    cmd_args = ["commit", "-m", message.title()]
    if message.body and message.body.strip():
        cmd_args.extend(["-m", message.body.strip()])
    if message.breaking_change and message.breaking_change.strip():
        cmd_args.extend(["-m", f"BREAKING CHANGE: {message.breaking_change.strip()}"])

    # 6. Execute commit via Mode B (interactive) to preserve hooks, GPG signing, and stdio
    returncode = run_git_interactive(cmd_args, cwd=repo_root)
    if returncode != 0:
        raise GitCommandError(
            command=["git", *cmd_args],
            returncode=returncode,
            stdout="",
            stderr="Git commit failed (hooks rejected commit or user cancelled).",
        )
