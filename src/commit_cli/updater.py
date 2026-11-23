"""In-place updater for Commit CLI."""

import os
import subprocess
import sys
from pathlib import Path

from platformdirs import user_data_dir
from rich.console import Console

from commit_cli import __version__

APP_NAME = "commit-ai"
OFFICIAL_REPO_URL = "https://github.com/Bookinheaven/Commit.git"
OFFICIAL_PIP_TARGET = f"git+{OFFICIAL_REPO_URL}"


def get_app_data_dir() -> Path:
    """Return user application data directory where venv and metadata live."""
    return Path(user_data_dir(APP_NAME))


def get_recorded_source_path() -> Path | None:
    """Return recorded source directory if saved during installation."""
    marker = get_app_data_dir() / "source_path"
    if marker.is_file():
        try:
            content = marker.read_text(encoding="utf-8").strip()
            p = Path(content)
            if p.is_dir() and (p / "pyproject.toml").is_file():
                return p
        except Exception:
            pass
    return None


def discover_source_directory() -> Path | None:
    """Discover local source repository directory if available."""
    # 1. Check current working directory
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").is_file():
        try:
            txt = (cwd / "pyproject.toml").read_text(encoding="utf-8")
            if 'name = "commit-ai"' in txt:
                return cwd
        except Exception:
            pass

    # 2. Check recorded source path from installation
    recorded = get_recorded_source_path()
    if recorded is not None:
        return recorded

    # 3. Check relative to current package file (e.g., editable or source tree)
    try:
        repo_root = Path(__file__).resolve().parents[2]
        if (repo_root / "pyproject.toml").is_file():
            txt = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
            if 'name = "commit-ai"' in txt:
                return repo_root
    except Exception:
        pass

    return None


def run_update(
    check_only: bool = False,
    force: bool = False,
    console: Console | None = None,
) -> int:
    """Check for or perform an in-place upgrade of Commit."""
    c = console or Console()
    c.print("\n[bold cyan]=== Commit CLI Updater ===[/bold cyan]\n")
    c.print(f"Current version: [green]{__version__}[/green]")
    c.print(f"Python runtime:  [dim]{sys.executable}[/dim]")

    source_dir = discover_source_directory()
    pip_bin = sys.executable

    # Case 1: Updating from local Git clone
    if source_dir is not None:
        c.print(f"Source repository: [bold]{source_dir}[/bold]")
        is_git_repo = (source_dir / ".git").is_dir()

        new_commits_available = False
        if is_git_repo:
            c.print("Checking for remote Git updates...")
            try:
                # Fetch upstream with timeout
                subprocess.run(
                    ["git", "fetch", "--quiet"],
                    cwd=source_dir,
                    check=False,
                    timeout=10,
                    capture_output=True,
                )
                # Count commits behind upstream
                res = subprocess.run(
                    ["git", "rev-list", "HEAD..@{u}", "--count"],
                    cwd=source_dir,
                    check=False,
                    timeout=5,
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    behind_count = int(res.stdout.strip() or "0")
                    if behind_count > 0:
                        new_commits_available = True
                        c.print(f"[yellow]Notice:[/yellow] {behind_count} new commit(s) available on remote.")
                    else:
                        c.print("[green]Repository is up to date with remote.[/green]")
            except Exception as e:
                c.print(f"[dim]Could not check remote status: {e}[/dim]")

        if check_only:
            if new_commits_available:
                c.print("\n[bold green]An update is available![/bold green] Run [bold]commit update[/bold] to install it.")
                return 0
            else:
                c.print("\n[green]Commit is already up to date.[/green]")
                return 0

        # Pull if in git repo and not forced local-only
        if is_git_repo and new_commits_available:
            c.print("==> Pulling latest changes from remote Git repository...")
            pull_res = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=source_dir,
                check=False,
                timeout=15,
                capture_output=True,
                text=True,
            )
            if pull_res.returncode != 0:
                c.print(f"[yellow]Warning: Fast-forward pull failed ({pull_res.stderr.strip()}).[/yellow]")
                c.print("Proceeding with local files in repository.")

        c.print(f"==> Upgrading Commit in isolated environment from [bold]{source_dir}[/bold]...")
        cmd = [pip_bin, "-m", "pip", "install", "--upgrade", "--no-warn-script-location", str(source_dir)]
        if force:
            cmd.append("--force-reinstall")

        install_res = subprocess.run(cmd, check=False, text=True)
        if install_res.returncode != 0:
            c.print(f"[bold red]Error: Failed to upgrade Commit (exit code {install_res.returncode}).[/bold red]")
            return 1

    # Case 2: Updating directly from official remote Git repository
    else:
        c.print(f"Source: [bold]{OFFICIAL_REPO_URL}[/bold]")
        if check_only:
            c.print("Checking remote repository availability...")
            try:
                check_res = subprocess.run(
                    ["git", "ls-remote", "--heads", OFFICIAL_REPO_URL],
                    check=False,
                    timeout=10,
                    capture_output=True,
                    text=True,
                )
                if check_res.returncode == 0:
                    c.print("[green]Remote repository accessible.[/green]")
                else:
                    c.print("[yellow]Remote repository check failed.[/yellow]")
            except Exception as e:
                c.print(f"[dim]Remote check error: {e}[/dim]")
            c.print("Run [bold]commit update[/bold] to fetch and install the latest version.")
            return 0

        c.print(f"==> Fetching and installing latest Commit from [bold]{OFFICIAL_PIP_TARGET}[/bold]...")
        cmd = [pip_bin, "-m", "pip", "install", "--upgrade", "--no-warn-script-location", OFFICIAL_PIP_TARGET]
        if force:
            cmd.append("--force-reinstall")

        install_res = subprocess.run(cmd, check=False, text=True)
        if install_res.returncode != 0:
            c.print(f"[bold red]Error: Failed to upgrade Commit (exit code {install_res.returncode}).[/bold red]")
            return 1

    # Verify updated version
    try:
        ver_res = subprocess.run(
            [pip_bin, "-c", "from commit_cli import __version__; print(__version__)"],
            check=False,
            timeout=5,
            capture_output=True,
            text=True,
        )
        new_version = ver_res.stdout.strip() if ver_res.returncode == 0 else __version__
    except Exception:
        new_version = __version__

    c.print(f"\n[bold green]✓ Commit successfully updated![/bold green] (Active version: [bold cyan]{new_version}[/bold cyan])\n")
    return 0
