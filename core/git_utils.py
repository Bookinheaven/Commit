import subprocess

def run_git(*args):
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip() or f"Git command failed with exit code {result.returncode}"
        raise RuntimeError(err)

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
    args = ["commit", "-m", title]
    if description and description.strip():
        args.extend(["-m", description.strip()])
    run_git(*args)


def get_unstaged_files() -> list:
    """Return files with unstaged modifications, deletions, or untracked status."""
    output = run_git("status", "--porcelain")
    unstaged = []
    for line in output.splitlines():
        if len(line) >= 3:
            # line[1] != ' ' indicates unstaged modifications/deletions, '??' is untracked
            if line[1] != " " or line.startswith("??"):
                unstaged.append(line[3:].strip())
    return unstaged


def stage_all() -> None:
    """Stage all modified, deleted, and untracked changes."""
    run_git("add", "-A")


def push_changes() -> str:
    """Push commits to current branch's remote tracking branch."""
    return run_git("push")


def get_custom_rules() -> str:
    """Read optional .commitrules or .commit-rules from repository root if present."""
    try:
        import os
        root = get_repo_root()
        for filename in (".commitrules", ".commit-rules"):
            rule_path = os.path.join(root, filename)
            if os.path.isfile(rule_path):
                with open(rule_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
    except Exception:
        pass
    return ""

