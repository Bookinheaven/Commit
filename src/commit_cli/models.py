"""Domain models and data structures for commit-cli."""

from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FileStatus(str, Enum):
    """Git index / working tree status of a file."""

    ADDED = "A"
    MODIFIED = "M"
    DELETED = "D"
    RENAMED = "R"
    COPIED = "C"
    TYPE_CHANGED = "T"
    UNMERGED = "U"
    UNTRACKED = "?"

    @classmethod
    def from_git_status_char(cls, char: str) -> "FileStatus":
        """Convert a Git status code character into a FileStatus enum."""
        mapping = {
            "A": cls.ADDED,
            "M": cls.MODIFIED,
            "D": cls.DELETED,
            "R": cls.RENAMED,
            "C": cls.COPIED,
            "T": cls.TYPE_CHANGED,
            "U": cls.UNMERGED,
            "?": cls.UNTRACKED,
        }
        return mapping.get(char.upper(), cls.MODIFIED)


@dataclass(frozen=True)
class FileMetadata:
    """Detailed metadata for a file in the Git index or working tree."""

    path: str
    status: FileStatus
    old_path: str | None = None
    is_binary: bool = False
    is_symlink: bool = False
    is_submodule: bool = False
    additions: int = 0
    deletions: int = 0


@dataclass(frozen=True)
class RepoState:
    """Snapshot of the repository state."""

    root: Path
    branch: str | None = None
    is_detached: bool = False
    is_bare: bool = False
    is_merge_in_progress: bool = False
    is_rebase_in_progress: bool = False
    is_cherry_pick_in_progress: bool = False
    has_unmerged_paths: bool = False
    head_commit: str | None = None


class StagedDiff:
    """Representation of staged changes ready for analysis."""

    def __init__(
        self,
        raw_diff: str = "",
        files: list[FileMetadata] | None = None,
        total_additions: int = 0,
        total_deletions: int = 0,
        is_truncated: bool = False,
        original_char_count: int = 0,
        truncated_char_count: int = 0,
        spool: Any = None,
    ) -> None:
        self._raw_diff = raw_diff
        self.files = files or []
        self.total_additions = total_additions
        self.total_deletions = total_deletions
        self.is_truncated = is_truncated
        self.original_char_count = original_char_count or len(raw_diff)
        self.truncated_char_count = truncated_char_count or len(raw_diff)
        self._spool = spool

    @property
    def spool(self) -> Any:
        return self._spool

    @property
    def raw_diff(self) -> str:
        if self._raw_diff:
            return self._raw_diff
        if self._spool is not None:
            self._spool.seek(0)
            return self._spool.read()
        return ""

    @raw_diff.setter
    def raw_diff(self, val: str) -> None:
        self._raw_diff = val

    def iter_lines(self) -> Generator[str, None, None]:
        """Stream diff line-by-line without loading entire diff into RAM."""
        if self._spool is not None:
            self._spool.seek(0)
            for line in self._spool:
                yield line
        elif self._raw_diff:
            for line in self._raw_diff.splitlines(keepends=True):
                yield line

    def close(self) -> None:
        """Close and delete underlying spooled temporary file."""
        if self._spool is not None:
            try:
                self._spool.close()
            except Exception:
                pass
            self._spool = None

    def __enter__(self) -> "StagedDiff":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, StagedDiff):
            return False
        return (
            self.raw_diff == other.raw_diff
            and self.files == other.files
            and self.total_additions == other.total_additions
            and self.total_deletions == other.total_deletions
        )

    def __repr__(self) -> str:
        return f"StagedDiff(files={len(self.files)}, chars={self.original_char_count})"


@dataclass(frozen=True)
class StagedSnapshot:
    """Consistent snapshot of staged changes and its index fingerprint."""

    diff: StagedDiff
    fingerprint: str

    def close(self) -> None:
        """Release underlying temporary storage."""
        self.diff.close()

    def __enter__(self) -> "StagedSnapshot":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


@dataclass(frozen=True)
class GitCommandResult:
    """Result of an executed Git command."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def is_success(self) -> bool:
        return self.returncode == 0


@dataclass
class UIConfig:
    """UI and interaction preferences."""

    mode: str = "guided"
    appearance: str = "minimal"


@dataclass
class EditorConfig:
    """External editor preferences."""

    command: str | None = None


@dataclass(frozen=True)
class CLIOverrides:
    """Optional runtime overrides passed via CLI options.

    Fields are None when the CLI option was omitted.
    """

    mode: str | None = None
    appearance: str | None = None
    model: str | None = None
    debug_generation: bool | None = None


@dataclass
class CommitConfig:
    """Application configuration."""

    model: str = "qwen2.5-coder:7b"
    provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    keep_alive: str = "5m"
    timeout: float = 120.0  # Overall generation deadline in seconds
    connect_timeout: float = 5.0  # Connection establishment timeout in seconds
    read_timeout: float = 60.0  # Inactivity timeout between received bytes/chunks in seconds
    ui: UIConfig = field(default_factory=UIConfig)
    editor: EditorConfig = field(default_factory=EditorConfig)


class CommitType(str, Enum):
    """Conventional Commit specification types."""

    FEAT = "feat"
    FIX = "fix"
    DOCS = "docs"
    STYLE = "style"
    REFACTOR = "refactor"
    PERF = "perf"
    TEST = "test"
    BUILD = "build"
    CI = "ci"
    CHORE = "chore"
    REVERT = "revert"


@dataclass(frozen=True)
class CommitMessage:
    """Structured representation of a Conventional Commit message."""

    type: CommitType
    subject: str
    scope: str | None = None
    body: str | None = None
    breaking_change: str | None = None

    @property
    def is_breaking(self) -> bool:
        return bool(self.breaking_change)

    def title(self) -> str:
        """Construct the standardized Conventional Commit title."""
        scope_str = f"({self.scope})" if self.scope else ""
        bang_str = "!" if self.is_breaking else ""
        return f"{self.type.value}{scope_str}{bang_str}: {self.subject}"

    def format(self) -> str:
        """Format the complete commit message including title, body, and breaking changes."""
        sections = [self.title()]
        if self.body and self.body.strip():
            sections.append(self.body.strip())
        if self.breaking_change and self.breaking_change.strip():
            sections.append(f"BREAKING CHANGE: {self.breaking_change.strip()}")
        return "\n\n".join(sections)


@dataclass(frozen=True)
class GenerationRequest:
    """Normalized input request for LLM generation."""

    prompt: str
    system_prompt: str | None = None
    response_schema: dict[str, Any] | None = None
    temperature: float = 0.1
    max_tokens: int | None = 600


@dataclass(frozen=True)
class StreamChunk:
    """A streaming token or fragment yielded during generation."""

    text: str
    is_done: bool = False
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_duration_ns: int | None = None


@dataclass(frozen=True)
class GenerationResponse:
    """Normalized final response from an LLM provider."""

    text: str
    model: str
    total_tokens: int | None = None
    prompt_tokens: int | None = None
    duration_seconds: float | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_duration_ns: int | None = None


