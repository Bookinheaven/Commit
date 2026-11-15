"""Minimal appearance screen controllers for Commit."""

from typing import Any, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl

from commit_cli.ui.console import is_no_color_active
from commit_cli.ui.prompts import MainMenuChoice


def _prompt_minimal_menu(
    has_staged: bool = True,
    repo_state: Optional[Any] = None,
    diff: Optional[Any] = None,
    **kwargs: Any,
) -> Optional[MainMenuChoice]:
    """Render the Minimal in-place initial selection prompt."""
    if has_staged:
        options = [
            ("Generate commit message", MainMenuChoice.GENERATE),
            ("Settings", MainMenuChoice.SETTINGS),
            ("Quit", MainMenuChoice.QUIT),
        ]
    else:
        options = [
            ("Settings", MainMenuChoice.SETTINGS),
            ("Quit", MainMenuChoice.QUIT),
        ]

    selected_idx = 0
    no_color = is_no_color_active()

    def get_text() -> list[tuple[str, str]]:
        tokens: list[tuple[str, str]] = []

        if repo_state is not None:
            repo_name = (
                repo_state.root.name
                if (repo_state.root and repo_state.root.name)
                else "Commit"
            )
            if repo_state.head_commit is None and (
                repo_state.is_detached or not repo_state.branch
            ):
                branch_str = "initial commit"
            elif repo_state.is_detached:
                head_short = (
                    repo_state.head_commit[:7]
                    if repo_state.head_commit
                    else "unknown"
                )
                branch_str = f"Detached HEAD ({head_short})"
            elif repo_state.branch:
                branch_str = f"{repo_state.branch} branch"
            else:
                branch_str = "initial commit"

            tokens.append(("", "\n"))
            tokens.append(("dim" if not no_color else "", "Repo: "))
            tokens.append(("bold", repo_name))
            tokens.append(("dim" if not no_color else "", f" ({branch_str})\n\n"))

            tokens.append(("bold", "STAGED FILES\n"))
            if diff and getattr(diff, "files", None):
                max_display = 6
                displayed = diff.files[:max_display]
                rem = len(diff.files) - len(displayed)

                status_styles = {
                    "A": "fg:green",
                    "M": "fg:yellow",
                    "D": "fg:red",
                    "R": "fg:cyan",
                    "C": "fg:magenta",
                    "T": "fg:blue",
                    "U": "fg:red",
                }

                for f in displayed:
                    s_char = getattr(getattr(f, "status", None), "value", "M")
                    col_style = status_styles.get(s_char, "") if not no_color else ""
                    p_str = getattr(f, "path", str(f))
                    tokens.append(("", "  "))
                    tokens.append((col_style, s_char))
                    tokens.append(("", f"  {p_str}\n"))

                if rem > 0:
                    tokens.append(
                        ("dim" if not no_color else "", f"  ... +{rem:,} more\n")
                    )
                tokens.append(("", "\n"))

                f_count = len(diff.files)
                f_word = "file" if f_count == 1 else "files"
                ins_count = getattr(diff, "total_additions", 0)
                del_count = getattr(diff, "total_deletions", 0)

                status_counts = [
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "A"
                        ),
                        "added",
                        "fg:green",
                    ),
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "M"
                        ),
                        "modified",
                        "fg:yellow",
                    ),
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "D"
                        ),
                        "deleted",
                        "fg:red",
                    ),
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "R"
                        ),
                        "renamed",
                        "fg:cyan",
                    ),
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "C"
                        ),
                        "copied",
                        "fg:magenta",
                    ),
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "T"
                        ),
                        "type changed",
                        "fg:blue",
                    ),
                    (
                        sum(
                            1
                            for x in diff.files
                            if getattr(getattr(x, "status", None), "value", None) == "U"
                        ),
                        "unmerged",
                        "fg:red",
                    ),
                ]
                non_zero = [(cnt, label, col) for cnt, label, col in status_counts if cnt > 0]

                tokens.append(("bold", f"{f_count:,} {f_word} changed"))
                tokens.append(("dim" if not no_color else "", " ("))
                tokens.append(("fg:green" if not no_color else "", f"+{ins_count:,}"))
                tokens.append(("dim" if not no_color else "", ", "))
                tokens.append(("fg:red" if not no_color else "", f"-{del_count:,}"))
                tokens.append(("dim" if not no_color else "", ")"))

                if non_zero:
                    tokens.append(("dim" if not no_color else "", "  ·  "))
                    for idx, (cnt, label, col) in enumerate(non_zero):
                        if idx > 0:
                            tokens.append(("dim" if not no_color else "", ", "))
                        tokens.append((col if not no_color else "", f"{cnt:,} {label}"))
                tokens.append(("", "\n\n"))
            else:
                tokens.append(("dim" if not no_color else "", "  No staged changes.\n\n"))
                tokens.append(("dim" if not no_color else "", "0 files changed (+0, -0)\n\n"))

        for i, (label, val) in enumerate(options):
            if i == selected_idx:
                pointer = "> " if no_color else "❯ "
                color_style = "bold" if no_color else "bold fg:cyan"
                tokens.append((color_style, pointer))
                tokens.append((color_style, label + "\n"))
            else:
                tokens.append(("", "  "))
                tokens.append(("", label + "\n"))
        tokens.append(("", "\n"))
        footer_style = "" if no_color else "fg:gray"
        tokens.append((footer_style, "↑/↓ Navigate   Enter Select   q Quit"))
        return tokens

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _(e: Any) -> None:
        nonlocal selected_idx
        selected_idx = (selected_idx - 1) % len(options)
        e.app.invalidate()

    @kb.add("down")
    @kb.add("j")
    def _(e: Any) -> None:
        nonlocal selected_idx
        selected_idx = (selected_idx + 1) % len(options)
        e.app.invalidate()

    @kb.add("enter")
    def _(e: Any) -> None:
        e.app.exit(result=options[selected_idx][1])

    if has_staged:

        @kb.add("g")
        @kb.add("G")
        def _(e: Any) -> None:
            e.app.exit(result=MainMenuChoice.GENERATE)

    @kb.add("s")
    @kb.add("S")
    def _(e: Any) -> None:
        e.app.exit(result=MainMenuChoice.SETTINGS)

    @kb.add("q")
    @kb.add("Q")
    @kb.add("escape")
    @kb.add("c-c")
    def _(e: Any) -> None:
        e.app.exit(result=MainMenuChoice.QUIT)

    app_kwargs: dict[str, Any] = {
        "layout": Layout(Window(FormattedTextControl(get_text, show_cursor=False), always_hide_cursor=True)),
        "key_bindings": kb,
        "erase_when_done": False,
    }
    if kwargs.get("pt_input") is not None:
        app_kwargs["input"] = kwargs["pt_input"]
    if kwargs.get("pt_output") is not None:
        app_kwargs["output"] = kwargs["pt_output"]

    app: Application[Optional[MainMenuChoice]] = Application(**app_kwargs)
    result = app.run()
    if kwargs.get("pt_output") is None:
        print("")
    return result
