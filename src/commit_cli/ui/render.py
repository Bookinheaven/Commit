"""Domain-model driven rendering functions and streaming UI primitives for Commit.

This module acts as a backwards-compatible facade re-exporting symbols from
the modular `commit_cli.ui.renderers` package.
"""

from pathlib import Path
from typing import Any, Optional

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from commit_cli.config import (
    SUPPORTED_CONFIG_KEYS,
    get_config_file_path,
    get_config_value,
    redact_sensitive_url,
)
from commit_cli.diagnostics import GenerationDiagnostics
from commit_cli.models import (
    CommitConfig,
    CommitMessage,
    FileMetadata,
    FileStatus,
    RepoState,
    StagedDiff,
    StagedSnapshot,
)
from commit_cli.ui.console import get_console, is_no_color_active
from commit_cli.ui.renderers import (
    StreamingRenderer,
    _format_display_path,
    _status_char_and_style,
    build_minimal_review_renderable,
    clear_rendered_lines,
    format_duration,
    format_progress_phase,
    render_chunk_progress,
    render_commit_preview,
    render_config,
    render_error,
    render_generation_diagnostics,
    render_generation_status,
    render_minimal_initial_screen,
    render_minimal_loading,
    render_minimal_review_screen,
    render_provisional_output,
    render_repo_overview,
    render_review_panel,
    render_staged_summary,
    render_success,
    render_warning,
)
from commit_cli.ui.theme import get_preset_style

__all__ = [
    "render_config",
    "render_repo_overview",
    "_format_display_path",
    "_status_char_and_style",
    "render_minimal_initial_screen",
    "render_staged_summary",
    "render_commit_preview",
    "format_duration",
    "render_review_panel",
    "format_progress_phase",
    "render_minimal_loading",
    "build_minimal_review_renderable",
    "render_minimal_review_screen",
    "clear_rendered_lines",
    "render_generation_status",
    "render_provisional_output",
    "StreamingRenderer",
    "render_success",
    "render_warning",
    "render_error",
    "render_chunk_progress",
    "render_generation_diagnostics",
]
