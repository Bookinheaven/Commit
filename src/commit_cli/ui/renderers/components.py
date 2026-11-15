"""Rich visual components, panels, tables, and preview blocks for Commit CLI."""

from pathlib import Path
from typing import Any, Optional

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from commit_cli.config import (
    SUPPORTED_CONFIG_KEYS,
    get_config_file_path,
    get_config_value,
    redact_sensitive_url,
)
from commit_cli.models import (
    CommitConfig,
    CommitMessage,
    FileStatus,
    RepoState,
    StagedDiff,
    StagedSnapshot,
)
from commit_cli.ui.console import get_console, is_no_color_active
from commit_cli.ui.renderers.common import format_duration, render_provisional_output
from commit_cli.ui.theme import get_preset_style


def render_config(
    config: CommitConfig,
    origins: Optional[dict[str, str]] = None,
    console: Optional[Console] = None,
    preset: Optional[str] = None,
) -> None:
    """Render application configuration in clean tabular or diagnostic format.

    Args:
        config: Effective CommitConfig instance.
        origins: Optional mapping of config keys to their origin ('persisted', 'environment', 'default').
        console: Target Rich console (defaults to stdout console).
        preset: Appearance preset name (defaults to config.ui.appearance).
    """
    resolved_preset = preset or config.ui.appearance
    c = console or get_console(preset=resolved_preset)
    style = get_preset_style(resolved_preset)
    cfg_path = get_config_file_path()

    if origins is not None:
        # Diagnostic display with Origins column
        table = Table(
            title="Commit CLI Configuration (Origin Diagnostics)",
            box=style.box_style if style.use_panels else None,
            show_header=True,
        )
        col_setting_style = "bold cyan" if resolved_preset != "minimal" else "bold"
        col_val_style = "green" if resolved_preset != "minimal" else ""
        col_origin_style = "dim" if resolved_preset != "minimal" else ""

        table.add_column("Setting", style=col_setting_style, no_wrap=True)
        table.add_column("Value", style=col_val_style)
        table.add_column("Origin", style=col_origin_style)

        status_str = (
            "[green]Found[/green]"
            if (cfg_path.is_file() and resolved_preset != "minimal")
            else ("Found" if cfg_path.is_file() else "Defaults active")
        )
        c.print(f"[bold]Configuration File:[/bold] {cfg_path} ({status_str})\n")

        for key in sorted(SUPPORTED_CONFIG_KEYS.keys()):
            val = get_config_value(config, key)
            if key == "ollama_url" and val:
                val_display = redact_sensitive_url(str(val))
            elif key == "editor.command" and (val is None or val == ""):
                val_display = "System default"
            elif val is None or val == "":
                val_display = "(unset)"
            else:
                val_display = str(val)

            origin_display = origins.get(key, "default")
            table.add_row(key, val_display, origin_display)

        c.print(table)
        return

    # Clean, professional grouped display
    if resolved_preset == "minimal":
        c.print("\nCOMMIT CONFIGURATION\n")

        c.print("GENERATION")
        c.print(f"  {'Model':<20} {config.model}")
        c.print(f"  {'Provider':<20} {config.provider.capitalize()}")
        c.print(f"  {'Ollama URL':<20} {redact_sensitive_url(config.ollama_url)}")
        c.print()

        c.print("GENERATION LIMITS")
        timeout_sec = int(config.timeout) if config.timeout.is_integer() else config.timeout
        c.print(f"  {'Generation timeout':<20} {timeout_sec} seconds")
        conn_sec = int(config.connect_timeout) if config.connect_timeout.is_integer() else config.connect_timeout
        c.print(f"  {'Connect timeout':<20} {conn_sec} seconds")
        read_sec = int(config.read_timeout) if config.read_timeout.is_integer() else config.read_timeout
        c.print(f"  {'Read timeout':<20} {read_sec} seconds")
        c.print(f"  {'Keep alive':<20} {config.keep_alive}")
        c.print()

        c.print("INTERFACE")
        c.print(f"  {'Interaction':<20} {config.ui.mode.capitalize()}")
        c.print(f"  {'Appearance':<20} {config.ui.appearance.capitalize()}")
        c.print()

        c.print("EDITOR")
        editor_display = config.editor.command if config.editor.command else "System default"
        c.print(f"  {'Command':<20} {editor_display}")
        c.print()

        c.print("CONFIGURATION FILE")
        status = "Found" if cfg_path.is_file() else "Defaults active"
        c.print(f"  {cfg_path} ({status})\n")
        return

    # Grouped display
    c.print("\n[bold]COMMIT CONFIGURATION[/bold]\n")

    # 1. GENERATION
    c.print("[bold cyan]GENERATION[/bold cyan]")
    c.print(f"  [dim]{'Model':<20}[/dim] {config.model}")
    c.print(f"  [dim]{'Provider':<20}[/dim] {config.provider.capitalize()}")
    c.print(f"  [dim]{'Ollama URL':<20}[/dim] {redact_sensitive_url(config.ollama_url)}")
    c.print()

    # 2. GENERATION LIMITS
    c.print("[bold cyan]GENERATION LIMITS[/bold cyan]")
    timeout_sec = int(config.timeout) if config.timeout.is_integer() else config.timeout
    c.print(f"  [dim]{'Generation timeout':<20}[/dim] {timeout_sec} seconds")
    conn_sec = int(config.connect_timeout) if config.connect_timeout.is_integer() else config.connect_timeout
    c.print(f"  [dim]{'Connect timeout':<20}[/dim] {conn_sec} seconds")
    read_sec = int(config.read_timeout) if config.read_timeout.is_integer() else config.read_timeout
    c.print(f"  [dim]{'Read timeout':<20}[/dim] {read_sec} seconds")
    c.print(f"  [dim]{'Keep alive':<20}[/dim] {config.keep_alive}")
    c.print()

    # 3. INTERFACE
    c.print("[bold cyan]INTERFACE[/bold cyan]")
    c.print(f"  [dim]{'Interaction':<20}[/dim] {config.ui.mode.capitalize()}")
    c.print(f"  [dim]{'Appearance':<20}[/dim] {config.ui.appearance.capitalize()}")
    c.print()

    # 4. EDITOR
    c.print("[bold cyan]EDITOR[/bold cyan]")
    editor_display = config.editor.command if config.editor.command else "System default"
    c.print(f"  [dim]{'Command':<20}[/dim] {editor_display}")
    c.print()

    # 5. CONFIGURATION FILE
    c.print("[bold cyan]CONFIGURATION FILE[/bold cyan]")
    status_str = "[green]Found[/green]" if cfg_path.is_file() else "[dim]Defaults active[/dim]"
    c.print(f"  {cfg_path} ({status_str})\n")


def render_repo_overview(
    state: RepoState,
    diff: Optional[StagedDiff] = None,
    model: Optional[str] = None,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render a compact repository header showing repository name and branch."""
    c = console or get_console(preset=preset)

    repo_name = state.root.name if (state.root and state.root.name) else "Commit"

    if state.head_commit is None and (state.is_detached or not state.branch):
        branch_name = "initial commit"
    elif state.is_detached:
        head_short = state.head_commit[:7] if state.head_commit else "unknown"
        branch_name = f"Detached HEAD ({head_short})"
    elif state.branch:
        branch_name = state.branch
    else:
        branch_name = "initial commit"

    if diff is not None or model is not None:
        staged_desc = ""
        if diff:
            staged_count = len(diff.files)
            if staged_count == 0:
                staged_desc = "No staged files"
            elif staged_count == 1:
                staged_desc = "1 staged file"
            else:
                staged_desc = f"{staged_count} staged files"

            if diff.total_additions or diff.total_deletions:
                staged_desc += f" (+{diff.total_additions}, -{diff.total_deletions})"

        header = Text()
        header.append(repo_name, style="bold" if preset != "rich" else "bold cyan")
        header.append(f" ({branch_name})", style="dim")
        if model:
            header.append(f"  ·  {model}", style="cyan" if preset == "rich" else "dim")
        if staged_desc:
            header.append(f"  ·  {staged_desc}", style="cyan")
        c.print(Align.center(header))
    else:
        header = Text()
        if preset == "rich":
            header.append(repo_name, style="bold magenta")
            header.append(f" ({branch_name})", style="dim")
        else:
            header.append(repo_name, style="bold")
            header.append(f" ({branch_name})", style="dim")
        c.print(Align.center(header))

    warnings: list[str] = []
    if state.is_merge_in_progress:
        warnings.append("Merge in progress")
    if state.is_rebase_in_progress:
        warnings.append("Rebase in progress")
    if state.is_cherry_pick_in_progress:
        warnings.append("Cherry-pick in progress")
    if state.has_unmerged_paths:
        warnings.append("Unmerged conflict paths detected")
    if state.is_bare:
        warnings.append("Bare repository")

    for w in warnings:
        if preset == "minimal":
            c.print(f"Warning: {w}")
        else:
            c.print(f"[bold yellow]Warning:[/bold yellow] [yellow]{w}[/yellow]")




def _format_display_path(path_str: str) -> str:
    """Format file path safely for display, guaranteeing relative paths."""
    try:
        p = Path(path_str)
        if p.is_absolute():
            try:
                return str(p.relative_to(Path.cwd()))
            except ValueError:
                return str(p).lstrip("/")
        return path_str
    except Exception:
        return path_str


def _status_char_and_style(status: FileStatus, preset: str) -> tuple[str, str]:
    """Get letter and semantic style name for a FileStatus."""
    mapping = {
        FileStatus.ADDED: ("A", "status.added"),
        FileStatus.MODIFIED: ("M", "status.modified"),
        FileStatus.DELETED: ("D", "status.deleted"),
        FileStatus.RENAMED: ("R", "status.renamed"),
        FileStatus.COPIED: ("C", "status.added"),
        FileStatus.TYPE_CHANGED: ("T", "status.modified"),
        FileStatus.UNMERGED: ("U", "status.deleted"),
        FileStatus.UNTRACKED: ("?", "status.untracked"),
    }
    char, style_name = mapping.get(status, ("M", "status.modified"))
    if preset == "minimal":
        return char, ""
    return char, style_name



def render_staged_summary(
    diff: StagedDiff,
    console: Optional[Console] = None,
    preset: str = "minimal",
    max_files: Optional[int] = None,
) -> None:
    """Render a structured summary of staged files and modification counts.

    Filenames are treated as literal text and never interpreted as Rich markup.
    When max_files is provided, renders a compact summary with at most max_files preview rows.
    When max_files is None, renders the complete table of all staged files for full review.
    """
    c = console or get_console(preset=preset)
    style = get_preset_style(preset)

    if not diff.files:
        c.print("No staged changes.")
        return

    if max_files is not None:
        sep_char = "-" if (preset == "minimal" or is_no_color_active()) else "━"
        sep_style = "" if (preset == "minimal" or is_no_color_active()) else "dim"

        # 1. Top separator
        c.print()
        c.print(Rule(characters=sep_char, style=sep_style))
        c.print()

        # 2. Section Heading
        heading = Text("STAGED CHANGES")
        if preset == "rich":
            heading.stylize("bold magenta")
        else:
            heading.stylize("bold")
        c.print(heading)
        c.print()

        # 3. Primary summary: "49 files changed (+16,350 insertions, -1 deletion)"
        file_count = len(diff.files)
        file_word = "file" if file_count == 1 else "files"
        summary = Text()
        summary.append(f"{file_count:,} {file_word} changed", style="bold")

        if diff.total_additions > 0 or diff.total_deletions > 0:
            summary.append(" (")
            if diff.total_additions > 0:
                ins_word = "insertion" if diff.total_additions == 1 else "insertions"
                summary.append(
                    f"+{diff.total_additions:,} {ins_word}",
                    style="green" if preset != "minimal" else "",
                )
                if diff.total_deletions > 0:
                    summary.append(", ")
            if diff.total_deletions > 0:
                del_word = "deletion" if diff.total_deletions == 1 else "deletions"
                summary.append(
                    f"-{diff.total_deletions:,} {del_word}",
                    style="red" if preset != "minimal" else "",
                )
            summary.append(")")
        elif diff.files:
            summary.append(" (+0 insertions, -0 deletions)", style="dim" if preset != "minimal" else "")

        c.print(summary)
        c.print()

        # 4. Status breakdown: "48 added · 1 modified"
        added = sum(1 for f in diff.files if f.status == FileStatus.ADDED)
        modified = sum(1 for f in diff.files if f.status == FileStatus.MODIFIED)
        deleted = sum(1 for f in diff.files if f.status == FileStatus.DELETED)
        renamed = sum(1 for f in diff.files if f.status == FileStatus.RENAMED)
        copied = sum(1 for f in diff.files if f.status == FileStatus.COPIED)
        type_changed = sum(1 for f in diff.files if f.status == FileStatus.TYPE_CHANGED)
        unmerged = sum(1 for f in diff.files if f.status == FileStatus.UNMERGED)
        untracked = sum(1 for f in diff.files if f.status == FileStatus.UNTRACKED)

        breakdown_items: list[tuple[str, str]] = []
        if added > 0:
            breakdown_items.append((f"{added:,} added", "green"))
        if modified > 0:
            breakdown_items.append((f"{modified:,} modified", "yellow"))
        if deleted > 0:
            breakdown_items.append((f"{deleted:,} deleted", "red"))
        if renamed > 0:
            breakdown_items.append((f"{renamed:,} renamed", "cyan"))
        if copied > 0:
            breakdown_items.append((f"{copied:,} copied", "green"))
        if type_changed > 0:
            breakdown_items.append((f"{type_changed:,} type changed", "yellow"))
        if unmerged > 0:
            breakdown_items.append((f"{unmerged:,} unmerged", "red"))
        if untracked > 0:
            breakdown_items.append((f"{untracked:,} untracked", "dim"))

        breakdown = Text()
        if not breakdown_items:
            breakdown.append("no changes", style="dim" if preset != "minimal" else "")
        else:
            for i, (text_part, style_name) in enumerate(breakdown_items):
                if i > 0:
                    breakdown.append(" · ", style="dim" if preset != "minimal" else "")
                breakdown.append(text_part, style=style_name if preset != "minimal" else "")

        c.print(breakdown)
        c.print()

        # 5. Bottom separator
        c.print(Rule(characters=sep_char, style=sep_style))
        c.print()
        return

    if preset == "minimal":
        for file in diff.files:
            char, _ = _status_char_and_style(file.status, preset)
            if file.status == FileStatus.RENAMED and file.old_path:
                path_str = f"{file.old_path} -> {file.path}"
            else:
                path_str = file.path

            if file.is_binary:
                stats_str = "(binary)"
            else:
                stats_str = f"(+{file.additions}, -{file.deletions})"

            line = Text()
            line.append(f"{char}  ")
            line.append(path_str)
            line.append(f"  {stats_str}")
            c.print(line)

        summary_line = f"Total: {len(diff.files)} files (+{diff.total_additions}, -{diff.total_deletions})"
        c.print(summary_line)
        if diff.is_truncated:
            c.print(f"Warning: Diff truncated ({diff.truncated_char_count:,} of {diff.original_char_count:,} chars)")
        return

    table = Table(
        box=style.box_style if style.use_panels else None,
        show_header=True,
        pad_edge=False,
    )
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Path", overflow="ellipsis")
    table.add_column("Changes", justify="right", no_wrap=True)

    for file in diff.files:
        char, style_name = _status_char_and_style(file.status, preset)
        status_text = Text(char, style=style_name)

        if file.status == FileStatus.RENAMED and file.old_path:
            path_text = Text()
            path_text.append(file.old_path, style="muted")
            path_text.append(" -> ")
            path_text.append(file.path, style="path")
        else:
            path_text = Text(file.path, style="path")

        if file.is_binary:
            changes_text = Text("(binary)", style="status.binary")
        else:
            changes_text = Text()
            changes_text.append(f"+{file.additions} ", style="diff.addition")
            changes_text.append(f"-{file.deletions}", style="diff.deletion")

        table.add_row(status_text, path_text, changes_text)

    if preset == "rich":
        panel = Panel(
            table,
            title=f"Staged Changes ({len(diff.files)} files)",
            subtitle=f"+{diff.total_additions}, -{diff.total_deletions}",
            box=box.ROUNDED,
            border_style="cyan",
            expand=False,
        )
        c.print(panel)
    else:
        c.print(table)
        totals_text = Text()
        totals_text.append(f"Total: {len(diff.files)} files (", style="bold")
        totals_text.append(f"+{diff.total_additions}", style="diff.addition")
        totals_text.append(", ")
        totals_text.append(f"-{diff.total_deletions}", style="diff.deletion")
        totals_text.append(")", style="bold")
        c.print(totals_text)

    if diff.is_truncated:
        warn = Text(
            f"{style.icon_warning} Diff truncated for display "
            f"({diff.truncated_char_count:,} of {diff.original_char_count:,} characters shown)",
            style="warning",
        )
        c.print(warn)


def render_commit_preview(
    message: CommitMessage,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render a structured preview of a generated Conventional Commit message.

    Commit fields are treated as untrusted literal text and never interpreted as Rich markup.
    """
    c = console or get_console(preset=preset)
    style = get_preset_style(preset)

    if preset == "minimal":
        # Clean literal format
        c.print(Text(message.format()))
        return

    # Build title with semantic styling and literal content
    title_text = Text()
    title_text.append(message.type.value, style="commit.type")
    if message.scope:
        title_text.append(f"({message.scope})", style="commit.scope")
    if message.is_breaking:
        title_text.append("!", style="commit.bang")
    title_text.append(": ", style="commit.subject")
    title_text.append(message.subject, style="commit.subject")

    content_items: list[Any] = [title_text]

    if message.body and message.body.strip():
        content_items.append(Text())
        content_items.append(Text(message.body.strip(), style="commit.body"))

    if message.breaking_change and message.breaking_change.strip():
        content_items.append(Text())
        breaking_text = Text()
        breaking_text.append("BREAKING CHANGE: ", style="commit.breaking")
        breaking_text.append(message.breaking_change.strip(), style="commit.body")
        content_items.append(breaking_text)

    group = Group(*content_items)

    if preset == "rich":
        panel = Panel(
            group,
            title="Generated Commit Message",
            subtitle=f"Type: {message.type.value}",
            box=box.ROUNDED,
            border_style="cyan",
            expand=False,
        )
        c.print(panel)
    else:
        c.print(group)



def render_review_panel(
    repo_state: RepoState,
    snapshot: StagedSnapshot,
    candidate_msg: Optional[CommitMessage] = None,
    cfg: Optional[CommitConfig] = None,
    service: Optional[Any] = None,
    console: Optional[Console] = None,
    preset: str = "minimal",
    loading: bool = False,
    loading_phase: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
    generation_duration_seconds: Optional[float] = None,
) -> Panel:
    """Build the unified generation and review panel."""
    c = console or get_console(preset=preset)
    c_w = c.width if c else 80

    # 1. Panel Title: Commit (branch-name)
    if repo_state.is_detached:
        head_short = repo_state.head_commit[:7] if repo_state.head_commit else "unknown"
        branch_name = f"Detached HEAD ({head_short})"
    elif repo_state.branch:
        branch_name = repo_state.branch
    else:
        branch_name = "initial commit" if repo_state.head_commit is None else "main"

    title_str = f"Commit ({branch_name})"

    # 2. Section 1: Header (Model Identity and Generation Time)
    model_name = cfg.model if cfg else (getattr(getattr(service, "provider", None), "model_name", "qwen2.5:7b"))
    url = (cfg.ollama_url if cfg else "http://localhost:11434").lower()
    is_local = any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1"))
    loc_str = "Local" if is_local else "Remote"

    time_label: Optional[str] = None
    time_val: Optional[str] = None
    if loading:
        time_label = "Elapsed"
        time_val = format_duration(elapsed_seconds or 0.0)
    elif generation_duration_seconds is not None:
        time_label = "Generated in"
        time_val = format_duration(generation_duration_seconds)

    header_text = Text()
    inner_w = c_w - 4
    time_suffix = f"  •  {time_label}: {time_val}" if (time_label and time_val) else ""
    full_len = len(f"Model: {model_name} ({loc_str}){time_suffix}")

    time_style = "bold cyan" if (loading and preset != "minimal") else ("bold green" if preset != "minimal" else "bold")

    if full_len <= inner_w:
        header_text.append("Model: ", style="dim")
        header_text.append(model_name, style="bold" if preset != "minimal" else "")
        header_text.append(f" ({loc_str})", style="dim")
        if time_label and time_val:
            header_text.append("  •  ", style="dim")
            header_text.append(f"{time_label}: ", style="dim")
            header_text.append(time_val, style=time_style)
    elif len(f"Model: {model_name} ({loc_str}) • {time_label}: {time_val}") <= inner_w:
        header_text.append("Model: ", style="dim")
        header_text.append(model_name, style="bold" if preset != "minimal" else "")
        header_text.append(f" ({loc_str})", style="dim")
        if time_label and time_val:
            header_text.append(" • ", style="dim")
            header_text.append(f"{time_label}: ", style="dim")
            header_text.append(time_val, style=time_style)
    else:
        header_text.append(model_name, style="bold" if preset != "minimal" else "")
        header_text.append(f" ({loc_str})", style="dim")
        if time_label and time_val:
            header_text.append(" • ", style="dim")
            header_text.append(time_val, style=time_style)

    # 3. Section 2: Staged Changes
    staged_items: list[Any] = []
    staged_heading = Text("STAGED CHANGES", style="bold cyan" if preset == "rich" else "bold")
    staged_items.append(staged_heading)

    files = snapshot.diff.files
    file_count = len(files)
    file_word = "file" if file_count == 1 else "files"
    ins_count = snapshot.diff.total_additions
    ins_word = "insertion" if ins_count == 1 else "insertions"
    del_count = snapshot.diff.total_deletions
    del_word = "deletion" if del_count == 1 else "deletions"

    stats_text = Text()
    stats_text.append(f"{file_count:,} {file_word} changed", style="bold")
    stats_text.append(" · ", style="dim")
    stats_text.append(f"+{ins_count:,} {ins_word}", style="green" if preset != "minimal" else "")
    stats_text.append(" · ", style="dim")
    stats_text.append(f"-{del_count:,} {del_word}", style="red" if preset != "minimal" else "")
    staged_items.append(stats_text)

    preview_files = files[:3]
    more_count = file_count - len(preview_files)
    if more_count > 0:
        for f in preview_files:
            rel_p = _format_display_path(f.path)
            line = Text()
            line.append("├── ", style="dim")
            line.append(rel_p, style="path" if preset != "minimal" else "")
            staged_items.append(line)
        more_line = Text()
        more_line.append("└── ", style="dim")
        more_line.append(f"+{more_count:,} more files", style="dim")
        staged_items.append(more_line)
    else:
        for i, f in enumerate(preview_files):
            rel_p = _format_display_path(f.path)
            prefix = "└── " if i == len(preview_files) - 1 else "├── "
            line = Text()
            line.append(prefix, style="dim")
            line.append(rel_p, style="path" if preset != "minimal" else "")
            staged_items.append(line)

    # 4. Section 3: Generated Commit Preview / Loading State
    preview_items: list[Any] = []
    preview_heading = Text("GENERATED COMMIT PREVIEW", style="bold cyan" if preset == "rich" else "bold")
    preview_items.append(preview_heading)
    preview_items.append(Text(""))

    if loading:
        sub_phase = loading_phase or "Analyzing staged changes"
        spinner_label = f" Generating commit message...\n   {sub_phase}"
        sp = Spinner("circleHalves" if (preset != "minimal" and not is_no_color_active()) else "dots", text=spinner_label, style="cyan" if preset != "minimal" else "")
        preview_items.append(Align.center(sp))
        preview_items.append(Text(""))
    elif candidate_msg:
        subject_text = Text(candidate_msg.title(), style="bold magenta" if preset == "rich" else "bold")
        preview_items.append(subject_text)
        if candidate_msg.body and candidate_msg.body.strip():
            preview_items.append(Text(""))
            preview_items.append(Text(candidate_msg.body.strip()))
        if candidate_msg.breaking_change and candidate_msg.breaking_change.strip():
            preview_items.append(Text(""))
            bc_text = Text(f"BREAKING CHANGE: {candidate_msg.breaking_change.strip()}", style="bold red" if preset != "minimal" else "bold")
            preview_items.append(bc_text)

    # 5. Section 4: Footer Shortcuts
    footer_text = Text()
    if loading:
        footer_text.append("[Generating commit message...]", style="dim")
    else:
        key_style = "bold cyan" if preset != "minimal" else "bold"
        if c_w < 70:
            footer_text.append("[Enter]", style=key_style)
            footer_text.append(" Accept   ")
            footer_text.append("[e]", style=key_style)
            footer_text.append(" Edit   ")
            footer_text.append("[r]", style=key_style)
            footer_text.append(" Regen   ")
            footer_text.append("[d]", style=key_style)
            footer_text.append(" Diff")
        else:
            footer_text.append("[Enter]", style=key_style)
            footer_text.append(" Accept & Commit   ")
            footer_text.append("[e]", style=key_style)
            footer_text.append(" Edit   ")
            footer_text.append("[r]", style=key_style)
            footer_text.append(" Regenerate   ")
            footer_text.append("[d]", style=key_style)
            footer_text.append(" View Diff")

    sep = Rule(characters="─", style="dim")
    panel_group = Group(
        header_text,
        sep,
        Group(*staged_items),
        sep,
        Group(*preview_items),
        sep,
        footer_text,
    )

    return Panel(
        panel_group,
        title=title_str,
        box=box.ROUNDED if preset != "minimal" else box.SQUARE,
        border_style="dim" if preset != "minimal" else "none",
        padding=(0, 1),
        expand=True,
    )



class StreamingRenderer:
    """Reusable presentation primitive for streaming LLM generation."""

    def __init__(
        self,
        console: Optional[Console] = None,
        preset: str = "minimal",
    ) -> None:
        self.console = console or get_console(preset=preset)
        self.preset = preset
        self.chunks: list[str] = []
        self.is_finished: bool = False
        self.has_error: bool = False
        self.error_message: Optional[str] = None

    @property
    def text(self) -> str:
        """Accumulated text so far."""
        return "".join(self.chunks)

    def append(self, chunk: str) -> None:
        """Append a new raw chunk from the stream."""
        if chunk:
            self.chunks.append(chunk)

    def fail(self, error: str) -> None:
        """Mark stream as failed with an error."""
        self.has_error = True
        self.error_message = error
        self.is_finished = True

    def finish(self) -> None:
        """Mark stream as finished (awaiting parsing/validation)."""
        self.is_finished = True

    def render(self) -> None:
        """Render current accumulated state."""
        render_provisional_output(
            text=self.text,
            is_complete=self.is_finished,
            is_error=self.has_error,
            error_message=self.error_message,
            console=self.console,
            preset=self.preset,
        )


