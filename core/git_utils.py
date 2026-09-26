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
