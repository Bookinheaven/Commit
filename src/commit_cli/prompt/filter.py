"""Transparent diff filtering for noise and generated files."""

import re
from pathlib import Path

from commit_cli.models import FileStatus, StagedDiff

LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "bun.lockb",
    "composer.lock",
    "Pipfile.lock",
}

NOISE_EXTENSIONS = {
    ".min.js",
    ".min.css",
    ".map",
}


def is_noise_file(path_str: str) -> bool:
    """Check if a file path represents a lockfile, minified asset, or source map."""
    p = Path(path_str)
    if p.name in LOCKFILE_NAMES:
        return True
    lower = p.name.lower()
    return any(lower.endswith(ext) for ext in NOISE_EXTENSIONS)


def filter_diff_noise(diff: StagedDiff, exclude_deleted: bool = True) -> str:
    """Filter noise from staged diff while retaining metadata headers and statistics.

    Replaces auto-generated lockfile and minified asset churn with transparent
    summaries, conserving context window without hiding the fact that these files
    were modified. When exclude_deleted is True, fully deleted file contents are omitted
    from the content diff since their metadata is captured separately.
    """
    raw_diff = diff.raw_diff
    if not raw_diff.strip():
        return ""

    file_metadata_map = {f.path: f for f in diff.files}
    deleted_paths = {f.path for f in diff.files if f.status == FileStatus.DELETED}

    # Split diff cleanly on file boundaries: 'diff --git a/'
    parts = re.split(r"(^diff --git a/)", raw_diff, flags=re.MULTILINE)
    if len(parts) < 2:
        return raw_diff

    filtered_sections: list[str] = []
    # parts[0] is preamble/empty. Each file is parts[i] (delimiter) + parts[i+1] (content)
    for i in range(1, len(parts), 2):
        file_diff = parts[i] + parts[i + 1]
        first_line = file_diff.splitlines()[0] if file_diff else ""

        path = ""
        for line in file_diff.splitlines()[:15]:
            if line.startswith("+++ b/"):
                path = line[6:].strip()
                break
            if line.startswith("--- a/") and "+++ /dev/null" in file_diff:
                path = line[6:].strip()
                break
        if not path:
            m = re.match(r"^diff --git a/(.*?)\s+b/(.*)$", first_line)
            if m:
                path = m.group(2).strip()

        file_meta = file_metadata_map.get(path)
        if file_meta is None and path:
            # Fallback check for source path if renamed or deleted
            m_src = re.match(r"^diff --git a/(.*?)\s+b/", first_line)
            if m_src:
                file_meta = file_metadata_map.get(m_src.group(1).strip())

        is_deleted = (
            (file_meta is not None and file_meta.status == FileStatus.DELETED)
            or (path in deleted_paths)
            or ("deleted file mode " in file_diff)
            or ("+++ /dev/null" in file_diff)
        )
        if exclude_deleted and is_deleted:
            continue

        is_binary = file_meta.is_binary if file_meta else ("Binary files " in file_diff)

        if is_noise_file(path) or is_binary:
            # Preserve headers (up to index or binary marker)
            lines = file_diff.splitlines()
            header_lines: list[str] = []
            for line in lines:
                header_lines.append(line)
                if line.startswith("index ") or line.startswith("Binary files ") or line.startswith("new file mode "):
                    break
            header_text = "\n".join(header_lines)

            adds = file_meta.additions if file_meta else 0
            dels = file_meta.deletions if file_meta else 0
            reason = "binary data" if is_binary else "auto-generated lockfile or minified asset"
            summary_notice = (
                f"\n[File content excluded: {reason} (+{adds}/-{dels} lines). Intent: build/dependency change]\n"
            )
            filtered_sections.append(header_text + summary_notice)
        else:
            filtered_sections.append(file_diff)

    return "".join(filtered_sections)
