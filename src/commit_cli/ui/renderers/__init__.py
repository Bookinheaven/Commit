"""Modular renderers for Commit CLI presentation."""

from commit_cli.ui.renderers.common import (
    clear_rendered_lines,
    format_duration,
    format_progress_phase,
    render_chunk_progress,
    render_error,
    render_generation_diagnostics,
    render_generation_status,
    render_provisional_output,
    render_success,
    render_warning,
)
from commit_cli.ui.renderers.components import (
    StreamingRenderer,
    _format_display_path,
    _status_char_and_style,
    render_commit_preview,
    render_config,
    render_repo_overview,
    render_review_panel,
    render_staged_summary,
)
from commit_cli.ui.renderers.minimal import (
    build_minimal_review_renderable,
    render_minimal_initial_screen,
    render_minimal_loading,
    render_minimal_review_screen,
)

__all__ = [
    # Common
    "format_duration",
    "format_progress_phase",
    "clear_rendered_lines",
    "render_generation_status",
    "render_provisional_output",
    "render_success",
    "render_warning",
    "render_error",
    "render_chunk_progress",
    "render_generation_diagnostics",
    # Components
    "_format_display_path",
    "_status_char_and_style",
    "render_config",
    "render_repo_overview",
    "render_staged_summary",
    "render_commit_preview",
    "render_review_panel",
    "StreamingRenderer",
    # Minimal
    "render_minimal_initial_screen",
    "render_minimal_loading",
    "build_minimal_review_renderable",
    "render_minimal_review_screen",
]
