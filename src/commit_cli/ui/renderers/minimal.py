"""Minimalist rendering logic, text layout, and plain-text review screens for Commit CLI."""

from typing import Any, Optional

from rich.console import Console, Group
from rich.spinner import Spinner
from rich.text import Text

from commit_cli.models import (
    CommitMessage,
    FileStatus,
    RepoState,
    StagedDiff,
    StagedSnapshot,
)
from commit_cli.ui.console import get_console, is_no_color_active
from commit_cli.ui.renderers.common import format_duration
from commit_cli.ui.renderers.components import _format_display_path


def render_minimal_initial_screen(
    repo_state: RepoState,
    diff: Optional[StagedDiff],
    console: Optional[Console] = None,
) -> None:
    """Render the Minimal appearance initial screen.

    Displays:
    1. Header: repository name / branch
    2. Staged summary: file count, insertions, deletions and nonzero status breakdown
    3. Staged files: up to 3 paths with status characters and optional '... +N more'
    """
    c = console or get_console(preset="minimal")
    no_color = is_no_color_active()
    w = (c._width if getattr(c, "_width", None) is not None else c.width) if c else 80

    # Gap above header
    c.print("")

    # 1. Header: repository name and current branch
    repo_name = repo_state.root.name if (repo_state.root and repo_state.root.name) else "Commit"
    if repo_state.head_commit is None and (repo_state.is_detached or not repo_state.branch):
        branch_str = "initial commit"
    elif repo_state.is_detached:
        head_short = repo_state.head_commit[:7] if repo_state.head_commit else "unknown"
        branch_str = f"Detached HEAD ({head_short})"
    elif repo_state.branch:
        branch_str = f"{repo_state.branch} branch"
    else:
        branch_str = "initial commit"

    header = Text()
    header.append("Repo: ", style="dim" if not no_color else "")
    header.append(repo_name, style="bold")
    header.append(f" ({branch_str})", style="dim" if not no_color else "")
    c.print(header)
    c.print("")

    # 2. Staged files (single column)
    c.print(Text("STAGED FILES", style="bold"))
    if diff and diff.files:
        max_display = 6
        displayed = diff.files[:max_display]
        rem = len(diff.files) - len(displayed)

        status_colors = {
            "A": "green",
            "M": "yellow",
            "D": "red",
            "R": "cyan",
            "C": "magenta",
            "T": "blue",
            "U": "red",
        }

        for f in displayed:
            status_char = f.status.value
            status_col = status_colors.get(status_char, "")
            path_str = _format_display_path(f.path)
            avail = max(20, w - 6)
            if len(path_str) > avail:
                path_str = path_str[: avail - 1] + "…"
            line = Text()
            line.append("  ")
            line.append(status_char, style=status_col if not no_color else "")
            line.append("  ")
            line.append(path_str)
            c.print(line)

        # Remaining count
        if rem > 0:
            c.print(Text(f"  ... +{rem:,} more", style="dim"))
        c.print("")

        # 3. Staged summary (below staged files)
        file_count = len(diff.files)
        file_word = "file" if file_count == 1 else "files"
        ins_count = diff.total_additions
        del_count = diff.total_deletions

        status_counts = [
            (sum(1 for f in diff.files if f.status == FileStatus.ADDED), "added", "green"),
            (sum(1 for f in diff.files if f.status == FileStatus.MODIFIED), "modified", "yellow"),
            (sum(1 for f in diff.files if f.status == FileStatus.DELETED), "deleted", "red"),
            (sum(1 for f in diff.files if f.status == FileStatus.RENAMED), "renamed", "cyan"),
            (sum(1 for f in diff.files if f.status == FileStatus.COPIED), "copied", "magenta"),
            (sum(1 for f in diff.files if f.status == FileStatus.TYPE_CHANGED), "type changed", "blue"),
            (sum(1 for f in diff.files if f.status == FileStatus.UNMERGED), "unmerged", "red"),
        ]
        non_zero = [(cnt, label, col) for cnt, label, col in status_counts if cnt > 0]

        summary_line = Text()
        summary_line.append(f"{file_count:,} {file_word} changed", style="bold")
        summary_line.append(" (", style="dim")
        summary_line.append(f"+{ins_count:,}", style="green" if not no_color else "")
        summary_line.append(", ", style="dim")
        summary_line.append(f"-{del_count:,}", style="red" if not no_color else "")
        summary_line.append(")", style="dim")

        breakdown_text = Text()
        for i, (cnt, label, col) in enumerate(non_zero):
            if i > 0:
                breakdown_text.append(", ", style="dim")
            breakdown_text.append(f"{cnt:,} {label}", style=col if not no_color else "")

        full_len = len(summary_line.plain) + len("  ·  ") + len(breakdown_text.plain)
        if full_len <= max(40, w - 4):
            summary_line.append("  ·  ", style="dim")
            summary_line.append(breakdown_text)
            c.print(summary_line)
        else:
            c.print(summary_line)
            c.print(breakdown_text)
        c.print("")
    else:
        c.print(Text("  No staged changes.", style="dim"))
        c.print("")
        c.print(Text("0 files changed (+0, -0)", style="dim"))
        c.print("")




def render_minimal_loading(
    repo_state: Optional[RepoState] = None,
    snapshot: Optional[StagedSnapshot] = None,
    loading_phase: str = "Analyzing staged changes",
    elapsed_seconds: float = 0.0,
    spinner: Optional[Spinner] = None,
) -> Group:
    """Build the compact loading display for Minimal appearance during generation."""
    sp = spinner if spinner is not None else Spinner("dots", text=Text("Generating commit message...", style="bold"))
    detail = Text(f"  {loading_phase} · {format_duration(elapsed_seconds)}", style="dim")
    return Group(sp, detail)


def build_minimal_review_renderable(
    repo_state: RepoState,
    candidate_msg: CommitMessage,
    generation_duration_seconds: Optional[float] = None,
    no_color: Optional[bool] = None,
) -> Group:
    """Build the clean commit preview Group for Minimal appearance."""
    nc = is_no_color_active() if no_color is None else no_color

    items: list[Any] = []
    items.append(Text(""))
    items.append(Text("PROPOSED COMMIT MESSAGE\n", style="bold"))

    title_line = Text()
    title_line.append("Title: ", style="dim" if not nc else "")
    title_line.append(candidate_msg.title(), style="bold" if nc else "bold cyan")
    items.append(title_line)

    if candidate_msg.body and candidate_msg.body.strip():
        body_lines = candidate_msg.body.strip().splitlines()
        if len(body_lines) == 1:
            desc_line = Text()
            desc_line.append("Description: ", style="dim" if not nc else "")
            desc_line.append(body_lines[0])
            items.append(desc_line)
        else:
            desc_line = Text()
            desc_line.append("Description: ", style="dim" if not nc else "")
            items.append(desc_line)
            for line in body_lines:
                items.append(Text(f"    {line}"))
    else:
        desc_line = Text()
        desc_line.append("Description: ", style="dim" if not nc else "")
        desc_line.append("(none)", style="dim" if not nc else "")
        items.append(desc_line)

    if candidate_msg.breaking_change and candidate_msg.breaking_change.strip():
        items.append(Text(f"Breaking Change: {candidate_msg.breaking_change.strip()}", style="bold red" if not nc else "bold"))

    items.append(Text(""))
    return Group(*items)


def render_minimal_review_screen(
    repo_state: RepoState,
    candidate_msg: CommitMessage,
    generation_duration_seconds: Optional[float] = None,
    console: Optional[Console] = None,
) -> None:
    """Render the generated commit preview and review actions in Minimal appearance."""
    c = console or get_console(preset="minimal")
    c.print(
        build_minimal_review_renderable(
            repo_state=repo_state,
            candidate_msg=candidate_msg,
            generation_duration_seconds=generation_duration_seconds,
            no_color=is_no_color_active(),
        )
    )

