"""External editor integration for commit message editing."""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

from commit_cli.exceptions import EditorError
from commit_cli.models import CommitMessage
from commit_cli.parser.commit import parse_commit_response
from commit_cli.ui.prompts import check_terminal_interactive
from commit_cli.ui.render import render_warning


def split_editor_command(raw_cmd: str, platform: Optional[str] = None) -> list[str]:
    """Parse an editor command string into arguments in a platform-aware manner without shell=True.

    Handles:
    - Executable paths containing spaces (e.g., '"C:\\Program Files\\Editor\\editor.exe" --wait')
    - Quoted arguments (e.g., 'editor --msg "hello world"')
    - Windows-style backslashes and path conventions
    - Standard Linux/Unix command invocations

    Args:
        raw_cmd: Raw command string to parse.
        platform: Target platform ('win32' or POSIX-like; defaults to sys.platform).

    Returns:
        List of command arguments suitable for subprocess.run(..., shell=False).

    Raises:
        EditorError: If the command contains malformed or unclosed quotes.
    """
    clean_cmd = raw_cmd.strip()
    if not clean_cmd:
        return []

    target_platform = platform if platform is not None else sys.platform

    if target_platform == "win32":
        try:
            tokens = shlex.split(clean_cmd, posix=False)
        except ValueError as e:
            raise EditorError(f"Malformed editor command '{clean_cmd}': {e}")

        # On Windows posix=False, quotes around quoted tokens are preserved by shlex.
        # Strip outer matching quotes so executable paths and arguments are clean strings.
        clean_tokens: list[str] = []
        for t in tokens:
            if len(t) >= 2 and ((t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'"))):
                clean_tokens.append(t[1:-1])
            else:
                clean_tokens.append(t)
        return clean_tokens

    # POSIX platforms (Linux, macOS)
    try:
        return shlex.split(clean_cmd, posix=True)
    except ValueError as e:
        raise EditorError(f"Malformed editor command '{clean_cmd}': {e}")


def get_editor_command(
    configured_command: Optional[str] = None,
    platform: Optional[str] = None,
) -> list[str]:
    """Resolve the external editor command args respecting precedence rules.

    Precedence:
    1. Explicit editor.command setting (if configured and non-empty)
    2. $VISUAL environment variable
    3. $EDITOR environment variable
    4. System fallback (nano, vim, vi on Unix; notepad on Windows)

    Returns:
        List of command arguments suitable for subprocess.run without shell=True.

    Raises:
        EditorError: If no suitable editor can be found or configured command is malformed.
    """
    raw_cmd: Optional[str] = None

    if configured_command and configured_command.strip():
        raw_cmd = configured_command.strip()
    elif os.environ.get("VISUAL", "").strip():
        raw_cmd = os.environ["VISUAL"].strip()
    elif os.environ.get("EDITOR", "").strip():
        raw_cmd = os.environ["EDITOR"].strip()

    if raw_cmd:
        parsed = split_editor_command(raw_cmd, platform=platform)
        if parsed:
            return parsed

    target_platform = platform if platform is not None else sys.platform

    # Platform default fallbacks
    if target_platform == "win32":
        return ["notepad"]

    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]

    # Final fallback if which is not available or candidates not found
    return ["nano"]


def edit_message_externally(
    message: CommitMessage,
    editor_command: Optional[str] = None,
) -> Optional[CommitMessage]:
    """Open a CommitMessage in an external editor and return the validated edited result.

    Platform Security:
    - On POSIX systems (Linux, macOS), file permissions are restricted to owner-only (0o600) via os.fchmod.
    - On Windows, secure tempfile.mkstemp creation relies on the user temporary directory's inherited NTFS ACLs;
      POSIX permission bits are not applicable on Windows.

    Rules:
    - Never uses shell=True.
    - Model-generated text is written to a temporary file, never passed as a command argument.
    - No instructional '#' comment lines are added to the template.
    - Message-body lines beginning with '#' are preserved.
    - If the user cancels (clears file) or leaves content unchanged, returns None.
    - A non-zero editor exit status raises EditorError with diagnostic information.
    - Temporary files are guaranteed to be cleaned up on success, cancellation, or failure.
    - If cleanup fails, a warning is reported and active exceptions are preserved without masking.
    - The original message is never silently overwritten on failure.

    Returns:
        The edited and validated CommitMessage, or None if cancelled or unchanged.

    Raises:
        NonInteractiveTerminalError: If terminal is non-interactive.
        EditorError: If editor cannot be found, executed, or exits with non-zero status.
        CommitValidationError: If the edited message violates Conventional Commit rules.
        CommitParseError: If the edited message cannot be parsed.
    """
    check_terminal_interactive()
    cmd = get_editor_command(editor_command)

    initial_text = message.format()
    temp_path: Optional[str] = None
    active_exc: Optional[BaseException] = None

    try:
        # 1. Secure temporary file creation with platform-appropriate access controls:
        # On POSIX (Linux/macOS), explicitly restrict file permissions to owner-only (0o600) via os.fchmod.
        # On Windows, tempfile.mkstemp() creates files in the user's private %TEMP% directory with inherited NTFS ACLs;
        # POSIX permission bits are not applicable on Windows.
        fd, temp_path = tempfile.mkstemp(prefix="commit_msg_", suffix=".gitcommit")
        try:
            if os.name == "posix" and hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(initial_text)
                f.flush()
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        # 2. Execute editor subprocess without shell=True
        exec_args = [*cmd, temp_path]
        try:
            proc = subprocess.run(exec_args, shell=False)
        except FileNotFoundError as e:
            raise EditorError(
                f"Editor executable '{cmd[0]}' not found: {e}",
                details={"command": cmd, "executable": cmd[0]},
            )
        except Exception as e:
            raise EditorError(
                f"Failed to launch editor '{cmd[0]}': {e}",
                details={"command": cmd, "error": str(e)},
            )

        # 3. Process failure check (distinguish failure from cancellation)
        if proc.returncode != 0:
            raise EditorError(
                f"Editor command '{' '.join(cmd)}' failed with exit code {proc.returncode}.",
                details={"command": cmd, "returncode": proc.returncode},
            )

        # 4. User cancellation checks
        if not os.path.exists(temp_path):
            # File was removed by the user
            return None

        with open(temp_path, "r", encoding="utf-8") as f:
            edited_text = f.read()

        # Empty content represents explicit user cancellation
        if not edited_text.strip():
            return None

        # Content unchanged represents user exiting without saving modifications
        if edited_text.strip() == initial_text.strip():
            return None

        # 5. Parse and validate the edited commit message
        return parse_commit_response(edited_text)

    except BaseException as exc:
        active_exc = exc
        raise
    finally:
        # 6. Guaranteed temporary file cleanup on success, cancellation, or failure
        if temp_path is not None:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError as cleanup_err:
                warning_msg = f"Failed to remove temporary file '{temp_path}': {cleanup_err}"
                render_warning(warning_msg)
                if active_exc is not None:
                    if hasattr(active_exc, "add_note"):
                        active_exc.add_note(warning_msg)
                    setattr(active_exc, "cleanup_error", cleanup_err)
