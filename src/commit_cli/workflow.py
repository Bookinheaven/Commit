"""Application workflow orchestration for Commit CLI.

Coordinates Git repository inspection, snapshot capture, generation,
rendering, interactive menus, message editing, safe commit execution,
and generation history recording.
"""

from collections.abc import Callable
from pathlib import Path
import sys
from typing import Optional

from rich.console import Console

from commit_cli.config import (
    VALID_UI_APPEARANCES,
    append_history,
    resolve_effective_config,
)
from commit_cli.diagnostics import GenerationDiagnostics
from commit_cli.exceptions import (
    GitCommandError,
    InvalidConfigurationError,
    InvalidRepositoryStateError,
    NonInteractiveTerminalError,
    NotAGitRepositoryError,
    StagedStateChangedError,
)
from commit_cli.git.commit import execute_commit
from commit_cli.git.diff import get_staged_snapshot
from commit_cli.git.repository import (
    get_custom_rules,
    get_repo_root,
    get_repo_state,
)
from commit_cli.models import (
    CLIOverrides,
    CommitConfig,
    CommitMessage,
    RepoState,
    StagedSnapshot,
)
from commit_cli.providers.ollama import OllamaProvider
from commit_cli.service import GenerationService
from commit_cli.ui.console import get_console
from commit_cli.ui.editor import edit_message_externally
from commit_cli.ui.interactive import (
    MainMenuChoice,
    check_terminal_interactive,
    prompt_commit_review,
    prompt_confirm,
    prompt_edit_method,
    prompt_main_menu,
    prompt_select,
    prompt_settings_menu,
    prompt_structured_editor,
    prompt_text,
    run_rich_guided_screen,
)
from commit_cli.ui.render import (
    StreamingRenderer,
    render_error,
    render_repo_overview,
    render_review_panel,
    render_staged_summary,
    render_success,
)
from commit_cli.workflows.commit_execution import (
    execute_commit_safe as _workflow_execute_commit_safe,
    record_history_safe as _workflow_record_history_safe,
)
from commit_cli.workflows.generation import (
    generate_candidate as _workflow_generate_candidate,
)
from commit_cli.workflows.review import (
    run_guided_review_loop as _workflow_run_guided_review_loop,
)


def _record_history_safe(
    repo_root: Path,
    message: CommitMessage,
    console: Optional[Console] = None,
) -> None:
    """Record a commit entry in history.jsonl using repository name without leaking full path."""
    _workflow_record_history_safe(
        repo_root=repo_root,
        message=message,
        console=console,
        append_history_fn=append_history,
    )


def _execute_commit_safe(
    repo_root: Path,
    candidate_msg: CommitMessage,
    snapshot: StagedSnapshot,
    console: Console,
    err_console: Console,
    preset: str,
) -> int:
    """Execute commit with fingerprint check, handle errors without tracebacks, and record history."""
    return _workflow_execute_commit_safe(
        repo_root=repo_root,
        candidate_msg=candidate_msg,
        snapshot=snapshot,
        console=console,
        err_console=err_console,
        preset=preset,
        execute_commit_fn=execute_commit,
        record_history_fn=_record_history_safe,
    )


def _generate_candidate(
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
    return _workflow_generate_candidate(
        service=service,
        snapshot=snapshot,
        console=console,
        err_console=err_console,
        preset=preset,
        stdout_mode=stdout_mode,
        dry_run_mode=dry_run_mode,
        model_name=model_name,
        user_feedback=user_feedback,
        debug_generation=debug_generation,
        repo_state=repo_state,
        cfg=cfg,
    )


def _run_guided_review_loop(
    service: GenerationService,
    snapshot: StagedSnapshot,
    candidate_msg: CommitMessage,
    repo_root: Path,
    cfg: CommitConfig,
    console: Console,
    err_console: Console,
    preset: str,
    debug_generation: bool = False,
    repo_state: Optional[RepoState] = None,
    generation_duration_seconds: Optional[float] = None,
) -> int:
    """Execute the interactive Guided review loop with editing, regeneration, and stale recovery."""
    return _workflow_run_guided_review_loop(
        service=service,
        snapshot=snapshot,
        candidate_msg=candidate_msg,
        repo_root=repo_root,
        cfg=cfg,
        console=console,
        err_console=err_console,
        preset=preset,
        debug_generation=debug_generation,
        repo_state=repo_state,
        generation_duration_seconds=generation_duration_seconds,
        execute_commit_fn=execute_commit,
        record_history_fn=_record_history_safe,
        generate_candidate_fn=_generate_candidate,
        prompt_commit_review_fn=prompt_commit_review,
        prompt_edit_method_fn=prompt_edit_method,
        prompt_structured_editor_fn=prompt_structured_editor,
        prompt_text_fn=prompt_text,
        prompt_select_fn=prompt_select,
        edit_message_externally_fn=edit_message_externally,
        get_staged_snapshot_fn=get_staged_snapshot,
    )


def run_workflow(
    overrides: Optional[CLIOverrides] = None,
    stdout_mode: bool = False,
    dry_run_mode: bool = False,
    yes_mode: bool = False,
    config_path: Optional[Path] = None,
    console: Optional[Console] = None,
    err_console: Optional[Console] = None,
    service_factory: Optional[Callable[[CommitConfig, Path], GenerationService]] = None,
) -> int:
    """Coordinate the commit generation and execution workflow.

    Returns:
        Exit code:
        0: Success or clean user cancellation
        1: Configuration error, invalid repo state, empty staging, non-interactive misuse
        2: LLM provider unavailable, model missing, or generation failure
        3: Git commit execution failure or stale snapshot
    """
    # 1. Resolve Effective Configuration
    try:
        cfg = resolve_effective_config(overrides=overrides, config_path=config_path)
    except InvalidConfigurationError as e:
        c_err = err_console or get_console(stderr=True)
        c_err.print(f"Error: {e}")
        return 1

    preset = cfg.ui.appearance
    if preset not in VALID_UI_APPEARANCES:
        c_err = err_console or get_console(stderr=True)
        c_err.print(f"Error: Invalid appearance preset '{preset}'.")
        return 1

    mode = cfg.ui.mode  # 'guided' or 'quick'
    is_non_interactive_flag = stdout_mode or dry_run_mode or yes_mode
    debug_gen = bool(overrides and overrides.debug_generation)

    # In stdout mode, output only raw message text to stdout; diagnostics go to stderr
    c_out = (err_console or get_console(stderr=True, preset=preset)) if stdout_mode else (console or get_console(preset=preset))
    c_err = err_console or get_console(stderr=True, preset=preset)

    # 2. Terminal Availability Check for Interactive Workflows
    if not is_non_interactive_flag:
        try:
            check_terminal_interactive()
        except NonInteractiveTerminalError as e:
            c_err.print(f"Error: {e}")
            c_err.print("Interactive terminal required for Guided and Quick modes.")
            c_err.print(
                "Use --yes for unattended commits, --dry-run for preview, or --stdout to output the message."
            )
            return 1

    # 3. Repository Inspection
    try:
        repo_root = get_repo_root()
    except NotAGitRepositoryError as e:
        c_err.print(f"Error: {e}")
        return 1
    except GitCommandError as e:
        c_err.print(f"Error: {e}")
        return 1

    repo_state = get_repo_state(repo_root)
    if repo_state.is_bare:
        c_err.print("Error: Cannot commit in a bare repository.")
        return 1
    if repo_state.has_unmerged_paths:
        c_err.print("Error: Cannot commit: repository has unresolved merge conflicts.")
        return 1

    # 4. Capture Staged Snapshot
    snapshot: Optional[StagedSnapshot] = None
    provider: Optional[OllamaProvider] = None
    service: Optional[GenerationService] = None

    try:
        try:
            snapshot = get_staged_snapshot(repo_root)
        except StagedStateChangedError as e:
            render_error("Staged state modified during inspection", detail=str(e), console=c_err, preset=preset)
            return 3

        if not snapshot.diff.files:
            if preset not in ("minimal", "rich") or stdout_mode or is_non_interactive_flag:
                if not stdout_mode:
                    c_err.print("No staged changes found.")
                    c_err.print("Stage changes before running commit (e.g. git add <files>).")
                else:
                    c_err.print("Error: No staged changes provided.")
                return 1

        # 5. Guided Mode: Overview & Main Menu
        if mode == "guided" and not is_non_interactive_flag:
            has_staged = bool(snapshot and snapshot.diff and snapshot.diff.files)

            while True:
                menu_choice = prompt_main_menu(
                    preset=preset,
                    has_staged=has_staged,
                    repo_state=repo_state,
                    diff=snapshot.diff if snapshot else None,
                    cfg=cfg,
                )
                if menu_choice == MainMenuChoice.GENERATE:
                    if not has_staged:
                        c_out.print("No staged changes to commit. Stage files first (git add <file>).\n")
                        continue
                    break
                elif menu_choice == MainMenuChoice.SETTINGS:
                    prompt_settings_menu(cfg, console=c_out, preset=preset, back_label="Back to menu")
                    preset = cfg.ui.appearance
                elif menu_choice == MainMenuChoice.QUIT or menu_choice is None:
                    return 0

        # 6. Lazy Service & Provider Construction
        def get_service() -> GenerationService:
            nonlocal provider, service
            if service is None:
                if service_factory is not None:
                    service = service_factory(cfg, repo_root)
                else:
                    provider = OllamaProvider(
                        base_url=cfg.ollama_url,
                        model=cfg.model,
                        connect_timeout=cfg.connect_timeout,
                        read_timeout=cfg.read_timeout,
                        timeout=cfg.timeout,
                        keep_alive=cfg.keep_alive,
                    )
                    service = GenerationService(
                        provider=provider,
                        custom_rules=get_custom_rules(repo_root) or None,
                        recent_commits=None,
                    )
                if debug_gen and getattr(service, "diagnostics", None) is None:
                    service.diagnostics = GenerationDiagnostics()
            return service

        active_service = get_service()

        # Rich Guided Workflow: unified in-place generation and review experience
        if preset == "rich" and mode == "guided" and not is_non_interactive_flag:
            action, candidate_msg, gen_duration = run_rich_guided_screen(
                service=active_service,
                snapshot=snapshot,
                repo_state=repo_state,
                cfg=cfg,
                console=c_out,
                err_console=c_err,
                return_on_generate=False,
            )
            if action == "commit" and candidate_msg is not None:
                try:
                    execute_commit(
                        root=repo_root,
                        message=candidate_msg,
                        expected_fingerprint=snapshot.fingerprint,
                    )
                    _record_history_safe(repo_root, candidate_msg, console=c_err)
                    render_success(f"Committed: {candidate_msg.title()}", console=c_out, preset="rich")
                    return 0
                except StagedStateChangedError as e:
                    render_error(
                        "Staged changes (Git index) or HEAD commit changed before commit could be executed.",
                        detail=str(e),
                        console=c_err,
                        preset="rich",
                    )
                    return 3
                except GitCommandError as e:
                    render_error("Git commit failed", detail=str(e), console=c_err, preset="rich")
                    return 3
                except InvalidRepositoryStateError as e:
                    render_error("Invalid repository state", detail=str(e), console=c_err, preset="rich")
                    return 1
            elif action == "error":
                render_error("Commit message generation failed.", console=c_err, preset="rich")
                return 2
            else:
                return 0

        candidate_msg, gen_duration = _generate_candidate(
            service=active_service,
            snapshot=snapshot,
            console=c_out,
            err_console=c_err,
            preset=preset,
            stdout_mode=stdout_mode,
            dry_run_mode=dry_run_mode,
            model_name=cfg.model,
            debug_generation=debug_gen,
            repo_state=repo_state,
            cfg=cfg,
        )
        if candidate_msg is None:
            return 2

        # 8. Non-Interactive Branch Execution
        if stdout_mode:
            sys.stdout.write(candidate_msg.format() + "\n")
            return 0

        if dry_run_mode:
            panel = render_review_panel(
                repo_state=repo_state,
                snapshot=snapshot,
                candidate_msg=candidate_msg,
                cfg=cfg,
                service=active_service,
                console=c_out,
                preset=preset,
                generation_duration_seconds=gen_duration,
            )
            c_out.print(panel)
            c_out.print("\n[dim][Dry run: commit not executed][/dim]")
            return 0

        if yes_mode:
            return _execute_commit_safe(
                repo_root=repo_root,
                candidate_msg=candidate_msg,
                snapshot=snapshot,
                console=c_out,
                err_console=c_err,
                preset=preset,
            )

        # 9. Quick Mode Execution
        if mode == "quick":
            panel = render_review_panel(
                repo_state=repo_state,
                snapshot=snapshot,
                candidate_msg=candidate_msg,
                cfg=cfg,
                service=active_service,
                console=c_out,
                preset=preset,
                generation_duration_seconds=gen_duration,
            )
            c_out.print(panel)
            confirmed = prompt_confirm(
                "Commit with this message?",
                default=False,
                preset=preset,
            )
            if not confirmed:
                c_out.print("[dim]Commit cancelled.[/dim]")
                return 0

            return _execute_commit_safe(
                repo_root=repo_root,
                candidate_msg=candidate_msg,
                snapshot=snapshot,
                console=c_out,
                err_console=c_err,
                preset=preset,
            )

        # 10. Guided Mode: Review & Editing Loop
        return _run_guided_review_loop(
            service=active_service,
            snapshot=snapshot,
            candidate_msg=candidate_msg,
            repo_root=repo_root,
            cfg=cfg,
            console=c_out,
            err_console=c_err,
            preset=preset,
            debug_generation=debug_gen,
            repo_state=repo_state,
            generation_duration_seconds=gen_duration,
        )

    finally:
        if snapshot is not None:
            snapshot.close()
        if provider is not None:
            provider.close()


__all__ = [
    "run_workflow",
    "_record_history_safe",
    "_execute_commit_safe",
    "_generate_candidate",
    "_run_guided_review_loop",
]
