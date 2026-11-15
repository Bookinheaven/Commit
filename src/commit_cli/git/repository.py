"""Repository inspection functions for Git repositories."""

import hashlib
from pathlib import Path

from commit_cli.exceptions import (
    GitCommandError,
    InvalidRepositoryStateError,
    NotAGitRepositoryError,
)
from commit_cli.git.runner import (
    _is_not_git_repo_msg,
    run_git_captured,
    run_git_captured_raw,
)
from commit_cli.models import FileMetadata, FileStatus, RepoState


def get_repo_root(cwd: Path | str | None = None) -> Path:
    """Return the absolute path of the Git repository root or worktree root.

    Handles standard repositories, worktrees, and bare repositories.
    """
    res = run_git_captured(["rev-parse", "--show-toplevel"], cwd=cwd, check=False)
    if res.is_success and res.stdout.strip():
        return Path(res.stdout.strip()).resolve()

    # Check if this is a bare repository
    bare_res = run_git_captured(["rev-parse", "--is-bare-repository"], cwd=cwd, check=False)
    if bare_res.is_success and bare_res.stdout.strip().lower() == "true":
        git_dir_res = run_git_captured(["rev-parse", "--git-dir"], cwd=cwd)
        git_dir_str = git_dir_res.stdout.strip()
        base_path = Path(cwd) if cwd is not None else Path.cwd()
        git_dir_path = Path(git_dir_str)
        if not git_dir_path.is_absolute():
            git_dir_path = (base_path / git_dir_path).resolve()
        return git_dir_path

    raise NotAGitRepositoryError(str(cwd) if cwd else "")


def _resolve_git_metadata_path(path_name: str, root: Path) -> Path:
    """Resolve an absolute path to Git metadata (e.g. rebase-merge, index).

    Works correctly across standard repositories, nested subdirectories,
    and linked worktrees without assuming .git is always a directory.
    """
    res = run_git_captured(["rev-parse", "--path-format=absolute", "--git-path", path_name], cwd=root, check=False)
    if res.is_success and res.stdout.strip():
        p = Path(res.stdout.strip())
        if p.is_absolute():
            return p

    res_rel = run_git_captured(["rev-parse", "--git-path", path_name], cwd=root, check=False)
    if res_rel.is_success and res_rel.stdout.strip():
        raw = Path(res_rel.stdout.strip())
        return raw if raw.is_absolute() else (root / raw).resolve()

    return (root / ".git" / path_name).resolve()


def get_repo_state(cwd: Path | str | None = None) -> RepoState:
    """Inspect and return the comprehensive state of the Git repository."""
    root = get_repo_root(cwd)

    # 1. Bare repository check
    bare_res = run_git_captured(["rev-parse", "--is-bare-repository"], cwd=root)
    is_bare = bare_res.stdout.strip().lower() == "true"

    # 2. Branch & Detached HEAD detection
    branch: str | None = None
    is_detached = False
    branch_res = run_git_captured(
        ["symbolic-ref", "--short", "-q", "HEAD"],
        cwd=root,
        check=False,
    )
    if branch_res.is_success and branch_res.stdout.strip():
        branch = branch_res.stdout.strip()
    else:
        is_detached = True

    # 3. Head commit SHA
    head_res = run_git_captured(["rev-parse", "--short", "HEAD"], cwd=root, check=False)
    head_commit = head_res.stdout.strip() if head_res.is_success else None

    # 4. In-progress operations: Merge, Rebase, Cherry-Pick
    # Merge
    merge_res = run_git_captured(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=root, check=False)
    is_merge = merge_res.is_success and bool(merge_res.stdout.strip())

    # Cherry-pick
    cp_res = run_git_captured(["rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD"], cwd=root, check=False)
    is_cherry_pick = cp_res.is_success and bool(cp_res.stdout.strip())

    # Rebase (check both rebase-merge and rebase-apply across worktrees and subdirs)
    is_rebase = False
    rebase_merge_path = _resolve_git_metadata_path("rebase-merge", root)
    if rebase_merge_path.exists():
        is_rebase = True
    else:
        rebase_apply_path = _resolve_git_metadata_path("rebase-apply", root)
        if rebase_apply_path.exists():
            is_rebase = True

    # 5. Unmerged index paths (conflicts)
    unmerged_res = run_git_captured(["diff", "--name-only", "--diff-filter=U", "-z"], cwd=root, check=False)
    has_unmerged = bool(unmerged_res.stdout) if unmerged_res.is_success else False

    return RepoState(
        root=root,
        branch=branch,
        is_detached=is_detached,
        is_bare=is_bare,
        is_merge_in_progress=is_merge,
        is_rebase_in_progress=is_rebase,
        is_cherry_pick_in_progress=is_cherry_pick,
        has_unmerged_paths=has_unmerged,
        head_commit=head_commit,
    )


def _parse_numstat(output: str) -> dict[str, tuple[bool, int, int]]:
    """Parse NUL-delimited numstat output.

    Uses bounded field splitting to preserve filenames containing tab characters.
    Returns mapping: path -> (is_binary, additions, deletions)
    """
    stats: dict[str, tuple[bool, int, int]] = {}
    tokens = output.split("\0")
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if not token:
            idx += 1
            continue

        parts = token.split("\t", 2)
        if len(parts) >= 2:
            add_str, del_str = parts[0], parts[1]
            path = parts[2] if len(parts) == 3 else ""

            # When path is empty (rename/copy header in -z), next tokens are old_path and new_path
            if not path and idx + 2 < len(tokens):
                idx += 1
                old_p = tokens[idx]
                idx += 1
                new_p = tokens[idx]
                path = new_p

            is_bin = (add_str == "-" and del_str == "-")
            adds = 0 if is_bin else (int(add_str) if add_str.isdigit() else 0)
            dels = 0 if is_bin else (int(del_str) if del_str.isdigit() else 0)
            stats[path] = (is_bin, adds, dels)
        idx += 1

    return stats


def get_staged_files(cwd: Path | str | None = None) -> list[FileMetadata]:
    """Return structured metadata for all files staged in the Git index.

    Uses NUL-delimited output to safely handle filenames with spaces, unicode, and quotes.
    Never modifies the Git index or working tree.
    """
    root = get_repo_root(cwd)

    # 1. Fetch raw status and modes
    raw_res = run_git_captured(["diff", "--cached", "--raw", "-z"], cwd=root)
    if not raw_res.stdout:
        return []

    # 2. Fetch numstat for binary detection and line counts
    numstat_res = run_git_captured(["diff", "--cached", "--numstat", "-z"], cwd=root)
    numstat_map = _parse_numstat(numstat_res.stdout)

    files: list[FileMetadata] = []
    tokens = raw_res.stdout.split("\0")
    i = 0
    while i < len(tokens):
        item = tokens[i]
        if not item or not item.startswith(":"):
            i += 1
            continue

        # Item format: :<src_mode> <dst_mode> <src_sha> <dst_sha> <status>
        meta_parts = item[1:].split()
        if len(meta_parts) < 5:
            i += 1
            continue

        src_mode, dst_mode, _, _, status_code = meta_parts[:5]
        status_char = status_code[0]
        status = FileStatus.from_git_status_char(status_char)

        is_symlink = dst_mode == "120000" or src_mode == "120000"
        is_submodule = dst_mode == "160000" or src_mode == "160000"

        old_path: str | None = None
        i += 1
        if i >= len(tokens):
            break

        if status_char in ("R", "C"):
            # Rename / Copy provides old_path then new_path
            old_path = tokens[i]
            i += 1
            path = tokens[i] if i < len(tokens) else old_path
        else:
            path = tokens[i]

        stat_info = numstat_map.get(path, (False, 0, 0))
        is_bin, adds, dels = stat_info

        files.append(
            FileMetadata(
                path=path,
                status=status,
                old_path=old_path,
                is_binary=is_bin,
                is_symlink=is_symlink,
                is_submodule=is_submodule,
                additions=adds,
                deletions=dels,
            )
        )
        i += 1

    return files


def get_unstaged_files(cwd: Path | str | None = None) -> list[str]:
    """Return relative paths of tracked files with unstaged modifications or deletions."""
    root = get_repo_root(cwd)
    res = run_git_captured(["diff", "--name-only", "-z"], cwd=root)
    return [p for p in res.stdout.split("\0") if p]


def get_untracked_files(cwd: Path | str | None = None) -> list[str]:
    """Return relative paths of untracked files not ignored by .gitignore."""
    root = get_repo_root(cwd)
    res = run_git_captured(["ls-files", "--others", "--exclude-standard", "-z"], cwd=root)
    return [p for p in res.stdout.split("\0") if p]


def get_staged_stats(cwd: Path | str | None = None) -> tuple[int, int]:
    """Return (total_additions, total_deletions) for staged changes."""
    root = get_repo_root(cwd)
    res = run_git_captured(["diff", "--cached", "--numstat", "-z"], cwd=root)
    numstat_map = _parse_numstat(res.stdout)
    total_adds = sum(stat[1] for stat in numstat_map.values())
    total_dels = sum(stat[2] for stat in numstat_map.values())
    return total_adds, total_dels


def get_custom_rules(cwd: Path | str | None = None) -> str:
    """Read optional .commitrules or .commit-rules from repo root without modifying."""
    try:
        root = get_repo_root(cwd)
        for rule_file in (".commitrules", ".commit-rules"):
            rule_path = root / rule_file
            if rule_path.is_file():
                with open(rule_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
    except Exception:
        pass
    return ""


def get_staged_fingerprint(cwd: Path | str | None = None) -> str:
    """Calculate a deterministic SHA-256 fingerprint of the current Git index.

    Uses `git ls-files --stage -z` to capture the exact modes, object SHAs,
    stages, and NUL-delimited paths of all staged entries without lossy UTF-8
    conversions. Never modifies the Git index or working tree.

    Returns:
        Hex-encoded SHA-256 string (64 characters).
    """
    root = get_repo_root(cwd)
    raw_stdout, _, _ = run_git_captured_raw(["ls-files", "--stage", "-z"], cwd=root)
    return hashlib.sha256(raw_stdout).hexdigest()


def get_commit_context_fingerprint(cwd: Path | str | None = None) -> str:
    """Calculate a deterministic composite SHA-256 fingerprint of the Git commit context.

    Incorporates:
    1. Raw index entries from `git ls-files --stage -z`.
    2. Current HEAD commit object ID (or empty if unborn branch).
    3. Current symbolic HEAD reference (or empty if detached HEAD).

    Uses unambiguous, labelled, length-prefixed fields to prevent collision or boundary
    shifting across normal branches, detached HEAD, and unborn branches.
    Never modifies the Git index or working tree.

    Returns:
        Hex-encoded SHA-256 string (64 characters).
    """
    root = get_repo_root(cwd)

    # 1. Fetch raw index entries
    raw_index, _, _ = run_git_captured_raw(["ls-files", "--stage", "-z"], cwd=root)

    # 2. Fetch HEAD commit object ID (empty bytes if unborn branch)
    head_cmd = ["rev-parse", "--verify", "-q", "HEAD"]
    raw_head, head_err, head_rc = run_git_captured_raw(head_cmd, cwd=root, check=False)

    # 3. Fetch symbolic HEAD reference (empty bytes if detached HEAD)
    ref_cmd = ["symbolic-ref", "-q", "HEAD"]
    raw_ref, ref_err, ref_rc = run_git_captured_raw(ref_cmd, cwd=root, check=False)

    # Validate return codes: only 0 and 1 are accepted
    if head_rc not in (0, 1):
        err_str = head_err.decode("utf-8", errors="replace")
        if _is_not_git_repo_msg(err_str):
            raise NotAGitRepositoryError(str(root))
        raise GitCommandError(
            command=["git", *head_cmd],
            returncode=head_rc,
            stdout=raw_head.decode("utf-8", errors="replace"),
            stderr=err_str,
        )

    if ref_rc not in (0, 1):
        err_str = ref_err.decode("utf-8", errors="replace")
        if _is_not_git_repo_msg(err_str):
            raise NotAGitRepositoryError(str(root))
        raise GitCommandError(
            command=["git", *ref_cmd],
            returncode=ref_rc,
            stdout=raw_ref.decode("utf-8", errors="replace"),
            stderr=err_str,
        )

    # Validate combined outcome combinations:
    # 0, 0 -> Normal branch
    # 0, 1 -> Detached HEAD
    # 1, 0 -> Unborn branch
    # 1, 1 -> Invalid or unexpected state; reject
    if head_rc == 1 and ref_rc == 1:
        raise InvalidRepositoryStateError(
            "Invalid or unexpected Git state: neither HEAD commit nor symbolic ref could be resolved."
        )

    clean_head = raw_head.strip()
    clean_ref = raw_ref.strip()

    # Ensure expected absence cases return empty stdout, and non-absence cases return non-empty
    if head_rc == 1:
        # Expected absence of HEAD (unborn branch)
        if clean_head:
            raise InvalidRepositoryStateError(
                f"Unexpected output from rev-parse for unborn HEAD (exit code 1): {raw_head!r}"
            )
        if head_err.strip():
            err_str = head_err.decode("utf-8", errors="replace")
            raise GitCommandError(
                command=["git", *head_cmd],
                returncode=head_rc,
                stdout=raw_head.decode("utf-8", errors="replace"),
                stderr=err_str,
            )
    else:
        # head_rc == 0
        if not clean_head:
            raise InvalidRepositoryStateError(
                "HEAD rev-parse succeeded with exit code 0 but returned an empty commit ID."
            )

    if ref_rc == 1:
        # Expected absence of symbolic ref (detached HEAD)
        if clean_ref:
            raise InvalidRepositoryStateError(
                f"Unexpected output from symbolic-ref for detached HEAD (exit code 1): {raw_ref!r}"
            )
        if ref_err.strip():
            err_str = ref_err.decode("utf-8", errors="replace")
            raise GitCommandError(
                command=["git", *ref_cmd],
                returncode=ref_rc,
                stdout=raw_ref.decode("utf-8", errors="replace"),
                stderr=err_str,
            )
    else:
        # ref_rc == 0
        if not clean_ref:
            raise InvalidRepositoryStateError(
                "symbolic-ref succeeded with exit code 0 but returned an empty reference."
            )

    # Combine using unambiguous labelled length-prefixed blocks
    hasher = hashlib.sha256()
    hasher.update(b"HEAD:" + str(len(clean_head)).encode("ascii") + b":" + clean_head + b"\n")
    hasher.update(b"REF:" + str(len(clean_ref)).encode("ascii") + b":" + clean_ref + b"\n")
    hasher.update(b"INDEX:" + str(len(raw_index)).encode("ascii") + b":" + raw_index + b"\n")

    return hasher.hexdigest()
