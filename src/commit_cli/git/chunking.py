"""Logical diff chunking, token budgeting, and chunk summary models.

Implements model-aware chunk sizing, hierarchical boundary splitting
(file -> hunk -> line -> line fragment), and structured chunk analysis schemas.
"""

from dataclasses import dataclass, field
import json
import math
import re
from typing import Any

from commit_cli.exceptions import CommitParseError, CommitValidationError
from commit_cli.models import StagedDiff

# Conservative token estimation:
# In source code and diffs containing syntax, punctuation, indentation, and CamelCase identifiers,
# token density is higher than prose. A conservative ratio of 3.0 characters per token avoids context overflow.
CHARS_PER_TOKEN = 3.0

# Safe fallback context window when provider cannot supply model metadata
DEFAULT_FALLBACK_CONTEXT_WINDOW = 8192

# Minimum token allocation for diff input regardless of deductions
MIN_DIFF_TOKEN_BUDGET = 1000

# Maximum practical token budget for a single logical diff chunk to ensure
# local prompt evaluation completes in < 5 seconds and stays well clear of read timeouts.
MAX_CHUNK_DIFF_TOKENS = 3000

# Reserved token overhead for system prompt (~500), JSON schema (~300), expected completion (~600), and metadata (~200)
FIXED_PROMPT_OVERHEAD_TOKENS = 1600

# Safety margin fraction deducted from total context window
SAFETY_MARGIN_FRACTION = 0.20


def compute_diff_token_budget(context_window: int | None) -> int:
    """Calculate the safe token budget available for staged diff content.

    Deducts safety margins, instruction prompts, schema overhead, and response tokens.
    Dynamically scales overhead and safety margins to support small, normal, and large context windows
    without ever forcing a diff budget that exceeds total available context.
    """
    ctx = context_window or DEFAULT_FALLBACK_CONTEXT_WINDOW
    # Cap maximum context window to 32,768 tokens to prevent local VRAM/OOM exhaustion
    effective_ctx = min(ctx, 32768)

    # Scale reserved overhead for instructions, schema, and response tokens (350 - 800 tokens)
    reserved_overhead = max(350, min(800, int(effective_ctx * 0.25)))
    safety_margin = max(100, int(effective_ctx * 0.15))

    available = effective_ctx - safety_margin - reserved_overhead
    # Never force a minimum diff-token budget that exceeds available context!
    min_budget = max(100, min(available, int(effective_ctx * 0.20)))
    return max(min_budget, available)


def compute_diff_char_budget(context_window: int | None) -> int:
    """Calculate the safe character budget for a single model request diff payload."""
    token_budget = compute_diff_token_budget(context_window)
    practical_budget = min(token_budget, MAX_CHUNK_DIFF_TOKENS)
    return int(practical_budget * CHARS_PER_TOKEN)


@dataclass(frozen=True)
class DiffChunk:
    """A logical slice of staged changes sized to fit within model context."""

    chunk_index: int
    total_chunks: int
    content: str
    files: list[str]


@dataclass(frozen=True)
class FileSummary:
    """Summary of changes to an individual file."""

    path: str
    change_type: str


@dataclass(frozen=True)
class ChunkSummary:
    """Structured analysis produced for a single diff chunk."""

    files: list[FileSummary]
    functional_changes: list[str]
    implementation_details: list[str] = field(default_factory=list)
    api_changes: list[str] = field(default_factory=list)
    test_changes: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    important_context: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)


CHUNK_ANALYSIS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "change_type": {"type": "string"},
                },
                "required": ["path", "change_type"],
                "additionalProperties": False,
            },
        },
        "functional_changes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "implementation_details": {
            "type": "array",
            "items": {"type": "string"},
        },
        "api_changes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "test_changes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "breaking_changes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "important_context": {
            "type": "array",
            "items": {"type": "string"},
        },
        "uncertainties": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["files", "functional_changes"],
    "additionalProperties": False,
}


def _repair_and_extract_json(raw_text: str) -> dict[str, Any]:
    """Attempt robust extraction and repair of JSON from model output."""
    cleaned = raw_text.strip()
    if "```" in cleaned:
        start = cleaned.find("```")
        first_nl = cleaned.find("\n", start)
        end = cleaned.rfind("```")
        if first_nl != -1 and end > first_nl:
            cleaned = cleaned[first_nl + 1 : end].strip()

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")

    # 1. Try outermost braces first if they form valid JSON
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate_outer = cleaned[first_brace : last_brace + 1]
        try:
            data = json.loads(candidate_outer, strict=False)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

        # Also try with trailing commas stripped
        no_commas = re.sub(r",\s*([}\]])", r"\1", candidate_outer)
        try:
            data = json.loads(no_commas, strict=False)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. If outermost braces failed or response is truncated, take from first_brace to end
    candidate = cleaned[first_brace:] if first_brace != -1 else cleaned

    # 1. Direct parse with strict=False
    try:
        data = json.loads(candidate, strict=False)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Strip trailing commas before } and ]
    candidate_no_commas = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        data = json.loads(candidate_no_commas, strict=False)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Handle truncation: balance unclosed strings and brackets
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in candidate_no_commas:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ("{", "["):
                stack.append(ch)
            elif ch == "}":
                if stack and stack[-1] == "{":
                    stack.pop()
            elif ch == "]":
                if stack and stack[-1] == "[":
                    stack.pop()

    repaired = candidate_no_commas
    if in_string:
        repaired += '"'
    for opener in reversed(stack):
        repaired = re.sub(r",\s*$", "", repaired.rstrip())
        if opener == "{":
            repaired += "}"
        elif opener == "[":
            repaired += "]"
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    try:
        data = json.loads(repaired, strict=False)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 4. Regex fallback extraction for malformed/truncated output
    raw_files: list[dict[str, str]] = []
    for m in re.finditer(
        r'\{[^{}]*?"path"\s*:\s*"([^"]+)"[^{}]*?"change_type"\s*:\s*"([^"]+)"[^{}]*?\}',
        cleaned,
    ):
        raw_files.append({"path": m.group(1), "change_type": m.group(2)})
    if not raw_files:
        for m in re.finditer(r'"path"\s*:\s*"([^"]+)"', cleaned):
            raw_files.append({"path": m.group(1), "change_type": "modified"})

    def extract_string_list(key: str) -> list[str]:
        pattern = rf'"{key}"\s*:\s*\[(.*?)\]'
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            content = match.group(1)
            items = re.findall(r'"((?:\\.|[^"\\])+)"', content)
            return [it.strip() for it in items if it.strip()]
        pattern_trunc = rf'"{key}"\s*:\s*\[(.*)$'
        match_trunc = re.search(pattern_trunc, cleaned, re.DOTALL)
        if match_trunc:
            content = match_trunc.group(1)
            items = re.findall(r'"((?:\\.|[^"\\])+)"', content)
            return [it.strip() for it in items if it.strip()]
        return []

    functional_changes = extract_string_list("functional_changes")
    implementation_details = extract_string_list("implementation_details")
    api_changes = extract_string_list("api_changes")
    test_changes = extract_string_list("test_changes")
    breaking_changes = extract_string_list("breaking_changes")
    important_context = extract_string_list("important_context")
    uncertainties = extract_string_list("uncertainties")

    if raw_files or functional_changes or implementation_details:
        return {
            "files": raw_files,
            "functional_changes": functional_changes or ["Update staged changes in this chunk"],
            "implementation_details": implementation_details,
            "api_changes": api_changes,
            "test_changes": test_changes,
            "breaking_changes": breaking_changes,
            "important_context": important_context,
            "uncertainties": uncertainties,
        }

    # If all parsing and recovery attempts fail, raise informative CommitParseError
    try:
        json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise CommitParseError(f"Malformed JSON in chunk analysis: {e}") from e
    raise CommitParseError("Expected JSON object for chunk analysis")


def parse_chunk_summary(raw_text: str) -> ChunkSummary:
    """Parse and validate raw model output into a ChunkSummary object."""
    data = _repair_and_extract_json(raw_text)

    if not isinstance(data, dict):
        raise CommitParseError(f"Expected JSON object for chunk analysis, got {type(data).__name__}")

    raw_files = data.get("files", [])
    if not isinstance(raw_files, list):
        raise CommitValidationError("'files' must be an array of file change objects.")

    file_summaries: list[FileSummary] = []
    for f in raw_files:
        if isinstance(f, dict) and "path" in f:
            file_summaries.append(
                FileSummary(
                    path=str(f["path"]),
                    change_type=str(f.get("change_type", "modified")),
                )
            )

    func_changes = data.get("functional_changes", [])
    if not isinstance(func_changes, list):
        raise CommitValidationError("'functional_changes' must be an array of strings.")

    return ChunkSummary(
        files=file_summaries,
        functional_changes=[str(item) for item in func_changes if str(item).strip()],
        implementation_details=[str(item) for item in data.get("implementation_details", []) if str(item).strip()],
        api_changes=[str(item) for item in data.get("api_changes", []) if str(item).strip()],
        test_changes=[str(item) for item in data.get("test_changes", []) if str(item).strip()],
        breaking_changes=[str(item) for item in data.get("breaking_changes", []) if str(item).strip()],
        important_context=[str(item) for item in data.get("important_context", []) if str(item).strip()],
        uncertainties=[str(item) for item in data.get("uncertainties", []) if str(item).strip()],
    )


@dataclass
class _ParsedHunk:
    header: str
    lines: list[str]


@dataclass
class _ParsedFile:
    header: str
    file_path: str
    is_binary: bool
    hunks: list[_ParsedHunk]


def _extract_file_path(header: str) -> str:
    """Extract destination file path from unified diff header."""
    for line in header.splitlines():
        if line.startswith("+++ b/"):
            return line[6:].strip()
        if line.startswith("diff --git a/"):
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return "unknown_file"


def _parse_unified_diff(lines_iter: Any) -> list[_ParsedFile]:
    """Parse raw unified diff lines into file and hunk hierarchies."""
    files: list[_ParsedFile] = []
    current_header_lines: list[str] = []
    current_hunks: list[_ParsedHunk] = []
    current_hunk_header: str | None = None
    current_hunk_lines: list[str] = []
    is_binary = False

    def flush_hunk() -> None:
        nonlocal current_hunk_header, current_hunk_lines
        if current_hunk_header is not None:
            current_hunks.append(_ParsedHunk(header=current_hunk_header, lines=current_hunk_lines))
            current_hunk_header = None
            current_hunk_lines = []

    def flush_file() -> None:
        nonlocal current_header_lines, current_hunks, is_binary
        flush_hunk()
        if current_header_lines:
            header_str = "".join(current_header_lines)
            path = _extract_file_path(header_str)
            files.append(
                _ParsedFile(
                    header=header_str,
                    file_path=path,
                    is_binary=is_binary,
                    hunks=current_hunks,
                )
            )
            current_header_lines = []
            current_hunks = []
            is_binary = False

    for line in lines_iter:
        if line.startswith("diff --git "):
            flush_file()
            current_header_lines.append(line)
        elif line.startswith("@@ "):
            flush_hunk()
            current_hunk_header = line
        elif current_hunk_header is not None:
            current_hunk_lines.append(line)
        else:
            if "Binary files " in line or "GIT binary patch" in line:
                is_binary = True
            current_header_lines.append(line)

    flush_file()
    return files


def _split_oversized_line(line: str, max_chunk_chars: int, file_path: str) -> list[str]:
    """Split an oversized line into ordered, explicitly numbered continuation fragments.

    Preserves 100% of characters across all fragments.
    """
    prefix = ""
    content = line
    if line.startswith(("+", "-", " ")):
        prefix = line[0]
        content = line[1:]

    # Target fragment size leaves room for continuation marker
    marker_overhead = 120
    frag_size = max(100, max_chunk_chars - marker_overhead)
    total_frags = math.ceil(len(content) / frag_size)

    fragments: list[str] = []
    for idx in range(total_frags):
        start = idx * frag_size
        end = min(len(content), (idx + 1) * frag_size)
        part = content[start:end]
        marker = (
            f"{prefix} [Line continuation fragment {idx + 1}/{total_frags} "
            f"for '{file_path}' (chars {start}-{end})]: "
        )
        fragments.append(marker + part + ("\n" if not part.endswith("\n") else ""))

    return fragments


def create_diff_chunks(
    diff: StagedDiff,
    max_chunk_chars: int,
    split_reasons: dict[str, int] | None = None,
) -> list[DiffChunk]:
    """Slice staged changes into logically coherent, bounded-size diff chunks.

    Hierarchy:
    1. Complete file diffs together whenever they fit.
    2. Split oversized file changes at hunk boundaries.
    3. Split oversized hunks at line boundaries.
    4. Split oversized lines into numbered continuation fragments without character loss.
    5. Retain file headers across all split chunks.
    """
    if split_reasons is not None:
        split_reasons.setdefault("file_boundary", 0)
        split_reasons.setdefault("hunk_boundary", 0)
        split_reasons.setdefault("line_boundary", 0)
        split_reasons.setdefault("oversized_line", 0)

    parsed_files = _parse_unified_diff(diff.iter_lines())

    if not parsed_files:
        # If no diff content was found (e.g. empty commit or binary-only with no hunks)
        file_paths = [f.path for f in diff.files]
        summary_content = "\n".join(f"- {f.path} [{f.status.value}]" for f in diff.files) or "(No diff content)"
        return [DiffChunk(chunk_index=1, total_chunks=1, content=summary_content, files=file_paths)]

    raw_chunks: list[tuple[str, list[str]]] = []
    current_lines: list[str] = []
    current_files: list[str] = []
    current_size = 0

    def flush_chunk() -> None:
        nonlocal current_lines, current_files, current_size
        if current_lines:
            raw_chunks.append(("".join(current_lines), list(dict.fromkeys(current_files))))
            current_lines = []
            current_files = []
            current_size = 0

    for file_obj in parsed_files:
        # Calculate full file diff size
        file_hunk_lines = [h.header + "".join(h.lines) for h in file_obj.hunks]
        file_total_str = file_obj.header + "".join(file_hunk_lines)
        file_len = len(file_total_str)

        # Priority 1: Complete file fits in current chunk
        if current_size + file_len <= max_chunk_chars:
            current_lines.append(file_total_str)
            current_files.append(file_obj.file_path)
            current_size += file_len
            continue

        # If current chunk already has data, flush it to try fitting file into a clean chunk
        if current_size > 0:
            if split_reasons is not None:
                split_reasons["file_boundary"] += 1
            flush_chunk()

        # Check if file fits in a clean empty chunk
        if file_len <= max_chunk_chars:
            current_lines.append(file_total_str)
            current_files.append(file_obj.file_path)
            current_size += file_len
            continue

        # Priority 2: File exceeds chunk budget -> split at hunk boundaries
        file_header = file_obj.header
        continuation_header = (
            file_header.rstrip("\n")
            + f"\n[File '{file_obj.file_path}' continuation from previous chunk]\n"
        )
        is_first_chunk_for_file = True

        for hunk in file_obj.hunks:
            hunk_content = hunk.header + "".join(hunk.lines)
            hunk_len = len(hunk_content)
            header_to_use = file_header if is_first_chunk_for_file else continuation_header
            header_len = len(header_to_use)

            # Check if hunk fits into current chunk
            if current_size + hunk_len + (header_len if file_obj.file_path not in current_files else 0) <= max_chunk_chars:
                if file_obj.file_path not in current_files:
                    current_lines.append(header_to_use)
                    current_size += header_len
                    current_files.append(file_obj.file_path)
                    is_first_chunk_for_file = False
                current_lines.append(hunk_content)
                current_size += hunk_len
                continue

            # Flush current chunk if non-empty
            if current_size > 0:
                if split_reasons is not None:
                    split_reasons["hunk_boundary"] += 1
                flush_chunk()

            # Check if hunk fits into fresh chunk
            header_to_use = file_header if is_first_chunk_for_file else continuation_header
            header_len = len(header_to_use)
            if header_len + hunk_len <= max_chunk_chars:
                current_lines.append(header_to_use)
                current_lines.append(hunk_content)
                current_files.append(file_obj.file_path)
                current_size = header_len + hunk_len
                is_first_chunk_for_file = False
                continue

            # Priority 3: Hunk exceeds chunk budget -> split at line boundaries
            current_lines.append(header_to_use)
            current_lines.append(hunk.header)
            current_files.append(file_obj.file_path)
            current_size = header_len + len(hunk.header)
            is_first_chunk_for_file = False

            for line in hunk.lines:
                line_len = len(line)
                # Priority 4: Giant line exceeds entire budget
                if line_len > max_chunk_chars:
                    if current_size > 0:
                        flush_chunk()
                    fragments = _split_oversized_line(line, max_chunk_chars, file_obj.file_path)
                    if split_reasons is not None:
                        split_reasons["oversized_line"] += len(fragments)
                    for frag in fragments:
                        raw_chunks.append((
                            f"{continuation_header}{hunk.header}{frag}",
                            [file_obj.file_path],
                        ))
                    continue

                if current_size + line_len > max_chunk_chars:
                    if split_reasons is not None:
                        split_reasons["line_boundary"] += 1
                    flush_chunk()
                    current_lines.append(continuation_header)
                    current_lines.append(f"{hunk.header.rstrip()}\n")
                    current_files.append(file_obj.file_path)
                    current_size = len(continuation_header) + len(hunk.header)

                current_lines.append(line)
                current_size += line_len

    flush_chunk()

    total = len(raw_chunks)
    return [
        DiffChunk(
            chunk_index=idx + 1,
            total_chunks=total,
            content=content,
            files=files,
        )
        for idx, (content, files) in enumerate(raw_chunks)
    ]
