"""Staged diff extraction and processing with bounded-memory spooling."""

from pathlib import Path

from commit_cli.exceptions import StagedStateChangedError
from commit_cli.git.repository import (
    get_commit_context_fingerprint,
    get_repo_root,
    get_staged_files,
    get_staged_stats,
)
from commit_cli.git.runner import run_git_to_spool
from commit_cli.models import StagedDiff, StagedSnapshot


def get_staged_diff(
    cwd: Path | str | None = None,
    max_chars: int | None = None,
    max_spool_memory: int = 2 * 1024 * 1024,
) -> StagedDiff:
    """Extract and structure the staged diff from the Git index with bounded memory.

    Streams output directly into a SpooledTemporaryFile to ensure safe processing
    of large diffs without unbounded RAM growth.

    Inspects staged changes exclusively. Never alters index or working tree.
    Binary files are identified and their content omitted.
    """
    root = get_repo_root(cwd)
    staged_files = get_staged_files(root)

    if not staged_files:
        return StagedDiff(raw_diff="", files=[])

    total_adds, total_dels = get_staged_stats(root)

    # Standard Git diff for staged changes with unified=3
    cmd = [
        "diff",
        "--cached",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--unified=3",
    ]
    spool, returncode, total_chars = run_git_to_spool(cmd, cwd=root, max_spool_memory=max_spool_memory)

    # If small (<= 2MB), load in-memory string for instant fast-path access
    if total_chars <= 2 * 1024 * 1024:
        spool.seek(0)
        diff_text = spool.read()
        return StagedDiff(
            raw_diff=diff_text,
            files=staged_files,
            total_additions=total_adds,
            total_deletions=total_dels,
            is_truncated=False,
            original_char_count=total_chars,
            truncated_char_count=total_chars,
            spool=spool,
        )

    # Large diff: content is safely spooled on disk (or in memory threshold)
    return StagedDiff(
        raw_diff="",
        files=staged_files,
        total_additions=total_adds,
        total_deletions=total_dels,
        is_truncated=False,
        original_char_count=total_chars,
        truncated_char_count=total_chars,
        spool=spool,
    )


def get_staged_snapshot(
    cwd: Path | str | None = None,
    max_chars: int | None = None,
    max_spool_memory: int = 2 * 1024 * 1024,
) -> StagedSnapshot:
    """Capture a consistent snapshot of staged changes and its composite commit context fingerprint.

    Ensures that neither the index, HEAD commit, nor branch reference mutated
    while the diff was being assembled.

    Raises:
        StagedStateChangedError: If the index, HEAD, or branch context changed during extraction.
    """
    root = get_repo_root(cwd)
    fp_before = get_commit_context_fingerprint(root)
    diff = get_staged_diff(root, max_chars=max_chars, max_spool_memory=max_spool_memory)
    fp_after = get_commit_context_fingerprint(root)

    if fp_before != fp_after:
        diff.close()
        raise StagedStateChangedError(
            expected_fingerprint=fp_before,
            actual_fingerprint=fp_after,
            message="Staged changes or Git commit context were modified while assembling diff snapshot. Re-run to inspect updated state.",
        )

    return StagedSnapshot(diff=diff, fingerprint=fp_after)

