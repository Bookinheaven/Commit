"""Application setup and threadsafe event loop lifecycle helpers for Prompt Toolkit."""

from typing import Any, Callable, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl


def safe_exit(app: Optional[Application[Any]], result: Any) -> None:
    """Exit Prompt Toolkit application safely across worker threads."""
    if app is None:
        return
    try:
        loop = getattr(app, "loop", None)
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(app.exit, result=result)
        else:
            app.exit(result=result)
    except Exception:
        try:
            app.exit(result=result)
        except Exception:
            pass


def safe_invalidate(app: Optional[Application[Any]]) -> None:
    """Invalidate Prompt Toolkit UI safely across worker threads."""
    if app is None:
        return
    try:
        loop = getattr(app, "loop", None)
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(app.invalidate)
        else:
            app.invalidate()
    except Exception:
        pass


def create_fullscreen_app(
    get_tokens: Callable[[], list[tuple[str, str]]],
    key_bindings: KeyBindings,
    pt_input: Optional[Any] = None,
    pt_output: Optional[Any] = None,
) -> Application[Any]:
    """Create a standardized full-screen Prompt Toolkit Application."""
    app_kwargs: dict[str, Any] = {
        "layout": Layout(
            Window(
                FormattedTextControl(get_tokens, show_cursor=False),
                always_hide_cursor=True,
                wrap_lines=False,
            )
        ),
        "key_bindings": key_bindings,
        "full_screen": True,
    }
    if pt_input is not None:
        app_kwargs["input"] = pt_input
    if pt_output is not None:
        app_kwargs["output"] = pt_output

    return Application(**app_kwargs)
