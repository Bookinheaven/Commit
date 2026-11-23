"""Interactive guided review loop, message editing, regeneration, and diff viewing."""

from pathlib import Path
from typing import Callable, Optional

from rich.console import Console

from commit_cli.ui.editor import edit_message_externally
from commit_cli.exceptions import (
    CommitParseError,
    CommitValidationError,
    EditorError,
    GitCommandError,
    InvalidRepositoryStateError,
    StagedStateChangedError,
)
from commit_cli.git.repository import get_custom_rules
from commit_cli.service import GenerationService
from commit_cli.git import execute_commit, get_repo_state, get_staged_snapshot
from commit_cli.models import CommitConfig, CommitMessage, RepoState, StagedSnapshot
from commit_cli.ui import (
    CommitReviewChoice,
    EditMethodChoice,
    prompt_commit_review,
    prompt_edit_method,
    prompt_select,
    prompt_structured_editor,
    prompt_text,
    render_error,
    render_minimal_review_screen,
    render_review_panel,
    render_staged_summary,
    render_success,
    run_rich_guided_screen,
)
from commit_cli.workflows.commit_execution import record_history_safe
from commit_cli.workflows.generation import generate_candidate


def run_guided_review_loop(
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
    execute_commit_fn: Optional[Callable] = None,
    record_history_fn: Optional[Callable] = None,
    generate_candidate_fn: Optional[Callable] = None,
    prompt_commit_review_fn: Optional[Callable] = None,
    prompt_edit_method_fn: Optional[Callable] = None,
    prompt_structured_editor_fn: Optional[Callable] = None,
    prompt_text_fn: Optional[Callable] = None,
    prompt_select_fn: Optional[Callable] = None,
    edit_message_externally_fn: Optional[Callable] = None,
    get_staged_snapshot_fn: Optional[Callable] = None,
) -> int:
    """Execute the interactive Guided review loop with editing, regeneration, and stale recovery."""
    committer = execute_commit_fn or execute_commit
    recorder = record_history_fn or record_history_safe
    generator = generate_candidate_fn or generate_candidate
    prompt_review = prompt_commit_review_fn or prompt_commit_review
    prompt_edit = prompt_edit_method_fn or prompt_edit_method
    prompt_struct_ed = prompt_structured_editor_fn or prompt_structured_editor
    prompt_txt = prompt_text_fn or prompt_text
    prompt_sel = prompt_select_fn or prompt_select
    edit_ext = edit_message_externally_fn or edit_message_externally
    get_snapshot = get_staged_snapshot_fn or get_staged_snapshot

    r_state = repo_state or get_repo_state(repo_root)
    gen_duration = generation_duration_seconds
    accumulated_feedback: list[str] = []

    while True:
        if preset == "rich":
            action, res_msg, res_dur = run_rich_guided_screen(
                service=service,
                snapshot=snapshot,
                repo_state=r_state,
                cfg=cfg,
                initial_candidate=candidate_msg,
                initial_duration=gen_duration,
                console=console,
                err_console=err_console,
                return_on_generate=False,
            )
            if action == "commit" and res_msg is not None:
                try:
                    committer(
                        root=repo_root,
                        message=res_msg,
                        expected_fingerprint=snapshot.fingerprint,
                    )
                    recorder(repo_root, res_msg, console=err_console)
                    render_success(f"Committed: {res_msg.title()}", console=console, preset="rich")
                    return 0
                except StagedStateChangedError as e:
                    render_error(
                        "Staged changes (Git index) or HEAD commit changed before commit could be executed.",
                        detail=str(e),
                        console=err_console,
                        preset="rich",
                    )
                    return 3
                except GitCommandError as e:
                    render_error("Git commit failed", detail=str(e), console=err_console, preset="rich")
                    return 3
                except InvalidRepositoryStateError as e:
                    render_error("Invalid repository state", detail=str(e), console=err_console, preset="rich")
                    return 1
            else:
                return 0
        else:
            render_minimal_review_screen(
                repo_state=r_state,
                candidate_msg=candidate_msg,
                generation_duration_seconds=gen_duration,
                console=console,
            )

        review_choice = prompt_review(preset=preset)

        if review_choice == CommitReviewChoice.COMMIT:
            # Selecting 'Commit with this message' is explicit authorization.
            try:
                committer(
                    root=repo_root,
                    message=candidate_msg,
                    expected_fingerprint=snapshot.fingerprint,
                )
                recorder(repo_root, candidate_msg, console=err_console)
                render_success(f"Committed: {candidate_msg.title()}", console=console, preset=preset)
                return 0
            except StagedStateChangedError:
                render_error(
                    "Staged changes (Git index) or HEAD commit changed during review.",
                    console=err_console,
                    preset=preset,
                )
                recovery = prompt_sel(
                    "How would you like to proceed?",
                    choices=[
                        ("Refresh staged changes and regenerate", "refresh"),
                        ("Abort", "abort"),
                    ],
                    default="refresh",
                    preset=preset,
                )
                if recovery == "refresh":
                    try:
                        new_snapshot = get_snapshot(repo_root)
                    except Exception as e:
                        render_error("Failed to refresh staged snapshot", detail=str(e), console=err_console, preset=preset)
                        return 3

                    if not new_snapshot.diff.files:
                        new_snapshot.close()
                        err_console.print("No staged changes found after refresh.")
                        return 1

                    snapshot.close()
                    snapshot = new_snapshot
                    service.clear_summary_cache()
                    service._custom_rules = get_custom_rules(repo_root) or None
                    render_staged_summary(snapshot.diff, console=console, preset=preset, max_files=5)

                    new_candidate, new_duration = generator(
                        service=service,
                        snapshot=snapshot,
                        console=console,
                        err_console=err_console,
                        preset=preset,
                        stdout_mode=False,
                        model_name=cfg.model,
                        debug_generation=debug_generation,
                        repo_state=r_state,
                        cfg=cfg,
                    )
                    if new_candidate is None:
                        return 2
                    candidate_msg = new_candidate
                    gen_duration = new_duration
                    if preset == "minimal":
                        preview_rendered = True
                    continue
                else:
                    return 3
            except GitCommandError as e:
                render_error("Git commit failed", detail=str(e), console=err_console, preset=preset)
                return 3

        elif review_choice == CommitReviewChoice.EDIT:
            edit_method = prompt_edit(preset=preset)
            if edit_method == EditMethodChoice.STRUCTURED:
                try:
                    edited = prompt_struct_ed(candidate_msg, preset=preset)
                    if edited is not None:
                        candidate_msg = edited
                except CommitValidationError as e:
                    render_error("Invalid commit message edit", detail=str(e), console=err_console, preset=preset)
            elif edit_method == EditMethodChoice.EXTERNAL:
                try:
                    edited = edit_ext(candidate_msg, editor_command=cfg.editor.command)
                    if edited is not None:
                        candidate_msg = edited
                except (CommitValidationError, CommitParseError, EditorError) as e:
                    render_error("External editor error", detail=str(e), console=err_console, preset=preset)

        elif review_choice == CommitReviewChoice.REGENERATE:
            feedback = prompt_txt("Regeneration feedback / instructions (optional):", preset=preset)
            if feedback and feedback.strip():
                accumulated_feedback.append(feedback.strip())

            combined_feedback = "\n".join(f"- {f}" for f in accumulated_feedback) if accumulated_feedback else None
            new_candidate, new_duration = generator(
                service=service,
                snapshot=snapshot,
                console=console,
                err_console=err_console,
                preset=preset,
                stdout_mode=False,
                model_name=cfg.model,
                user_feedback=combined_feedback,
                debug_generation=debug_generation,
                repo_state=r_state,
                cfg=cfg,
            )
            if new_candidate is not None:
                candidate_msg = new_candidate
                gen_duration = new_duration

        elif review_choice == CommitReviewChoice.CANCEL or review_choice is None:
            return 0
