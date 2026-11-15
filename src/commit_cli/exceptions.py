"""Custom exception hierarchy for commit-cli."""

from typing import Any


class CommitCLIError(Exception):
    """Base exception for all commit-cli errors."""

    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return self.message


class GitError(CommitCLIError):
    """Base exception for Git operations."""


class GitNotInstalledError(GitError):
    """Raised when the git executable cannot be found in PATH."""

    def __init__(self, message: str = "Git is not installed or not found in system PATH.") -> None:
        super().__init__(message)


class NotAGitRepositoryError(GitError):
    """Raised when a command is executed outside of a Git repository."""

    def __init__(self, path: str = "") -> None:
        msg = f"'{path}' is not a Git repository." if path else "Not inside a Git repository."
        super().__init__(msg, details={"path": path})


class GitCommandError(GitError):
    """Raised when a Git command returns a non-zero exit code."""

    def __init__(
        self,
        command: list[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        clean_stderr = stderr.strip()
        clean_stdout = stdout.strip()
        err_msg = clean_stderr or clean_stdout or f"Git command failed with exit code {returncode}."
        cmd_str = " ".join(command)
        super().__init__(
            f"Git command failed: {cmd_str}\n{err_msg}",
            details={
                "command": command,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class GitTimeoutError(GitError):
    """Raised when a Git command exceeds its allowed execution timeout."""

    def __init__(self, command: list[str], timeout: float) -> None:
        cmd_str = " ".join(command)
        super().__init__(
            f"Git command timed out after {timeout:.1f}s: {cmd_str}",
            details={"command": command, "timeout": timeout},
        )
        self.command = command
        self.timeout = timeout


class InvalidRepositoryStateError(GitError):
    """Raised when the repository is in an invalid state for the requested operation."""


class StagedStateChangedError(GitError):
    """Raised when staged index changes between generation snapshot and commit execution."""

    def __init__(
        self,
        expected_fingerprint: str = "",
        actual_fingerprint: str = "",
        message: str = "Staged changes were modified after generation snapshot was captured.",
    ) -> None:
        details = {
            "expected_fingerprint": expected_fingerprint,
            "actual_fingerprint": actual_fingerprint,
        }
        super().__init__(message, details=details)
        self.expected_fingerprint = expected_fingerprint
        self.actual_fingerprint = actual_fingerprint


class ConfigurationError(CommitCLIError):
    """Base exception for configuration errors."""


class InvalidConfigurationError(ConfigurationError):
    """Raised when the configuration file contains invalid syntax or values."""


class DiffLimitExceededError(CommitCLIError):
    """Raised when the staged diff exceeds the configured maximum character limit."""

    def __init__(self, char_count: int, max_chars: int) -> None:
        super().__init__(
            f"Staged diff size ({char_count:,} characters) exceeds configured limit ({max_chars:,} characters).",
            details={"char_count": char_count, "max_chars": max_chars},
        )
        self.char_count = char_count
        self.max_chars = max_chars


class ProviderError(CommitCLIError):
    """Base exception for LLM provider errors."""


class ProviderProtocolError(ProviderError):
    """Raised when an LLM provider violates expected protocol (e.g. malformed NDJSON, missing fields)."""


class IncompleteGenerationError(ProviderProtocolError):
    """Raised when streaming or generation terminates prematurely before completion."""


class ProviderUnavailableError(ProviderError):
    """Raised when the LLM provider cannot be reached."""

    def __init__(self, provider: str, url: str, reason: str = "") -> None:
        msg = f"Cannot reach {provider} at {url}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(msg, details={"provider": provider, "url": url, "reason": reason})
        self.provider = provider
        self.url = url
        self.reason = reason


class ModelNotFoundError(ProviderError):
    """Raised when the configured model is not installed on the provider."""

    def __init__(self, model: str, provider: str = "Ollama", install_command: str = "") -> None:
        cmd_hint = f" You can install it with:\n  {install_command}" if install_command else ""
        super().__init__(
            f"Model '{model}' is not installed on {provider}.{cmd_hint}",
            details={"model": model, "provider": provider, "install_command": install_command},
        )
        self.model = model
        self.provider = provider
        self.install_command = install_command


class GenerationTimeoutError(ProviderError):
    """Raised when the generation request exceeds allowed timeout."""

    def __init__(self, timeout: float, provider: str = "Ollama", reason: str = "") -> None:
        msg = f"{provider} generation timed out after {timeout:.1f}s."
        if reason:
            msg += f" ({reason})"
        super().__init__(
            msg,
            details={"timeout": timeout, "provider": provider, "reason": reason},
        )
        self.timeout = timeout
        self.provider = provider
        self.reason = reason


class CommitMessageError(CommitCLIError):
    """Base exception for commit message parsing and validation errors."""


class CommitParseError(CommitMessageError):
    """Raised when model response cannot be parsed into structured commit message."""


class CommitValidationError(CommitMessageError):
    """Raised when parsed commit message fails validation."""


class NonInteractiveTerminalError(CommitCLIError):
    """Raised when interactive input is requested in a non-interactive environment."""

    def __init__(self, message: str = "Interactive input is not available in non-interactive environments.") -> None:
        super().__init__(message)


class EditorError(CommitCLIError):
    """Raised when an external editor cannot be launched or fails."""


