"""Staged diff extraction and processing with bounded-memory spooling."""

from dataclasses import dataclass
from pathlib import Path

from commit_cli.exceptions import StagedStateChangedError
from commit_cli.git.repository import (
    get_commit_context_fingerprint,
    get_repo_root,
    get_staged_files,
    get_staged_stats,
)
from commit_cli.git.runner import run_git_to_spool
from commit_cli.models import FileMetadata, FileStatus, StagedDiff, StagedSnapshot


@dataclass(frozen=True)
class StatusAwareDiff:
    """Status-aware separation of staged changes into content diff and deletion metadata."""

    content_diff: str
    content_char_count: int
    eligible_files: list[FileMetadata]
    deleted_files: list[FileMetadata]
    deletion_manifest: str


def format_deletion_manifest(
    deleted_files: list[FileMetadata],
    max_chars: int | None = None,
) -> str:
    """Format metadata manifest for fully deleted files.

    Includes all deleted paths, their removed line counts or binary indicators,
    and a summary total without reading from the working filesystem.
    When max_chars is specified and uncompacted paths exceed budget, groups deleted
    files by directory to conserve context while preserving exact counts and line stats.
    """
    if not deleted_files:
        return ""

    from collections import defaultdict
    from pathlib import Path

    total_removed = 0
    full_lines = []

    for f in deleted_files:
        if f.is_binary:
            stat_desc = "binary"
        elif f.deletions is not None and f.deletions >= 0:
            count = f.deletions
            total_removed += count
            unit = "line" if count == 1 else "lines"
            stat_desc = f"-{count:,} {unit}"
        else:
            stat_desc = "line stats unavailable"
        full_lines.append(f"  D {f.path} ({stat_desc})")

    file_word = "file" if len(deleted_files) == 1 else "files"
    line_word = "line" if total_removed == 1 else "lines"
    summary_line = f"\n{len(deleted_files):,} {file_word} deleted, {total_removed:,} {line_word} removed."
    header_line = f"DELETED FILES ({len(deleted_files):,})\n"

    uncompacted = header_line + "\n".join(full_lines) + summary_line
    if max_chars is None or len(uncompacted) <= max_chars:
        return uncompacted

    # Compact directory-level summary: group by parent directory
    dir_groups: dict[str, list[FileMetadata]] = defaultdict(list)
    for f in deleted_files:
        parent = str(Path(f.path).parent)
        dir_groups[parent].append(f)

    def format_dir_line(dir_path: str, files: list[FileMetadata]) -> str:
        d_count = len(files)
        d_lines = sum(x.deletions for x in files if x.deletions is not None and x.deletions >= 0)
        bin_count = sum(1 for x in files if x.is_binary)
        unavail_count = sum(1 for x in files if not x.is_binary and (x.deletions is None or x.deletions < 0))

        display_dir = f"{dir_path}/*" if dir_path != "." else "* (root)"
        parts = [f"{d_count:,} {'file' if d_count == 1 else 'files'}"]
        if d_lines > 0:
            parts.append(f"-{d_lines:,} {'line' if d_lines == 1 else 'lines'} removed")
        if bin_count > 0:
            parts.append(f"{bin_count} binary")
        if unavail_count > 0:
            parts.append(f"{unavail_count} stats unavailable")
        return f"  D {display_dir} ({', '.join(parts)})"

    compact_header = (
        f"DELETED FILES ({len(deleted_files):,})\n"
        f"[Compact directory summary: individual file paths summarized by directory to fit model context budget]\n"
    )

    sorted_dirs = sorted(dir_groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    compact_lines = [format_dir_line(d, fls) for d, fls in sorted_dirs]
    compact_manifest = compact_header + "\n".join(compact_lines) + summary_line

    if len(compact_manifest) <= max_chars:
        return compact_manifest

    # If still exceeding max_chars, group by top-level directory
    top_groups: dict[str, list[FileMetadata]] = defaultdict(list)
    for f in deleted_files:
        parts = Path(f.path).parts
        top_dir = parts[0] if len(parts) > 1 else "."
        top_groups[top_dir].append(f)

    sorted_tops = sorted(top_groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    top_lines = [format_dir_line(d, fls) for d, fls in sorted_tops]
    top_manifest = compact_header + "\n".join(top_lines) + summary_line

    if len(top_manifest) <= max_chars:
        return top_manifest

    # If still too large, truncate directory list to fit within max_chars
    budgeted_lines = []
    accum_len = len(compact_header) + len(summary_line) + 200
    omitted_dirs = 0
    omitted_files = 0
    omitted_lines = 0

    for idx, (d, fls) in enumerate(sorted_tops):
        line = format_dir_line(d, fls)
        if accum_len + len(line) + 1 <= max_chars:
            budgeted_lines.append(line)
            accum_len += len(line) + 1
        else:
            omitted_dirs = len(sorted_tops) - idx
            omitted_files = sum(len(x[1]) for x in sorted_tops[idx:])
            omitted_lines = sum(
                sum(f.deletions for f in x[1] if f.deletions is not None and f.deletions >= 0)
                for x in sorted_tops[idx:]
            )
            break

    if omitted_dirs > 0:
        budgeted_lines.append(
            f"  ... and {omitted_dirs:,} additional directories ({omitted_files:,} files, -{omitted_lines:,} lines removed)"
        )
        budgeted_lines.append(
            f"  [Notice: {len(deleted_files):,} deleted paths summarized above. Complete deletion metadata retained internally.]"
        )

    return compact_header + "\n".join(budgeted_lines) + summary_line


def analyze_status_aware_diff(
    diff: StagedDiff,
    max_manifest_chars: int | None = None,
) -> StatusAwareDiff:
    """Perform status-aware diff analysis separating content diff from deletion metadata.

    Excludes fully deleted file contents while preserving all removals inside modified files.
    """
    from commit_cli.prompt.filter import filter_diff_noise

    deleted_files = [f for f in diff.files if f.status == FileStatus.DELETED]
    eligible_files = [f for f in diff.files if f.status != FileStatus.DELETED]

    manifest = format_deletion_manifest(deleted_files, max_chars=max_manifest_chars)
    content_diff = filter_diff_noise(diff, exclude_deleted=True)

    return StatusAwareDiff(
        content_diff=content_diff,
        content_char_count=len(content_diff),
        eligible_files=eligible_files,
        deleted_files=deleted_files,
        deletion_manifest=manifest,
    )


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

