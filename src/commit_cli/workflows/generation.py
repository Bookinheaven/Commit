"""Candidate commit message generation workflow with progress tracking and observability."""

import time
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

from commit_cli.diagnostics import GenerationDiagnostics
from commit_cli.exceptions import (
    CommitCLIError,
    CommitParseError,
    CommitValidationError,
    ProviderError,
)
from commit_cli.service import GenerationService
from commit_cli.models import CommitConfig, CommitMessage, RepoState, StagedSnapshot
from commit_cli.ui import (
    build_minimal_review_renderable,
    format_duration,
    format_progress_phase,
    render_error,
    render_generation_diagnostics,
    render_minimal_loading,
    run_rich_guided_screen,
)
from commit_cli.ui.console import is_no_color_active


def generate_candidate(
    service: GenerationService,
    snapshot: StagedSnapshot,
    console: Console,
    err_console: Console,
    preset: str,
    stdout_mode: bool,
    dry_run_mode: bool = False,
    model_name: str = "",
    user_feedback: Optional[str] = None,
    debug_generation: bool = False,
    repo_state: Optional[RepoState] = None,
    cfg: Optional[CommitConfig] = None,
) -> tuple[Optional[CommitMessage], Optional[float]]:
    """Generate a validated commit message via the generation service."""
    if getattr(service, "diagnostics", None) is None:
        service.diagnostics = GenerationDiagnostics()

    start_time = time.monotonic()
    try:
        if not stdout_mode:
            diag_console = err_console if dry_run_mode else console
            r_state = repo_state or RepoState(root=Path.cwd())
            loading_phase = "Analyzing staged changes"

            if preset == "rich":
                action, msg, duration = run_rich_guided_screen(
                    service=service,
                    snapshot=snapshot,
                    repo_state=r_state,
                    cfg=cfg,
                    console=diag_console,
                    err_console=err_console,
                    return_on_generate=True,
                )
                if action == "cancel":
                    return None, None
                return msg, duration
            else:
                sp = Spinner("dots", text=Text("Generating commit message...", style="bold"))
                final_renderable: Optional[Any] = None

                def get_loading_renderable() -> Any:
                    if final_renderable is not None:
                        return final_renderable
                    elapsed = time.monotonic() - start_time
                    return render_minimal_loading(
                        repo_state=r_state,
                        snapshot=snapshot,
                        loading_phase=loading_phase,
                        elapsed_seconds=elapsed,
                        spinner=sp,
                    )

                if diag_console.is_terminal:
                    with Live(
                        get_renderable=get_loading_renderable,
                        console=diag_console,
                        screen=False,
                        refresh_per_second=10,
                        auto_refresh=True,
                        transient=False,
                    ) as live:
                        def on_prog(cur: int, tot: int, ph: str) -> None:
                            nonlocal loading_phase
                            loading_phase = format_progress_phase(cur, tot, ph)

                        msg = service.stream_commit(
                            snapshot.diff,
                            on_chunk=lambda chunk: None,
                            on_progress=on_prog,
                            user_feedback=user_feedback,
                        )
                        duration = time.monotonic() - start_time
                        if msg is not None:
                            done_text = Text()
                            done_text.append(
                                "✔ Generated commit message",
                                style="bold green" if not is_no_color_active() else "bold",
                            )
                            done_text.append(f" in {format_duration(duration)}", style="dim")
                            final_renderable = done_text
                            live.update(done_text, refresh=True)
                        return msg, duration
                else:
                    diag_console.print("Generating commit message...")
                    msg = service.generate_commit(
                        snapshot.diff,
                        user_feedback=user_feedback,
                    )
                    duration = time.monotonic() - start_time
                    return msg, duration
        else:
            msg = service.generate_commit(
                snapshot.diff,
                user_feedback=user_feedback,
            )
            duration = time.monotonic() - start_time
            return msg, duration
    except ProviderError as e:
        render_error("Generation provider error", detail=str(e), console=err_console, preset=preset)
        return None, None
    except (CommitValidationError, CommitParseError) as e:
        render_error("Commit message validation failed", detail=str(e), console=err_console, preset=preset)
        return None, None
    except CommitCLIError as e:
        render_error("Generation failed", detail=str(e), console=err_console, preset=preset)
        return None, None
    finally:
        if debug_generation and getattr(service, "diagnostics", None) is not None:
            diag_c = err_console if stdout_mode else console
            render_generation_diagnostics(service.diagnostics, console=diag_c, preset=preset)
