"""Full-screen Rich appearance screen controller for Commit."""

import threading
import time
from typing import Any, Optional

from prompt_toolkit.application import Application

from commit_cli.models import CommitMessage
from commit_cli.ui.console import is_no_color_active
from commit_cli.ui.prompts import (
    MainMenuChoice,
    check_terminal_interactive,
)
from commit_cli.ui.screens.rich.interactions import (
    handle_rich_edit,
    handle_rich_regenerate,
)
from commit_cli.ui.screens.rich.layout import (
    render_rich_guided_tokens,
    render_rich_menu_tokens,
)
from commit_cli.ui.screens.shared import (
    build_guided_keybindings,
    build_menu_keybindings,
    create_fullscreen_app,
    get_terminal_size,
    safe_exit,
    safe_invalidate,
)


def _prompt_rich_menu(
    has_staged: bool = True,
    repo_state: Optional[Any] = None,
    diff: Optional[Any] = None,
    cfg: Optional[Any] = None,
    **kwargs: Any,
) -> Optional[MainMenuChoice]:
    """Render the full-screen Rich initial selection screen."""
    if has_staged:
        options = [
            ("Generate commit message", MainMenuChoice.GENERATE),
            ("Settings", MainMenuChoice.SETTINGS),
        ]
    else:
        options = [
            ("Settings", MainMenuChoice.SETTINGS),
        ]

    selected_idx = 0
    no_color = is_no_color_active()
    app: Optional[Application[Optional[MainMenuChoice]]] = None

    def timer_worker() -> None:
        while app is None or not getattr(app, "is_done", False):
            if app is not None and not no_color:
                safe_invalidate(app)
            time.sleep(0.18)

    timer_thread = threading.Thread(target=timer_worker, daemon=True)
    timer_thread.start()

    def on_move(delta: int) -> None:
        nonlocal selected_idx
        selected_idx = (selected_idx + delta) % len(options)

    def on_select() -> None:
        safe_exit(app, options[selected_idx][1])

    def on_shortcut(choice: MainMenuChoice) -> None:
        safe_exit(app, choice)

    kb = build_menu_keybindings(on_move, on_select, on_shortcut, has_staged)

    def get_tokens() -> list[tuple[str, str]]:
        w, h = get_terminal_size()
        return render_rich_menu_tokens(
            has_staged=has_staged,
            options=options,
            selected_idx=selected_idx,
            repo_state=repo_state,
            diff=diff,
            cfg=cfg,
            w=w,
            h=h,
            no_color=no_color,
        )

    pt_input = kwargs.get("pt_input")
    pt_output = kwargs.get("pt_output")
    app = create_fullscreen_app(get_tokens, kb, pt_input, pt_output)
    return app.run()


def _run_rich_guided_app_turn(
    service: Any,
    snapshot: Any,
    repo_state: Optional[Any] = None,
    cfg: Optional[Any] = None,
    initial_candidate: Optional[Any] = None,
    initial_duration: Optional[float] = None,
    pending_feedback: Optional[str] = None,
    return_on_generate: bool = False,
    pt_input: Optional[Any] = None,
    pt_output: Optional[Any] = None,
) -> tuple[str, Optional[Any], Optional[float]]:
    """Execute a single interactive turn of the full-screen Rich generation/review interface."""
    app_state = "review" if initial_candidate is not None else "generating"
    candidate_msg = initial_candidate
    gen_duration: Optional[float] = initial_duration
    is_generating = (app_state == "generating")
    start_time = time.monotonic()
    phase_desc = "Analyzing staged changes"
    cur_chunk = 0
    tot_chunks = 0
    diff_scroll_offset = 0
    review_scroll_offset = 0
    regeneration_error: Optional[str] = None
    no_color = is_no_color_active()
    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    app: Optional[Application[Any]] = None

    def start_generation_thread(feedback: Optional[str] = None) -> None:
        nonlocal is_generating, start_time, phase_desc, cur_chunk, tot_chunks, regeneration_error
        is_generating = True
        start_time = time.monotonic()
        phase_desc = "Analyzing staged changes"
        cur_chunk = 0
        tot_chunks = 0
        regeneration_error = None

        def worker() -> None:
            nonlocal is_generating, candidate_msg, gen_duration, app_state, phase_desc, cur_chunk, tot_chunks, regeneration_error
            try:
                def on_prog(cur: int, tot: int, ph: str) -> None:
                    nonlocal cur_chunk, tot_chunks, phase_desc
                    cur_chunk = cur
                    tot_chunks = tot
                    phase_desc = ph.replace("_", " ").capitalize()
                    safe_invalidate(app)

                diff = snapshot.diff if snapshot else None
                msg = service.stream_commit(
                    diff,
                    on_chunk=lambda _: None,
                    on_progress=on_prog,
                    user_feedback=feedback,
                )
                duration = time.monotonic() - start_time
                if return_on_generate:
                    if msg is not None:
                        safe_exit(app, ("review", msg, duration))
                    else:
                        safe_exit(app, ("error", None, None))
                    return

                if msg is not None:
                    candidate_msg = msg
                    gen_duration = duration
                    app_state = "review"
                else:
                    if candidate_msg is None:
                        safe_exit(app, ("error", None, None))
                        return
                    regeneration_error = "Generation returned empty message."
                    app_state = "review"
            except Exception as ex:
                if candidate_msg is None:
                    safe_exit(app, ("error", None, None))
                    return
                regeneration_error = str(ex)
                app_state = "review"
            finally:
                is_generating = False
                safe_invalidate(app)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def timer_worker() -> None:
        while app is None or not getattr(app, "is_done", False):
            if is_generating or (app_state == "review" and not no_color):
                safe_invalidate(app)
            time.sleep(0.06)

    timer_thread = threading.Thread(target=timer_worker, daemon=True)
    timer_thread.start()

    # Guided action handlers
    def on_cancel() -> None:
        safe_exit(app, ("cancel", None, None))

    def on_enter() -> None:
        if app_state == "review":
            safe_exit(app, ("commit", candidate_msg, gen_duration))

    def on_edit() -> None:
        if app_state == "review" and candidate_msg is not None:
            safe_exit(app, ("edit", candidate_msg, gen_duration))

    def on_regenerate() -> None:
        if app_state == "review":
            safe_exit(app, ("regenerate", candidate_msg, gen_duration))

    def on_scroll(delta: int, absolute: Optional[int]) -> None:
        nonlocal review_scroll_offset
        if app_state == "review":
            if absolute is not None:
                review_scroll_offset = absolute
            else:
                review_scroll_offset = max(0, review_scroll_offset + delta)
            safe_invalidate(app)

    kb = build_guided_keybindings(
        on_cancel=on_cancel,
        on_enter=on_enter,
        on_edit=on_edit,
        on_regenerate=on_regenerate,
        on_scroll=on_scroll,
    )

    def get_tokens() -> list[tuple[str, str]]:
        w, h = get_terminal_size()
        return render_rich_guided_tokens(
            app_state=app_state,
            candidate_msg=candidate_msg,
            snapshot=snapshot,
            repo_state=repo_state,
            cfg=cfg,
            is_generating=is_generating,
            start_time=start_time,
            phase_desc=phase_desc,
            cur_chunk=cur_chunk,
            tot_chunks=tot_chunks,
            diff_scroll_offset=diff_scroll_offset,
            review_scroll_offset=review_scroll_offset,
            gen_duration=gen_duration,
            regeneration_error=regeneration_error,
            spinner_frames=spinner_frames,
            w=w,
            h=h,
            no_color=no_color,
        )

    app = create_fullscreen_app(get_tokens, kb, pt_input, pt_output)

    try:
        def on_pre_run() -> None:
            if initial_candidate is None:
                start_generation_thread(pending_feedback)

        res = app.run(pre_run=on_pre_run if initial_candidate is None else None)
        if res is None:
            return ("cancel", None, None)
        return res
    except (KeyboardInterrupt, EOFError):
        return ("cancel", None, None)


def run_rich_guided_screen(
    service: Any,
    snapshot: Any,
    repo_state: Optional[Any] = None,
    cfg: Optional[Any] = None,
    initial_candidate: Optional[Any] = None,
    initial_duration: Optional[float] = None,
    console: Optional[Any] = None,
    err_console: Optional[Any] = None,
    return_on_generate: bool = False,
    pt_input: Optional[Any] = None,
    pt_output: Optional[Any] = None,
) -> tuple[str, Optional[Any], Optional[float]]:
    """Execute the full-screen Rich generation, review, and editing experience.

    Returns:
        tuple[str, Optional[CommitMessage], Optional[float]]:
            Action ('commit', 'cancel', 'error', 'review'), candidate message, and duration in seconds.
    """
    check_terminal_interactive()

    candidate_msg = initial_candidate
    gen_duration = initial_duration
    pending_feedback: Optional[str] = None

    while True:
        action, res_msg, res_dur = _run_rich_guided_app_turn(
            service=service,
            snapshot=snapshot,
            repo_state=repo_state,
            cfg=cfg,
            initial_candidate=candidate_msg,
            initial_duration=gen_duration,
            pending_feedback=pending_feedback,
            return_on_generate=return_on_generate,
            pt_input=pt_input,
            pt_output=pt_output,
        )
        pending_feedback = None

        if action == "edit":
            target_msg = res_msg if res_msg is not None else candidate_msg
            edited = handle_rich_edit(target_msg, cfg, err_console)
            if edited is not None:
                candidate_msg = edited
                gen_duration = res_dur if res_dur is not None else gen_duration
            continue

        if action == "regenerate":
            user_fb = handle_rich_regenerate()
            pending_feedback = user_fb
            candidate_msg = None
            gen_duration = None
            continue

        return action, res_msg, res_dur
