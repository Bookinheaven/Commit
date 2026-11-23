"""CLI entry point and command implementations for commit-cli."""

import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from commit_cli import __version__
from commit_cli.config import (
    ENV_VAR_MAP,
    SUPPORTED_CONFIG_KEYS,
    VALID_UI_APPEARANCES,
    get_config_dir,
    get_config_file_path,
    get_config_origins,
    get_config_value,
    get_history_file_path,
    get_state_dir,
    load_config,
    reset_persisted_config,
    set_persisted_config_value,
)
from commit_cli.exceptions import (
    CommitCLIError,
    InvalidConfigurationError,
    NotAGitRepositoryError,
)
from commit_cli.models import CLIOverrides, CommitConfig
from commit_cli.ui import prompt_settings_menu, render_config
from commit_cli.workflow import run_workflow
from commit_cli.git.repository import (
    get_repo_state,
    get_staged_files,
    get_unstaged_files,
    get_untracked_files,
)
from commit_cli.git.runner import run_git_captured

app = typer.Typer(
    name="commit",
    help="AI-powered Conventional Commit message generator.",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold cyan]commit-ai[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit(code=0)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    quick: bool = typer.Option(False, "--quick", "-q", help="Run quick commit workflow."),
    guided: bool = typer.Option(False, "--guided", "-g", help="Run guided commit workflow."),
    appearance: Optional[str] = typer.Option(
        None,
        "--appearance",
        "-a",
        help="Override appearance preset (minimal, rich).",
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override generation model."),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Output generated commit message to stdout without committing.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Generate and display commit message without committing.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip Commit confirmation prompts. "
            "Git pre-commit hooks and GPG signing remain active and may prompt."
        ),
    ),
    debug_generation: bool = typer.Option(
        False,
        "--debug-generation",
        help="Expose detailed generation diagnostics, context budgeting, and metrics.",
    ),
) -> None:
    """Conventional Commit generator CLI."""
    if ctx.invoked_subcommand is not None:
        return

    # Validate conflicting flags:
    # - guided and quick
    # - stdout and yes
    # - stdout and dry_run
    # - dry_run and yes
    # - guided and yes
    # - quick and yes
    if guided and quick:
        err_console.print("[bold red]Error:[/bold red] Cannot combine --guided and --quick.")
        raise typer.Exit(code=1)
    if stdout and yes:
        err_console.print("[bold red]Error:[/bold red] Cannot combine --stdout and --yes.")
        raise typer.Exit(code=1)
    if stdout and dry_run:
        err_console.print("[bold red]Error:[/bold red] Cannot combine --stdout and --dry-run.")
        raise typer.Exit(code=1)
    if dry_run and yes:
        err_console.print("[bold red]Error:[/bold red] Cannot combine --dry-run and --yes.")
        raise typer.Exit(code=1)
    if guided and yes:
        err_console.print("[bold red]Error:[/bold red] Cannot combine --guided and --yes.")
        raise typer.Exit(code=1)
    if quick and yes:
        err_console.print("[bold red]Error:[/bold red] Cannot combine --quick and --yes.")
        raise typer.Exit(code=1)

    if appearance is not None and appearance not in VALID_UI_APPEARANCES:
        err_console.print(
            f"[bold red]Error:[/bold red] Invalid appearance preset '{appearance}'. "
            f"Choose from: {', '.join(sorted(VALID_UI_APPEARANCES))}"
        )
        raise typer.Exit(code=1)

    mode = "guided" if guided else ("quick" if quick else None)
    overrides = CLIOverrides(
        mode=mode,
        appearance=appearance,
        model=model,
        debug_generation=debug_generation,
    )

    exit_code = run_workflow(
        overrides=overrides,
        stdout_mode=stdout,
        dry_run_mode=dry_run,
        yes_mode=yes,
        console=console,
        err_console=err_console,
    )
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


@app.command(name="doctor")
def doctor_command() -> None:
    """Run environment, Git, and configuration diagnostics."""
    console.print("\n[bold blue]=== Commit CLI Diagnostics (Doctor) ===[/bold blue]\n")

    # 1. Environment & Python
    py_table = Table(title="Python Environment", show_header=False, box=None)
    py_table.add_column("Property", no_wrap=True)
    py_table.add_column("Value", overflow="fold")
    py_table.add_row("[bold]Python Version:[/bold]", sys.version.split()[0])
    py_table.add_row("[bold]Python Executable:[/bold]", sys.executable)
    py_table.add_row("[bold]Package Version:[/bold]", __version__)
    console.print(py_table)
    console.print()

    # 2. Git Binary Diagnostics
    git_table = Table(title="Git Environment", show_header=False, box=None)
    try:
        git_res = run_git_captured(["--version"])
        git_version = git_res.stdout.strip()
        git_table.add_row("[bold]Git Status:[/bold]", "[green]Available[/green]")
        git_table.add_row("[bold]Git Version:[/bold]", git_version)
    except Exception as e:
        git_table.add_row("[bold]Git Status:[/bold]", f"[red]Unavailable ({e})[/red]")
    console.print(git_table)
    console.print()

    # 3. Repository Diagnostics
    repo_table = Table(title="Repository State", show_header=False, box=None)
    repo_table.add_column("Property", no_wrap=True)
    repo_table.add_column("Value", overflow="fold")
    try:
        state = get_repo_state()
        staged = get_staged_files(state.root)
        unstaged = get_unstaged_files(state.root)
        untracked = get_untracked_files(state.root)

        repo_table.add_row("[bold]Repository Root:[/bold]", str(state.root))
        branch_str = (
            f"[yellow]Detached HEAD ({state.head_commit or 'unknown'})[/yellow]"
            if state.is_detached
            else f"[green]{state.branch}[/green]"
        )
        repo_table.add_row("[bold]Current Branch:[/bold]", branch_str)
        repo_table.add_row("[bold]Bare Repository:[/bold]", str(state.is_bare))
        repo_table.add_row("[bold]Staged Files:[/bold]", f"[cyan]{len(staged)}[/cyan]")
        repo_table.add_row("[bold]Unstaged Changes:[/bold]", f"[yellow]{len(unstaged)}[/yellow]")
        repo_table.add_row("[bold]Untracked Files:[/bold]", f"[dim]{len(untracked)}[/dim]")

        if state.is_merge_in_progress:
            repo_table.add_row("[bold]Merge State:[/bold]", "[red]MERGE IN PROGRESS[/red]")
        if state.is_rebase_in_progress:
            repo_table.add_row("[bold]Rebase State:[/bold]", "[red]REBASE IN PROGRESS[/red]")
        if state.is_cherry_pick_in_progress:
            repo_table.add_row("[bold]Cherry-Pick State:[/bold]", "[red]CHERRY-PICK IN PROGRESS[/red]")
        if state.has_unmerged_paths:
            repo_table.add_row("[bold]Conflicts:[/bold]", "[red]UNMERGED PATHS DETECTED[/red]")

    except NotAGitRepositoryError:
        repo_table.add_row(
            "[bold]Repository Status:[/bold]",
            "[yellow]Not inside a Git repository (run in a git repo for repo diagnostics)[/yellow]",
        )
    except Exception as e:
        repo_table.add_row("[bold]Repository Status:[/bold]", f"[red]Error inspecting repository: {e}[/red]")

    console.print(repo_table)
    console.print()

    # 4. Configuration Paths
    cfg_table = Table(title="Configuration & State Paths", show_header=False, box=None)
    cfg_table.add_column("Property", no_wrap=True)
    cfg_table.add_column("Value", overflow="fold")
    cfg_path = get_config_file_path()
    cfg_dir = get_config_dir()
    state_dir = get_state_dir()
    history_path = get_history_file_path()

    cfg_table.add_row("[bold]Config Directory:[/bold]", str(cfg_dir))
    cfg_table.add_row(
        "[bold]Config File:[/bold]",
        f"{cfg_path} ([green]Found[/green])" if cfg_path.is_file() else f"{cfg_path} ([dim]Defaults active[/dim])",
    )
    cfg_table.add_row("[bold]State Directory:[/bold]", str(state_dir))
    cfg_table.add_row(
        "[bold]History File:[/bold]",
        f"{history_path} ([green]Found[/green])" if history_path.is_file() else f"{history_path} ([dim]Empty[/dim])",
    )

    try:
        cfg = load_config()
        cfg_table.add_row("[bold]Active Model:[/bold]", cfg.model)
        cfg_table.add_row("[bold]Active Provider:[/bold]", cfg.provider)
        cfg_table.add_row("[bold]UI Mode:[/bold]", cfg.ui.mode)
        cfg_table.add_row("[bold]UI Appearance:[/bold]", cfg.ui.appearance)
        cfg_table.add_row("[bold]Editor Command:[/bold]", cfg.editor.command or "(system default)")
    except Exception as e:
        cfg_table.add_row("[bold]Configuration Status:[/bold]", f"[red]Error loading config: {e}[/red]")

    console.print(cfg_table)
    console.print()


@app.command(name="update")
def update_command(
    check: bool = typer.Option(False, "--check", "-c", help="Check for available updates without installing."),
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstallation of dependencies."),
) -> None:
    """Check for or perform an in-place upgrade of Commit."""
    from commit_cli.updater import run_update

    code = run_update(check_only=check, force=force, console=console)
    if code != 0:
        raise typer.Exit(code=code)


def is_stdin_interactive() -> bool:
    """Check if standard input is an interactive terminal."""
    return sys.stdin.isatty()


config_app = typer.Typer(
    name="config",
    help="Inspect and modify commit-cli configuration settings.",
    add_completion=False,
)
app.add_typer(config_app, name="config")


@config_app.callback(invoke_without_command=True)
def config_callback(ctx: typer.Context) -> None:
    """Inspect and modify commit-cli configuration settings."""
    if ctx.invoked_subcommand is None:
        if is_stdin_interactive():
            try:
                cfg = load_config()
                prompt_settings_menu(cfg, console=console, preset=cfg.ui.appearance)
                raise typer.Exit(code=0)
            except (KeyboardInterrupt, EOFError):
                raise typer.Exit(code=0)
        console.print(ctx.get_help())
        raise typer.Exit(code=0)


@config_app.command(name="show")
def config_show_command(
    origins: bool = typer.Option(False, "--origins", help="Show diagnostic configuration origins."),
) -> None:
    """Display the loaded configuration settings and file path."""
    cfg_path = get_config_file_path()
    try:
        cfg = load_config()
    except InvalidConfigurationError as e:
        err_console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    origins_map = get_config_origins(cfg_path) if origins else None
    render_config(cfg, origins=origins_map, console=console, preset=cfg.ui.appearance)


@config_app.command(name="get")
def config_get_command(
    key: str = typer.Argument(..., help="Configuration key to read (e.g. ui.mode, editor.command, model)."),
) -> None:
    """Read a supported configuration key and print only its value."""
    try:
        cfg = load_config()
        val = get_config_value(cfg, key)
        if val is None:
            sys.stdout.write("\n")
        else:
            sys.stdout.write(f"{val}\n")
    except InvalidConfigurationError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@config_app.command(name="set")
def config_set_command(
    key: Optional[str] = typer.Argument(None, help="Configuration key to update (e.g. ui.mode, editor.command, model)."),
    value: Optional[str] = typer.Argument(None, help="New value for the setting (empty string clears editor.command)."),
) -> None:
    """Validate and persist a configuration setting."""
    if key is None or (value is None and is_stdin_interactive()):
        if is_stdin_interactive():
            try:
                cfg = load_config()
                prompt_settings_menu(cfg, console=console, preset=cfg.ui.appearance, initial_key=key)
                raise typer.Exit(code=0)
            except (KeyboardInterrupt, EOFError):
                raise typer.Exit(code=0)
        err_console.print(
            "[bold red]Error:[/bold red] Missing argument 'KEY'. Use 'commit config set <key> <value>' or run interactively."
        )
        raise typer.Exit(code=1)

    val_to_set = value if value is not None else ""
    try:
        parsed_val = set_persisted_config_value(key, val_to_set)
        display_val = "(cleared)" if parsed_val is None else str(parsed_val)
        console.print(f"Set [bold]{key}[/bold] = [green]{display_val}[/green]")
    except InvalidConfigurationError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


@config_app.command(name="reset")
def config_reset_command(
    key: Optional[str] = typer.Argument(None, help="Configuration key to reset (omit to reset all settings)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Bypass confirmation prompt."),
) -> None:
    """Reset one or all persisted configuration settings to built-in defaults."""
    if key is not None and key not in SUPPORTED_CONFIG_KEYS:
        err_console.print(f"[bold red]Error:[/bold red] Unknown configuration key: '{key}'")
        raise typer.Exit(code=1)

    if not yes:
        if not is_stdin_interactive():
            err_console.print(
                "[bold red]Error:[/bold red] Reset requires confirmation. "
                "In non-interactive environments, use --yes to confirm."
            )
            raise typer.Exit(code=1)

        if key is None:
            console.print("[bold]Reset Commit configuration?[/bold]\n")
            console.print("This will restore all saved settings to their built-in defaults.")
            console.print("Your generation history will not be affected.\n")
            confirmed = typer.confirm("Continue?", default=False)
        else:
            default_cfg = CommitConfig()
            default_val = get_config_value(default_cfg, key)
            default_display = "System default" if key == "editor.command" and default_val is None else str(default_val)
            confirmed = typer.confirm(f"Reset '{key}' to default ({default_display})?", default=False)

        if not confirmed:
            console.print("Reset cancelled.")
            raise typer.Exit(code=0)

    try:
        reset_persisted_config(key)
    except InvalidConfigurationError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    if key is None:
        console.print("Configuration reset to built-in defaults.")
        active_env = [
            f"{k} via {v}"
            for k, v in ENV_VAR_MAP.items()
            if v in os.environ and os.environ[v].strip()
        ]
        if active_env:
            console.print(
                f"[yellow]Note: Active environment variable(s) ({', '.join(active_env)}) "
                "will continue to take precedence.[/yellow]"
            )
    else:
        default_cfg = CommitConfig()
        default_val = get_config_value(default_cfg, key)
        default_display = "System default" if key == "editor.command" and default_val is None else str(default_val)
        console.print(
            f"Reset [bold]{key}[/bold] in configuration file (restored default: [green]{default_display}[/green])."
        )
        env_var = ENV_VAR_MAP.get(key)
        if env_var and env_var in os.environ and os.environ[env_var].strip():
            console.print(
                f"[yellow]Note: Environment variable '{env_var}' is active and will continue to take precedence.[/yellow]"
            )


def main() -> None:
    """Application main runner with safe exception handling."""
    try:
        app()
    except CommitCLIError as e:
        err_console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        err_console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
