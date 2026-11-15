"""Diagnostic models, observability metrics, and calculation helpers for Commit generation."""

from dataclasses import dataclass, field
import math
import os
import statistics

from commit_cli.git.chunking import (
    CHARS_PER_TOKEN,
    DEFAULT_FALLBACK_CONTEXT_WINDOW,
    MAX_CHUNK_DIFF_TOKENS,
    DiffChunk,
)
from commit_cli.models import StagedDiff


@dataclass(frozen=True)
class ModelDiagnostics:
    """Detailed metadata and context observability for the LLM provider model."""

    model_name: str
    server_version: str | None = None
    architecture: str | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None
    advertised_context_length: int | None = None
    modelfile_num_ctx: int | None = None
    server_default_num_ctx: int | None = None
    request_num_ctx: int | None = None
    runtime_loaded_num_ctx: int | None = None
    context_source: str = "Unknown"
    context_confidence: str = "Unknown"


@dataclass(frozen=True)
class ContextBudgetDiagnostics:
    """Detailed inspection of the context budgeting calculations."""

    effective_context_tokens: int
    system_prompt_overhead_tokens: int
    schema_overhead_tokens: int
    metadata_overhead_tokens: int
    reserved_output_tokens: int
    total_overhead_tokens: int
    safety_margin_tokens: int
    available_diff_tokens: int
    practical_diff_tokens: int
    chars_per_token_ratio: float
    estimated_char_budget: int
    fallback_context_used: bool
    context_reason: str
    is_safe: bool
    unsafe_warning: str | None = None


@dataclass(frozen=True)
class DiffDiagnostics:
    """Pre-analysis metrics and statistics for the staged diff."""

    total_files: int
    files_by_type: dict[str, int]
    binary_files_count: int
    insertions: int
    deletions: int
    size_bytes: int
    size_chars: int
    estimated_tokens: int
    estimation_method: str
    planned_chunks: int
    per_chunk_budget_chars: int


@dataclass(frozen=True)
class ChunkPlanDiagnostics:
    """Distribution and partitioning metrics for the diff chunking plan."""

    chunk_count: int
    min_chunk_chars: int
    avg_chunk_chars: float
    median_chunk_chars: float
    max_chunk_chars: int
    min_est_tokens: int
    avg_est_tokens: float
    max_est_tokens: int
    split_reasons: dict[str, int]


@dataclass
class RequestMetric:
    """Measured and estimated metrics for an individual LLM request."""

    stage: str  # "chunk_analysis", "retry", "reduction", "synthesis"
    chunk_index: int | None = None
    file_count: int | None = None
    char_count: int | None = None
    estimated_tokens: int | None = None
    prompt_tokens: int | None = None
    generated_tokens: int | None = None
    total_duration_sec: float | None = None
    load_duration_sec: float | None = None
    prompt_eval_duration_sec: float | None = None
    eval_duration_sec: float | None = None
    tokens_per_second: float | None = None
    retries: int = 0


@dataclass
class ReductionPassMetrics:
    """Metrics tracking hierarchical summary reduction passes."""

    pass_number: int
    input_summary_count: int
    output_summary_count: int
    input_size_chars: int
    output_size_chars: int
    reduction_requests: int


@dataclass
class GenerationDiagnostics:
    """Comprehensive diagnostic container for a complete generation run."""

    model: ModelDiagnostics | None = None
    diff: DiffDiagnostics | None = None
    context_budget: ContextBudgetDiagnostics | None = None
    chunk_plan: ChunkPlanDiagnostics | None = None
    request_metrics: list[RequestMetric] = field(default_factory=list)
    reduction_passes: list[ReductionPassMetrics] = field(default_factory=list)
    initial_summary_count: int = 0
    final_synthesis_fits_budget: bool = True

    @property
    def total_requests(self) -> int:
        return len(self.request_metrics)

    @property
    def requests_by_stage(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for m in self.request_metrics:
            counts[m.stage] = counts.get(m.stage, 0) + 1
        return counts

    @property
    def total_prompt_tokens(self) -> int | None:
        vals = [m.prompt_tokens for m in self.request_metrics if m.prompt_tokens is not None]
        return sum(vals) if vals else None

    @property
    def avg_prompt_tokens(self) -> float | None:
        vals = [m.prompt_tokens for m in self.request_metrics if m.prompt_tokens is not None]
        return (sum(vals) / len(vals)) if vals else None

    @property
    def total_generated_tokens(self) -> int | None:
        vals = [m.generated_tokens for m in self.request_metrics if m.generated_tokens is not None]
        return sum(vals) if vals else None

    @property
    def avg_generated_tokens(self) -> float | None:
        vals = [m.generated_tokens for m in self.request_metrics if m.generated_tokens is not None]
        return (sum(vals) / len(vals)) if vals else None

    @property
    def total_load_duration_sec(self) -> float:
        return sum(m.load_duration_sec for m in self.request_metrics if m.load_duration_sec is not None)

    @property
    def total_prompt_eval_duration_sec(self) -> float:
        return sum(m.prompt_eval_duration_sec for m in self.request_metrics if m.prompt_eval_duration_sec is not None)

    @property
    def total_eval_duration_sec(self) -> float:
        return sum(m.eval_duration_sec for m in self.request_metrics if m.eval_duration_sec is not None)

    @property
    def overall_elapsed_sec(self) -> float:
        return sum(m.total_duration_sec for m in self.request_metrics if m.total_duration_sec is not None)

    @property
    def avg_tokens_per_second(self) -> float | None:
        speeds = [m.tokens_per_second for m in self.request_metrics if m.tokens_per_second is not None]
        return (sum(speeds) / len(speeds)) if speeds else None


def calculate_context_budget_diagnostics(
    context_window: int | None,
    context_reason: str = "",
    fallback_used: bool = False,
) -> ContextBudgetDiagnostics:
    """Calculate and explain the complete context budgeting breakdown."""
    ctx = context_window or DEFAULT_FALLBACK_CONTEXT_WINDOW
    effective_ctx = min(ctx, 32768)

    # Scale reserved overhead
    reserved_overhead = max(350, min(800, int(effective_ctx * 0.25)))
    safety_margin = max(100, int(effective_ctx * 0.15))

    # Overhead breakdown estimates (labeled clearly as heuristic estimates)
    system_prompt_est = min(300, int(reserved_overhead * 0.35))
    schema_est = min(250, int(reserved_overhead * 0.30))
    metadata_est = min(150, int(reserved_overhead * 0.15))
    reserved_output = max(200, reserved_overhead - system_prompt_est - schema_est - metadata_est)

    available = effective_ctx - safety_margin - reserved_overhead
    is_safe = available > 0

    unsafe_warning = None
    if not is_safe:
        unsafe_warning = (
            f"Context window ({effective_ctx} tokens) is too small to safely fit required "
            f"overhead ({reserved_overhead} tokens) and safety margin ({safety_margin} tokens)."
        )

    practical_diff_tokens = min(max(0, available), MAX_CHUNK_DIFF_TOKENS)
    estimated_char_budget = int(practical_diff_tokens * CHARS_PER_TOKEN)

    return ContextBudgetDiagnostics(
        effective_context_tokens=effective_ctx,
        system_prompt_overhead_tokens=system_prompt_est,
        schema_overhead_tokens=schema_est,
        metadata_overhead_tokens=metadata_est,
        reserved_output_tokens=reserved_output,
        total_overhead_tokens=reserved_overhead,
        safety_margin_tokens=safety_margin,
        available_diff_tokens=max(0, available),
        practical_diff_tokens=practical_diff_tokens,
        chars_per_token_ratio=CHARS_PER_TOKEN,
        estimated_char_budget=estimated_char_budget,
        fallback_context_used=fallback_used,
        context_reason=context_reason or ("Default fallback context" if fallback_used else "Detected model context"),
        is_safe=is_safe,
        unsafe_warning=unsafe_warning,
    )


def build_diff_diagnostics(
    diff: StagedDiff,
    chunks: list[DiffChunk],
    per_chunk_budget_chars: int,
) -> DiffDiagnostics:
    """Analyze staged diff and construct DiffDiagnostics without materializing full spool."""
    files_by_type: dict[str, int] = {}
    binary_count = 0
    for f in diff.files:
        st = f.status.value
        files_by_type[st] = files_by_type.get(st, 0) + 1
        if f.is_binary:
            binary_count += 1

    # Measure exact byte size without materializing into an in-memory string
    size_bytes = 0
    if getattr(diff, "_spool", None) is not None:
        try:
            spool = diff._spool
            spool.seek(0, os.SEEK_END)
            size_bytes = spool.tell()
            spool.seek(0)
        except Exception:
            size_bytes = diff.original_char_count
    else:
        size_bytes = len(diff.raw_diff.encode("utf-8", errors="replace"))

    est_tokens = math.ceil(diff.original_char_count / CHARS_PER_TOKEN)

    return DiffDiagnostics(
        total_files=len(diff.files),
        files_by_type=files_by_type,
        binary_files_count=binary_count,
        insertions=diff.total_additions,
        deletions=diff.total_deletions,
        size_bytes=size_bytes,
        size_chars=diff.original_char_count,
        estimated_tokens=est_tokens,
        estimation_method=f"Heuristic ratio: {CHARS_PER_TOKEN:.1f} chars/token (code & diff tokenization)",
        planned_chunks=len(chunks),
        per_chunk_budget_chars=per_chunk_budget_chars,
    )


def build_chunk_plan_diagnostics(
    chunks: list[DiffChunk],
    split_reasons: dict[str, int] | None = None,
) -> ChunkPlanDiagnostics:
    """Calculate chunk distribution statistics and split reasons."""
    reasons = split_reasons or {
        "file_boundary": 0,
        "hunk_boundary": 0,
        "line_boundary": 0,
        "oversized_line": 0,
    }

    if not chunks:
        return ChunkPlanDiagnostics(
            chunk_count=0,
            min_chunk_chars=0,
            avg_chunk_chars=0.0,
            median_chunk_chars=0.0,
            max_chunk_chars=0,
            min_est_tokens=0,
            avg_est_tokens=0.0,
            max_est_tokens=0,
            split_reasons=reasons,
        )

    char_sizes = [len(c.content) for c in chunks]
    est_tokens = [math.ceil(s / CHARS_PER_TOKEN) for s in char_sizes]

    return ChunkPlanDiagnostics(
        chunk_count=len(chunks),
        min_chunk_chars=min(char_sizes),
        avg_chunk_chars=round(statistics.mean(char_sizes), 1),
        median_chunk_chars=round(statistics.median(char_sizes), 1),
        max_chunk_chars=max(char_sizes),
        min_est_tokens=min(est_tokens),
        avg_est_tokens=round(statistics.mean(est_tokens), 1),
        max_est_tokens=max(est_tokens),
        split_reasons=reasons,
    )
