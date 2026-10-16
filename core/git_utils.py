import subprocess

def run_git(*args):
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    return result.stdout

def check_git_repo():
    """Verify that the current directory is a Git repository."""
    run_git("rev-parse", "--show-toplevel")


def get_repo_root() -> str:
    """Return the absolute path of the current Git repository root."""
    return run_git("rev-parse", "--show-toplevel").strip()


def get_staged_files() -> list[str]:
    """Return a list of files that are staged for the next commit."""
    output = run_git("diff", "--cached", "--name-only")
    return [f for f in output.splitlines() if f.strip()]

def get_staged_diff():
    return run_git(
        "diff",
        "--cached",
        "--no-ext-diff",
        "--unified=2"
    )

def commit_changes(title, description):
    run_git(
        "commit",
        "-m",
        title,
        "-m",
        description
    )
