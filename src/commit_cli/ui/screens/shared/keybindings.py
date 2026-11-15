"""Shared keyboard binding registration for full-screen menu and guided screens."""

from typing import Any, Callable, Optional

from prompt_toolkit.key_binding import KeyBindings

from commit_cli.ui.prompts import MainMenuChoice


def build_menu_keybindings(
    on_move: Callable[[int], None],
    on_select: Callable[[], None],
    on_shortcut: Callable[[MainMenuChoice], None],
    has_staged: bool = True,
) -> KeyBindings:
    """Build keybindings for full-screen initial menus."""
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(e: Any) -> None:
        on_move(-1)
        e.app.invalidate()

    @kb.add("down")
    @kb.add("j")
    def _down(e: Any) -> None:
        on_move(1)
        e.app.invalidate()

    @kb.add("enter")
    def _enter(e: Any) -> None:
        on_select()

    if has_staged:
        @kb.add("g")
        @kb.add("G")
        def _gen(e: Any) -> None:
            on_shortcut(MainMenuChoice.GENERATE)

    @kb.add("s")
    @kb.add("S")
    def _settings(e: Any) -> None:
        on_shortcut(MainMenuChoice.SETTINGS)

    @kb.add("q")
    @kb.add("Q")
    @kb.add("escape")
    @kb.add("c-c")
    def _quit(e: Any) -> None:
        on_shortcut(MainMenuChoice.QUIT)

    return kb


def build_guided_keybindings(
    on_cancel: Callable[[], None],
    on_enter: Callable[[], None],
    on_edit: Callable[[], None],
    on_regenerate: Callable[[], None],
    on_scroll: Callable[[int, Optional[int]], None],
) -> KeyBindings:
    """Build keybindings for full-screen guided screens."""
    kb = KeyBindings()

    # Cancel / Back
    @kb.add("escape")
    @kb.add("q")
    @kb.add("Q")
    @kb.add("c-c")
    def _cancel_gen(e: Any) -> None:
        on_cancel()

    # Enter / Commit
    @kb.add("enter")
    def _enter(e: Any) -> None:
        on_enter()

    # Edit
    @kb.add("e")
    @kb.add("E")
    def _edit(e: Any) -> None:
        on_edit()

    # Regenerate
    @kb.add("r")
    @kb.add("R")
    def _regenerate(e: Any) -> None:
        on_regenerate()

    # Scrolling
    @kb.add("up")
    @kb.add("k")
    def _scroll_up(e: Any) -> None:
        on_scroll(-1, None)

    @kb.add("down")
    @kb.add("j")
    def _scroll_down(e: Any) -> None:
        on_scroll(1, None)

    @kb.add("pageup")
    @kb.add("b")
    def _page_up(e: Any) -> None:
        on_scroll(-15, None)

    @kb.add("pagedown")
    @kb.add("space")
    @kb.add("f")
    def _page_down(e: Any) -> None:
        on_scroll(15, None)

    @kb.add("home")
    @kb.add("g")
    def _home(e: Any) -> None:
        on_scroll(0, 0)

    @kb.add("end")
    @kb.add("G")
    def _end(e: Any) -> None:
        on_scroll(0, 999999)

    return kb
