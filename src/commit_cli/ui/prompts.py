"""Interactive prompts, Questionary wrappers, and structured message editing for Commit."""

from enum import Enum
import sys
from typing import Any, Optional, TypeVar

import questionary
from questionary import Choice, Style

from rich.console import Console
from rich.text import Text

from commit_cli.config import save_config, set_config_value
from commit_cli.exceptions import (
    InvalidConfigurationError,
    NonInteractiveTerminalError,
)
from commit_cli.models import CommitConfig, CommitMessage, CommitType
from commit_cli.parser.commit import validate_commit_message
from commit_cli.ui.console import get_console, is_no_color_active


T = TypeVar("T")


class MainMenuChoice(str, Enum):
    """Actions available from the main interactive menu."""

    GENERATE = "generate"
    SETTINGS = "settings"
    QUIT = "quit"


class CommitReviewChoice(str, Enum):
    """Actions available after a commit message has been generated."""

    COMMIT = "commit"
    EDIT = "edit"
    REGENERATE = "regenerate"
    CANCEL = "cancel"


class EditMethodChoice(str, Enum):
    """Methods available for editing a generated commit message."""

    STRUCTURED = "structured"
    EXTERNAL = "external"
    CANCEL = "cancel"


def check_terminal_interactive() -> None:
    """Verify standard input and output support interactive prompts.

    Raises:
        NonInteractiveTerminalError: If stdin or stdout is non-interactive.
    """
    if not sys.stdin.isatty():
        raise NonInteractiveTerminalError("Standard input is not an interactive terminal.")
    if not sys.stdout.isatty():
        raise NonInteractiveTerminalError("Standard output is not an interactive terminal.")


def get_questionary_style(preset: str = "minimal") -> Style:
    """Get Questionary style definitions adhering to the centralized appearance preset."""
    if preset == "rich" and not is_no_color_active():
        return Style(
            [
                ("qmark", "fg:magenta bold"),
                ("question", "fg:magenta bold"),
                ("answer", "fg:green bold"),
                ("pointer", "fg:magenta bold"),
                ("highlighted", "noinherit noreverse fg:magenta bold"),
                ("selected", "noinherit noreverse"),
                ("separator", "fg:gray"),
                ("instruction", "fg:gray italic"),
                ("text", "nobold fg:gray"),
                ("disabled", "fg:gray italic"),
            ]
        )
    if not is_no_color_active():
        return Style(
            [
                ("qmark", "fg:cyan bold"),
                ("question", "bold"),
                ("answer", "fg:green bold"),
                ("pointer", "fg:cyan bold"),
                ("highlighted", "fg:cyan bold"),
                ("selected", "noinherit noreverse"),
                ("separator", "noinherit"),
                ("instruction", "fg:gray"),
                ("text", "nobold"),
                ("disabled", "noinherit"),
            ]
        )
    return Style(
        [
            ("qmark", "noinherit"),
            ("question", "bold"),
            ("answer", "noinherit"),
            ("pointer", "bold"),
            ("highlighted", "bold"),
            ("selected", "noinherit noreverse"),
            ("separator", "noinherit"),
            ("instruction", "noinherit"),
            ("text", "nobold"),
            ("disabled", "noinherit"),
        ]
    )


def prompt_settings_menu(
    cfg: CommitConfig,
    console: Optional[Console] = None,
    preset: str = "minimal",
    initial_key: Optional[str] = None,
    back_label: Optional[str] = None,
) -> None:
    """Interactively inspect and modify configuration settings."""
    check_terminal_interactive()
    c = console or get_console(preset=preset)
    no_color = is_no_color_active()
    is_targeted = initial_key is not None
    close_label = back_label if back_label else "Exit"

    while True:
        style = get_questionary_style(preset)
        pointer = "> " if (no_color or preset == "minimal") else "❯ "

        if initial_key is not None:
            selected = initial_key
            initial_key = None
        else:
            c.print("")
            if preset == "rich":
                c.print(Text("SETTINGS", style="bold magenta"))
            else:
                c.print(Text("SETTINGS", style="bold"))

            editor_display = cfg.editor.command if cfg.editor.command else "unset"
            choices = [
                Choice(f"Model ({cfg.model})", value="model"),
                Choice(f"Appearance ({cfg.ui.appearance})", value="ui.appearance"),
                Choice(f"Mode ({cfg.ui.mode})", value="ui.mode"),
                Choice(f"Editor ({editor_display})", value="editor.command"),
                Choice(close_label, value="exit"),
            ]

            try:
                selected = questionary.select(
                    "Select setting to configure:",
                    choices=choices,
                    style=style,
                    use_indicator=False,
                    pointer=pointer,
                ).ask()
            except (KeyboardInterrupt, EOFError):
                break

        if selected is None or selected == "exit":
            break

        if selected == "model":
            from commit_cli.providers.ollama import OllamaProvider

            models: list[str] = []
            try:
                models = OllamaProvider(base_url=cfg.ollama_url).list_local_models()
            except Exception:
                pass

            model_choices: list[Choice] = []
            if models:
                for m in models:
                    model_choices.append(Choice(f"{m} (installed)", value=m))
            else:
                model_choices.append(Choice("qwen2.5:7b (default)", value="qwen2.5:7b"))

            model_choices.append(Choice("Enter model name manually...", value="__manual__"))
            model_choices.append(Choice("Online models (Under development)", value="__online__", disabled="Coming soon"))
            model_choices.append(Choice("Cancel", value="__cancel__"))

            try:
                chosen_model = questionary.select(
                    "Select local model:",
                    choices=model_choices,
                    default=cfg.model if cfg.model in models else None,
                    style=style,
                    use_indicator=False,
                    pointer=pointer,
                ).ask()
            except (KeyboardInterrupt, EOFError):
                if is_targeted:
                    break
                continue

            if chosen_model == "__cancel__" or chosen_model is None:
                if is_targeted:
                    break
                continue
            elif chosen_model == "__manual__":
                try:
                    new_val = questionary.text(
                        "Enter Ollama model name:",
                        default=cfg.model,
                        style=style,
                    ).ask()
                except (KeyboardInterrupt, EOFError):
                    if is_targeted:
                        break
                    continue
                if new_val is None or not new_val.strip():
                    if is_targeted:
                        break
                    continue
                new_val = new_val.strip()
            else:
                new_val = chosen_model

            try:
                set_config_value(cfg, "model", new_val)
                save_config(cfg)
                c.print(f"[green]Model set to '{new_val}'[/green]")
            except InvalidConfigurationError as err:
                c.print(f"[red]Error: {err}[/red]")

        elif selected == "ui.appearance":
            appearance_choices = [
                Choice("minimal", value="minimal"),
                Choice("rich", value="rich"),
                Choice("Cancel", value="__cancel__"),
            ]
            try:
                new_val = questionary.select(
                    "Select appearance preset:",
                    choices=appearance_choices,
                    default=cfg.ui.appearance,
                    style=style,
                    use_indicator=False,
                    pointer=pointer,
                ).ask()
            except (KeyboardInterrupt, EOFError):
                if is_targeted:
                    break
                continue

            if new_val == "__cancel__" or new_val is None:
                if is_targeted:
                    break
                continue

            try:
                set_config_value(cfg, "ui.appearance", new_val)
                save_config(cfg)
                preset = new_val
                c.print(f"[green]Appearance set to '{new_val}'[/green]")
            except InvalidConfigurationError as err:
                c.print(f"[red]Error: {err}[/red]")

        elif selected == "ui.mode":
            mode_choices = [
                Choice("guided", value="guided"),
                Choice("quick", value="quick"),
                Choice("Cancel", value="__cancel__"),
            ]
            try:
                new_val = questionary.select(
                    "Select workflow mode:",
                    choices=mode_choices,
                    default=cfg.ui.mode,
                    style=style,
                    use_indicator=False,
                    pointer=pointer,
                ).ask()
            except (KeyboardInterrupt, EOFError):
                if is_targeted:
                    break
                continue

            if new_val == "__cancel__" or new_val is None:
                if is_targeted:
                    break
                continue

            try:
                set_config_value(cfg, "ui.mode", new_val)
                save_config(cfg)
                c.print(f"[green]Mode set to '{new_val}'[/green]")
            except InvalidConfigurationError as err:
                c.print(f"[red]Error: {err}[/red]")

        elif selected == "editor.command":
            current_ed = cfg.editor.command or ""
            try:
                new_val = questionary.text(
                    "Enter editor command (leave empty for system default):",
                    default=current_ed,
                    style=style,
                ).ask()
            except (KeyboardInterrupt, EOFError):
                if is_targeted:
                    break
                continue

            if new_val is None:
                if is_targeted:
                    break
                continue

            new_val = new_val.strip()
            try:
                set_config_value(cfg, "editor.command", new_val)
                save_config(cfg)
                disp = new_val if new_val else "(system default)"
                c.print(f"[green]Editor command set to '{disp}'[/green]")
            except InvalidConfigurationError as err:
                c.print(f"[red]Error: {err}[/red]")

        if is_targeted:
            break


def prompt_commit_review(
    preset: str = "minimal",
    pt_input: Optional[Any] = None,
    pt_output: Optional[Any] = None,
) -> Optional[CommitReviewChoice]:
    """Capture review action: Enter (commit), e (edit), r (regenerate), Esc/q (cancel)."""
    check_terminal_interactive()

    # Flush terminal stdin buffer to prevent stale keystrokes from auto-authorizing commits
    if pt_input is None:
        try:
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception:
            pass

    choices = [
        Choice("Commit with this message", value=CommitReviewChoice.COMMIT),
        Choice("Edit message", value=CommitReviewChoice.EDIT),
        Choice("Regenerate", value=CommitReviewChoice.REGENERATE),
        Choice("Cancel", value=CommitReviewChoice.CANCEL),
    ]

    instruction = "(Enter: commit, e: edit, r: regenerate, q: quit)"
    pointer = "> " if is_no_color_active() else "❯ "

    q_kwargs: dict[str, Any] = {
        "choices": choices,
        "style": get_questionary_style(preset),
        "use_indicator": False,
        "pointer": pointer,
        "instruction": instruction,
    }
    if pt_input is not None:
        q_kwargs["input"] = pt_input
    if pt_output is not None:
        q_kwargs["output"] = pt_output

    try:
        q = questionary.select("What would you like to do?", **q_kwargs)

        kb = q.application.key_bindings
        if kb is not None:

            @kb.add("e")
            @kb.add("E")
            def _(event: Any) -> None:
                event.app.exit(result=CommitReviewChoice.EDIT)

            @kb.add("r")
            @kb.add("R")
            def _(event: Any) -> None:
                event.app.exit(result=CommitReviewChoice.REGENERATE)

            @kb.add("q")
            @kb.add("Q")
            def _(event: Any) -> None:
                event.app.exit(result=CommitReviewChoice.CANCEL)

        return q.ask()
    except (KeyboardInterrupt, EOFError):
        return None


def prompt_edit_method(preset: str = "minimal") -> Optional[EditMethodChoice]:
    """Prompt user to choose between structured and external message editing."""
    check_terminal_interactive()
    choices = [
        Choice("Structured editor", value=EditMethodChoice.STRUCTURED),
        Choice("External editor", value=EditMethodChoice.EXTERNAL),
        Choice("Cancel", value=EditMethodChoice.CANCEL),
    ]

    try:
        res = questionary.select(
            "Choose editing method:",
            choices=choices,
            style=get_questionary_style(preset),
            use_indicator=False,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None

    return res


def prompt_confirm(message: str, default: bool = True, preset: str = "minimal") -> Optional[bool]:
    """Prompt for a binary yes/no confirmation with cancellation safety."""
    check_terminal_interactive()
    try:
        return questionary.confirm(
            message,
            default=default,
            style=get_questionary_style(preset),
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None


def prompt_select(
    message: str,
    choices: list[Any],
    default: Any = None,
    preset: str = "minimal",
) -> Any:
    """Prompt user to select from a list of choices with cancellation safety."""
    check_terminal_interactive()
    normalized_choices = [
        questionary.Choice(title=choice[0], value=choice[1])
        if isinstance(choice, tuple) and len(choice) == 2
        else choice
        for choice in choices
    ]
    try:
        return questionary.select(
            message,
            choices=normalized_choices,
            default=default,
            style=get_questionary_style(preset),
            use_indicator=True,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None


def prompt_text(
    message: str,
    default: str = "",
    multiline: bool = False,
    preset: str = "minimal",
) -> Optional[str]:
    """Prompt user for single-line or multiline text input."""
    check_terminal_interactive()
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        try:
            val = input(f"{message} ")
            return val if val.strip() else default
        except (KeyboardInterrupt, EOFError):
            return None

    try:
        res = questionary.text(
            message,
            default=default,
            multiline=multiline,
            style=get_questionary_style(preset),
        ).ask()
        return res
    except (KeyboardInterrupt, EOFError):
        return None


def prompt_structured_editor(
    message: CommitMessage,
    preset: str = "minimal",
) -> Optional[CommitMessage]:
    """Interactively edit fields of a CommitMessage and validate the result.

    Allows editing:
    - Type
    - Scope (can be edited or cleared)
    - Subject
    - Body (preserves multiline text)
    - Breaking change description

    Returns:
        A validated CommitMessage, or None if the edit was cancelled.

    Raises:
        CommitValidationError: If the edited message violates Conventional Commit rules.
    """
    check_terminal_interactive()
    style = get_questionary_style(preset)

    # 1. Type
    type_choices = [Choice(t.value, value=t.value) for t in CommitType]
    try:
        selected_type = questionary.select(
            "Commit type:",
            choices=type_choices,
            default=message.type.value,
            style=style,
            use_indicator=True,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None

    if selected_type is None:
        return None

    # 2. Scope
    scope_default = message.scope or ""
    try:
        raw_scope = questionary.text(
            "Scope (leave empty to clear):",
            default=scope_default,
            style=style,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None

    if raw_scope is None:
        return None
    new_scope = raw_scope.strip() if raw_scope.strip() else None

    # 3. Subject
    try:
        new_subject = questionary.text(
            "Subject:",
            default=message.subject,
            style=style,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None

    if new_subject is None:
        return None

    # 4. Body (multiline support)
    body_default = message.body or ""
    try:
        raw_body = questionary.text(
            "Body (optional, multiline - press Esc+Enter to submit):",
            default=body_default,
            multiline=True,
            style=style,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None

    if raw_body is None:
        return None
    new_body = raw_body.strip() if raw_body.strip() else None

    # 5. Breaking change
    bc_default = message.breaking_change or ""
    try:
        raw_bc = questionary.text(
            "Breaking change description (leave empty if none):",
            default=bc_default,
            style=style,
        ).ask()
    except (KeyboardInterrupt, EOFError):
        return None

    if raw_bc is None:
        return None
    new_bc = raw_bc.strip() if raw_bc.strip() else None

    # 6. Construct and validate candidate commit message
    candidate = CommitMessage(
        type=CommitType(selected_type),
        scope=new_scope,
        subject=new_subject.strip(),
        body=new_body,
        breaking_change=new_bc,
    )

    validate_commit_message(candidate)
    return candidate
