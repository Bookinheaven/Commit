"""Centralized Git subprocess execution runner."""

import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from commit_cli.exceptions import (
    DiffLimitExceededError,
    GitCommandError,
    GitNotInstalledError,
    GitTimeoutError,
    NotAGitRepositoryError,
)
from commit_cli.models import GitCommandResult

DEFAULT_GIT_TIMEOUT = 15.0


def _is_not_git_repo_msg(stderr: str) -> bool:
    """Check if git error message indicates execution outside a git repo."""
    lower = stderr.lower()
    return "fatal: not a git repository" in lower or "fatal: no such ref: head" in lower


def run_git_captured(
    args: list[str],
    cwd: Path | str | None = None,
    timeout: float | None = DEFAULT_GIT_TIMEOUT,
    env_overrides: dict[str, str] | None = None,
    check: bool = True,
    max_output_chars: int | None = None,
) -> GitCommandResult:
    """Execute a Git command in Mode A (captured, read-only).

    Captures stdout/stderr and applies timeouts.
    Sets GIT_OPTIONAL_LOCKS=0 to suppress optional lock-requiring operations
    (such as automatic index refresh in git status/diff) without altering index state.
    Note: GIT_OPTIONAL_LOCKS=0 does not guarantee zero index locking for all Git commands,
    but rather suppresses optional index refresh operations during read-only queries.

    If max_output_chars is set and stdout exceeds that length, terminates the
    subprocess early and raises DiffLimitExceededError to prevent excessive memory buffering.
    """
    env = os.environ.copy()
    # Suppress optional lock-requiring operations such as git status/diff index refresh
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_overrides:
        env.update(env_overrides)

    cmd = ["git", *args]
    target_cwd = str(cwd) if cwd is not None else None

    # Bounded capture mode when max_output_chars is specified
    if max_output_chars is not None and max_output_chars > 0:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=target_cwd,
                env=env,
            )
        except FileNotFoundError as e:
            raise GitNotInstalledError() from e

        chunks: list[str] = []
        total_chars = 0
        exceeded = False
        start_time = time.monotonic()
        sel = None
        if os.name != "nt":
            try:
                import selectors

                sel = selectors.DefaultSelector()
                sel.register(proc.stdout, selectors.EVENT_READ)
            except Exception:
                sel = None

        try:
            while True:
                if timeout is not None:
                    elapsed = time.monotonic() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        proc.kill()
                        proc.wait()
                        raise GitTimeoutError(cmd, timeout)
                    if sel is not None:
                        events = sel.select(timeout=remaining)
                        if not events:
                            proc.kill()
                            proc.wait()
                            raise GitTimeoutError(cmd, timeout)

                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                total_chars += len(chunk)
                if total_chars > max_output_chars:
                    exceeded = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1.0)
                    break
        finally:
            if sel is not None:
                sel.close()

        if exceeded:
            try:
                if proc.stderr:
                    proc.stderr.read()
            except Exception:
                pass
            raise DiffLimitExceededError(char_count=total_chars, max_chars=max_output_chars)

        stdout_text = "".join(chunks)
        stderr_text = proc.stderr.read() if proc.stderr else ""
        proc.wait()
        proc_returncode = proc.returncode

        if check and proc_returncode != 0:
            if _is_not_git_repo_msg(stderr_text):
                raise NotAGitRepositoryError(str(cwd) if cwd else "")
            raise GitCommandError(
                command=cmd,
                returncode=proc_returncode,
                stdout=stdout_text,
                stderr=stderr_text,
            )

        return GitCommandResult(
            command=cmd,
            returncode=proc_returncode,
            stdout=stdout_text,
            stderr=stderr_text,
        )

    # Standard unconstrained capture mode
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=target_cwd,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as e:
        raise GitNotInstalledError() from e
    except subprocess.TimeoutExpired as e:
        raise GitTimeoutError(cmd, timeout or 0.0) from e

    result = GitCommandResult(
        command=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )

    if check and proc.returncode != 0:
        if _is_not_git_repo_msg(proc.stderr):
            raise NotAGitRepositoryError(str(cwd) if cwd else "")
        raise GitCommandError(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    return result


def run_git_to_spool(
    args: list[str],
    cwd: Path | str | None = None,
    timeout: float | None = DEFAULT_GIT_TIMEOUT,
    env_overrides: dict[str, str] | None = None,
    check: bool = True,
    max_spool_memory: int = 2 * 1024 * 1024,
) -> tuple[tempfile.SpooledTemporaryFile, int, int]:
    """Execute a Git command and stream stdout directly into a SpooledTemporaryFile.

    Binds memory usage: if output exceeds max_spool_memory (default 2MB), the
    spool automatically spills to a secure temporary file on disk.

    Returns:
        (spool_file, returncode, total_chars)
    """
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_overrides:
        env.update(env_overrides)

    cmd = ["git", *args]
    target_cwd = str(cwd) if cwd is not None else None

    spool = tempfile.SpooledTemporaryFile(
        max_size=max_spool_memory,
        mode="w+",
        encoding="utf-8",
        errors="replace",
    )
    stderr_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
    proc: subprocess.Popen[str] | None = None
    total_chars = 0

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=target_cwd,
            env=env,
        )
    except FileNotFoundError as e:
        spool.close()
        stderr_file.close()
        raise GitNotInstalledError() from e

    read_exc: Exception | None = None

    def read_stdout() -> None:
        nonlocal total_chars, read_exc
        try:
            assert proc is not None and proc.stdout is not None
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                spool.write(chunk)
                total_chars += len(chunk)
        except Exception as e:
            read_exc = e

    reader_thread = threading.Thread(target=read_stdout, daemon=True)
    reader_thread.start()

    try:
        reader_thread.join(timeout=timeout)
        if reader_thread.is_alive():
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            reader_thread.join(timeout=1.0)
            spool.close()
            stderr_file.close()
            raise GitTimeoutError(cmd, timeout or 0.0)

        if read_exc is not None:
            spool.close()
            stderr_file.close()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise read_exc

        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        proc_returncode = proc.returncode

        stderr_file.seek(0)
        stderr_text = stderr_file.read()
        stderr_file.close()

        if check and proc_returncode != 0:
            spool.close()
            if _is_not_git_repo_msg(stderr_text):
                raise NotAGitRepositoryError(str(cwd) if cwd else "")
            raise GitCommandError(
                command=cmd,
                returncode=proc_returncode,
                stdout="",
                stderr=stderr_text,
            )

        spool.seek(0)
        return spool, proc_returncode, total_chars

    except Exception:
        spool.close()
        try:
            stderr_file.close()
        except Exception:
            pass
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        raise


def run_git_captured_raw(
    args: list[str],
    cwd: Path | str | None = None,
    timeout: float | None = DEFAULT_GIT_TIMEOUT,
    env_overrides: dict[str, str] | None = None,
    check: bool = True,
) -> tuple[bytes, bytes, int]:
    """Execute a Git command in Mode A and capture un-decoded raw bytes.

    Avoids lossy UTF-8 decoding and re-encoding for cryptographic hashing.
    Applies identical environment isolation (GIT_OPTIONAL_LOCKS=0, GIT_TERMINAL_PROMPT=0)
    and timeout protections as run_git_captured.
    """
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_overrides:
        env.update(env_overrides)

    cmd = ["git", *args]
    target_cwd = str(cwd) if cwd is not None else None

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            cwd=target_cwd,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as e:
        raise GitNotInstalledError() from e
    except subprocess.TimeoutExpired as e:
        raise GitTimeoutError(cmd, timeout or 0.0) from e

    if check and proc.returncode != 0:
        stderr_str = proc.stderr.decode("utf-8", errors="replace")
        if _is_not_git_repo_msg(stderr_str):
            raise NotAGitRepositoryError(str(cwd) if cwd else "")
        raise GitCommandError(
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=stderr_str,
        )

    return proc.stdout, proc.stderr, proc.returncode


def run_git_interactive(
    args: list[str],
    cwd: Path | str | None = None,
    timeout: float | None = None,
    env_overrides: dict[str, str] | None = None,
) -> int:
    """Execute a Git command in Mode B (interactive).

    Inherits terminal streams to support GPG pinentry, commit hooks, and editor workflows.
    """
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    cmd = ["git", *args]
    target_cwd = str(cwd) if cwd is not None else None

    try:
        proc = subprocess.run(
            cmd,
            stdin=None,
            stdout=None,
            stderr=None,
            cwd=target_cwd,
            timeout=timeout,
            env=env,
        )
        return proc.returncode
    except FileNotFoundError as e:
        raise GitNotInstalledError() from e
    except subprocess.TimeoutExpired as e:
        raise GitTimeoutError(cmd, timeout or 0.0) from e

