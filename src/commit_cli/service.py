"""Service coordinating prompt construction, provider generation, diff chunking, and commit parsing."""

from collections.abc import Callable
import math
from pathlib import Path
from typing import Any

from commit_cli.diagnostics import (
    GenerationDiagnostics,
    ReductionPassMetrics,
    RequestMetric,
    build_chunk_plan_diagnostics,
    build_diff_diagnostics,
    calculate_context_budget_diagnostics,
)
from commit_cli.exceptions import (
    CommitCLIError,
    CommitParseError,
    CommitValidationError,
    GenerationTimeoutError,
    ProviderError,
)
from commit_cli.git.chunking import (
    CHARS_PER_TOKEN,
    CHUNK_ANALYSIS_JSON_SCHEMA,
    ChunkSummary,
    DiffChunk,
    FileSummary,
    compute_diff_char_budget,
    create_diff_chunks,
    parse_chunk_summary,
)
from commit_cli.models import CommitMessage, GenerationRequest, StagedDiff, StreamChunk
from commit_cli.parser.commit import parse_commit_response
from commit_cli.prompt.engine import (
    build_chunk_analysis_request,
    build_generation_request,
    build_synthesis_request,
)
from commit_cli.providers.base import BaseLLMProvider


class GenerationService:
    """Orchestrates commit message generation from staged diffs with automatic large-diff processing."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        custom_rules: str | None = None,
        recent_commits: list[str] | None = None,
        diagnostics: GenerationDiagnostics | None = None,
    ) -> None:
        self._provider = provider
        self._custom_rules = custom_rules
        self._recent_commits = recent_commits
        self._cached_summaries: list[ChunkSummary] | None = None
        self.diagnostics = diagnostics

    @property
    def provider(self) -> BaseLLMProvider:
        return self._provider

    def clear_summary_cache(self) -> None:
        """Discard cached chunk summaries (e.g. when staged snapshot is refreshed)."""
        self._cached_summaries = None

    def _record_metric(
        self,
        stage: str,
        resp: Any,
        chunk_index: int | None = None,
        file_count: int | None = None,
        char_count: int | None = None,
        estimated_tokens: int | None = None,
        retries: int = 0,
    ) -> None:
        """Record model request metrics into diagnostics if enabled."""
        if self.diagnostics is None or resp is None:
            return

        prompt_tokens = getattr(resp, "prompt_tokens", None) or getattr(resp, "prompt_eval_count", None)
        if not isinstance(prompt_tokens, (int, float)):
            prompt_tokens = None
        else:
            prompt_tokens = int(prompt_tokens)

        generated_tokens = getattr(resp, "eval_count", None) or getattr(resp, "total_tokens", None)
        if not isinstance(generated_tokens, (int, float)):
            generated_tokens = None
        else:
            generated_tokens = int(generated_tokens)

        total_sec = getattr(resp, "duration_seconds", None)
        total_ns = getattr(resp, "total_duration_ns", None)
        if not isinstance(total_sec, (int, float)):
            total_sec = None
        if total_sec is None and isinstance(total_ns, (int, float)):
            total_sec = total_ns / 1e9

        load_ns = getattr(resp, "load_duration_ns", None)
        load_sec = (load_ns / 1e9) if isinstance(load_ns, (int, float)) else None

        pe_ns = getattr(resp, "prompt_eval_duration_ns", None)
        pe_sec = (pe_ns / 1e9) if isinstance(pe_ns, (int, float)) else None

        eval_ns = getattr(resp, "eval_duration_ns", None)
        eval_sec = (eval_ns / 1e9) if isinstance(eval_ns, (int, float)) else None

        tps = None
        if generated_tokens and eval_sec and eval_sec > 0:
            tps = round(generated_tokens / eval_sec, 1)

        self.diagnostics.request_metrics.append(
            RequestMetric(
                stage=stage,
                chunk_index=chunk_index,
                file_count=file_count,
                char_count=char_count,
                estimated_tokens=estimated_tokens,
                prompt_tokens=prompt_tokens,
                generated_tokens=generated_tokens,
                total_duration_sec=total_sec,
                load_duration_sec=load_sec,
                prompt_eval_duration_sec=pe_sec,
                eval_duration_sec=eval_sec,
                tokens_per_second=tps,
                retries=retries,
            )
        )

    def _prepare_diagnostics_plan(
        self,
        diff: StagedDiff,
        budget: int,
        split_reasons: dict[str, int],
        chunks: list[DiffChunk],
    ) -> None:
        """Populate pre-analysis model, budget, diff, and chunk plan diagnostics."""
        if self.diagnostics is None:
            return
        if hasattr(self._provider, "get_diagnostics"):
            self.diagnostics.model = self._provider.get_diagnostics()
        ctx_window = None
        try:
            ctx_window = self._provider.get_context_window()
        except Exception:
            pass
        fallback_used = not isinstance(ctx_window, int) or ctx_window <= 0
        ctx_reason = getattr(self._provider, "_cached_context_reason", "")
        self.diagnostics.context_budget = calculate_context_budget_diagnostics(
            context_window=ctx_window,
            context_reason=ctx_reason,
            fallback_used=fallback_used,
        )
        self.diagnostics.diff = build_diff_diagnostics(diff, chunks, budget)
        self.diagnostics.chunk_plan = build_chunk_plan_diagnostics(chunks, split_reasons)

    def _get_char_budget(self) -> int:
        """Compute the model-aware character budget for a single diff prompt."""
        try:
            ctx_window = self._provider.get_context_window()
        except Exception:
            ctx_window = None
        if not isinstance(ctx_window, int):
            ctx_window = None
        return compute_diff_char_budget(ctx_window)

    def _analyze_chunk_with_retry(
        self,
        chunk: DiffChunk,
        retry_depth: int = 0,
    ) -> list[ChunkSummary]:
        """Analyze a chunk with bounded retry if provider reports context overflow or parsing fails."""
        req = build_chunk_analysis_request(
            chunk=chunk,
            custom_rules=self._custom_rules,
            max_tokens=2048,
        )
        est_tokens = math.ceil(len(chunk.content) / CHARS_PER_TOKEN)
        try:
            response = self._provider.generate(req)
            self._record_metric(
                stage="retry" if retry_depth > 0 else "chunk_analysis",
                resp=response,
                chunk_index=chunk.chunk_index,
                file_count=len(chunk.files),
                char_count=len(chunk.content),
                estimated_tokens=est_tokens,
                retries=retry_depth,
            )
            summary = parse_chunk_summary(response.text)
            return [summary]
        except (ProviderError, CommitParseError, CommitValidationError) as e:
            err_msg = str(e).lower()
            is_overflow = any(term in err_msg for term in ("context", "overflow", "too long", "exceeds", "token limit"))
            is_parse_failure = isinstance(e, (CommitParseError, CommitValidationError))
            is_timeout = isinstance(e, GenerationTimeoutError) or "timed out" in err_msg

            if (is_overflow or is_parse_failure or is_timeout) and retry_depth < 2 and len(chunk.content) > 100:
                # Bounded retry: split chunk in half and analyze sub-chunks
                half_budget = max(50, len(chunk.content) // 2)
                sub_diff = StagedDiff(raw_diff=chunk.content, original_char_count=len(chunk.content))
                sub_chunks = create_diff_chunks(sub_diff, max_chunk_chars=half_budget)
                if len(sub_chunks) > 1:
                    sub_summaries: list[ChunkSummary] = []
                    for sub in sub_chunks:
                        sub_summaries.extend(self._analyze_chunk_with_retry(sub, retry_depth=retry_depth + 1))
                    return sub_summaries

            # If sub-chunking cannot proceed on parse failure or timeout, build a fallback summary from chunk file metadata
            if (is_parse_failure or is_timeout) and chunk.files:
                return [
                    ChunkSummary(
                        files=[FileSummary(path=f, change_type="modified") for f in chunk.files],
                        functional_changes=[f"Update {Path(f).name}" for f in chunk.files],
                    )
                ]
            raise

    def _analyze_all_chunks(
        self,
        chunks: list[DiffChunk],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[ChunkSummary]:
        """Sequentially analyze all diff chunks into validated ChunkSummary instances."""
        summaries: list[ChunkSummary] = []
        total = len(chunks)

        for chunk in chunks:
            if on_progress:
                on_progress(chunk.chunk_index, total, "analyzing")

            chunk_summaries = self._analyze_chunk_with_retry(chunk)
            summaries.extend(chunk_summaries)

            if on_progress:
                on_progress(chunk.chunk_index, total, "chunk_done")

        return summaries

    def _estimate_summaries_size(self, summaries: list[ChunkSummary]) -> int:
        """Estimate the total formatted character volume of summaries."""
        total = 0
        for s in summaries:
            total += sum(len(f.path) + len(getattr(f, "change_type", "modified")) for f in s.files)
            total += sum(len(x) for x in s.functional_changes)
            total += sum(len(x) for x in s.implementation_details)
            total += sum(len(x) for x in s.api_changes)
            total += sum(len(x) for x in s.breaking_changes)
            total += sum(len(x) for x in s.test_changes)
        return total

    def _deterministic_merge_batch(self, batch: list[ChunkSummary]) -> ChunkSummary:
        """Deterministically merge and deduplicate a batch of chunk summaries."""
        all_files: list[Any] = []
        all_func: list[str] = []
        all_api: list[str] = []
        all_breaking: list[str] = []
        all_tests: list[str] = []
        all_impl: list[str] = []
        for s in batch:
            all_files.extend(s.files)
            all_func.extend(s.functional_changes)
            all_api.extend(s.api_changes)
            all_breaking.extend(s.breaking_changes)
            all_tests.extend(s.test_changes)
            all_impl.extend(s.implementation_details)

        # Deduplicate files by path preserving order
        unique_files: list[Any] = []
        seen_paths: set[str] = set()
        for f in all_files:
            if f.path not in seen_paths:
                seen_paths.add(f.path)
                unique_files.append(f)

        return ChunkSummary(
            files=unique_files,
            functional_changes=list(dict.fromkeys(all_func)),
            implementation_details=list(dict.fromkeys(all_impl)),
            api_changes=list(dict.fromkeys(all_api)),
            test_changes=list(dict.fromkeys(all_tests)),
            breaking_changes=list(dict.fromkeys(all_breaking)),
        )

    def _model_assisted_reduce_batch(
        self,
        batch: list[ChunkSummary],
        on_progress: Callable[[int, int, str], None] | None = None,
        batch_index: int = 1,
        total_batches: int = 1,
    ) -> ChunkSummary:
        """Use the same provider instance to distill and reduce a collection of chunk summaries."""
        det_summary = self._deterministic_merge_batch(batch)
        prompt_parts = ["SUMMARIES TO CONSOLIDATE:"]
        for idx, s in enumerate(batch):
            prompt_parts.append(f"Summary {idx + 1}:")
            if s.files:
                prompt_parts.append(
                    "Files: " + ", ".join(f"{f.path} ({getattr(f, 'change_type', getattr(f, 'action', 'modified'))})" for f in s.files)
                )
            if s.functional_changes:
                prompt_parts.append("Functional: " + "; ".join(s.functional_changes))
            if s.api_changes:
                prompt_parts.append("API: " + "; ".join(s.api_changes))
            if s.breaking_changes:
                prompt_parts.append("Breaking Evidence: " + "; ".join(s.breaking_changes))

        prompt_parts.append(
            "Consolidate these into ONE concise, structured ChunkSummary JSON adhering to the schema.\n"
            "Eliminate duplicate details, preserve all file paths, preserve all API changes, and preserve 100% of breaking-change evidence."
        )

        red_req = GenerationRequest(
            prompt="\n\n".join(prompt_parts),
            system_prompt="You are a senior technical editor condensing multiple code change summaries into one unified summary JSON. Output ONLY valid JSON matching the schema.",
            response_schema=CHUNK_ANALYSIS_JSON_SCHEMA,
            temperature=0.1,
            max_tokens=600,
        )
        if on_progress:
            on_progress(batch_index, total_batches, "reducing")

        try:
            resp = self._provider.generate(red_req)
            self._record_metric(stage="reduction", resp=resp)
            parsed = parse_chunk_summary(resp.text)
            combined_breaking = list(dict.fromkeys(det_summary.breaking_changes + parsed.breaking_changes))
            all_file_paths = {f.path for f in det_summary.files}
            for f in parsed.files:
                all_file_paths.discard(f.path)
            extra_files = [f for f in det_summary.files if f.path in all_file_paths]
            return ChunkSummary(
                files=parsed.files + extra_files,
                functional_changes=parsed.functional_changes or det_summary.functional_changes,
                implementation_details=parsed.implementation_details or det_summary.implementation_details,
                api_changes=list(dict.fromkeys(det_summary.api_changes + parsed.api_changes)),
                test_changes=list(dict.fromkeys(det_summary.test_changes + parsed.test_changes)),
                breaking_changes=combined_breaking,
            )
        except Exception:
            return det_summary

    def _reduce_summaries_if_needed(
        self,
        summaries: list[ChunkSummary],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[ChunkSummary]:
        """Hierarchically consolidate large collections of chunk summaries until they fit budget."""
        budget = self._get_char_budget()
        current = summaries
        if self.diagnostics is not None:
            self.diagnostics.initial_summary_count = len(summaries)

        # If already within budget and count <= 8, no reduction needed
        if len(current) <= 8 and self._estimate_summaries_size(current) <= budget:
            if self.diagnostics is not None:
                self.diagnostics.final_synthesis_fits_budget = True
            return current

        # Recursive/iterative reduction bounded to at most 3 passes
        for pass_idx in range(3):
            batch_size = 4
            batches = [current[i : i + batch_size] for i in range(0, len(current), batch_size)]
            input_count = len(current)
            input_size = self._estimate_summaries_size(current)
            req_count = len(batches) if pass_idx > 0 else 0

            if pass_idx == 0:
                current = [self._deterministic_merge_batch(b) for b in batches]
            else:
                current = [
                    self._model_assisted_reduce_batch(
                        b,
                        on_progress=on_progress,
                        batch_index=i + 1,
                        total_batches=len(batches),
                    )
                    for i, b in enumerate(batches)
                ]

            output_count = len(current)
            output_size = self._estimate_summaries_size(current)

            if self.diagnostics is not None:
                self.diagnostics.reduction_passes.append(
                    ReductionPassMetrics(
                        pass_number=pass_idx + 1,
                        input_summary_count=input_count,
                        output_summary_count=output_count,
                        input_size_chars=input_size,
                        output_size_chars=output_size,
                        reduction_requests=req_count,
                    )
                )

            if len(current) <= 8 and self._estimate_summaries_size(current) <= budget:
                if self.diagnostics is not None:
                    self.diagnostics.final_synthesis_fits_budget = True
                return current

        if self.diagnostics is not None:
            self.diagnostics.final_synthesis_fits_budget = (self._estimate_summaries_size(current) <= budget)

        if self._estimate_summaries_size(current) > budget * 2 and len(current) > 8:
            raise CommitCLIError("Summary volume exceeds synthesis context budget even after hierarchical reduction.")

        return current

    def generate_commit(
        self,
        diff: StagedDiff,
        user_feedback: str | None = None,
        temperature: float = 0.1,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> CommitMessage:
        """Generate a validated CommitMessage synchronously (non-streaming)."""
        if not diff.files and diff.original_char_count == 0:
            raise CommitCLIError("Cannot generate commit message: no staged changes provided.")

        budget = self._get_char_budget()

        # Fast path: staged diff fits comfortably within one request
        if diff.original_char_count <= budget:
            self._prepare_diagnostics_plan(
                diff=diff,
                budget=budget,
                split_reasons={"file_boundary": 0, "hunk_boundary": 0, "line_boundary": 0, "oversized_line": 0},
                chunks=[DiffChunk(chunk_index=1, total_chunks=1, content=diff.raw_diff, files=[f.path for f in diff.files])],
            )
            request = build_generation_request(
                diff=diff,
                custom_rules=self._custom_rules,
                recent_commits=self._recent_commits,
                user_feedback=user_feedback,
                temperature=temperature,
            )
            if on_progress:
                on_progress(1, 1, "generating")

            response = self._provider.generate(request)
            self._record_metric("synthesis", response)
            return parse_commit_response(response.text)

        # Chunked hierarchical generation path
        split_reasons: dict[str, int] = {}
        chunks = create_diff_chunks(diff, budget, split_reasons=split_reasons)
        self._prepare_diagnostics_plan(diff, budget, split_reasons, chunks)
        if len(chunks) == 1:
            request = build_generation_request(
                diff=diff,
                custom_rules=self._custom_rules,
                recent_commits=self._recent_commits,
                user_feedback=user_feedback,
                temperature=temperature,
            )
            if on_progress:
                on_progress(1, 1, "generating")

            response = self._provider.generate(request)
            self._record_metric("synthesis", response)
            return parse_commit_response(response.text)

        # Multi-chunk processing
        if self._cached_summaries is None:
            self._cached_summaries = self._analyze_all_chunks(chunks, on_progress=on_progress)

        if on_progress:
            on_progress(len(chunks), len(chunks), "synthesizing")

        summaries = self._reduce_summaries_if_needed(self._cached_summaries, on_progress=on_progress)
        synth_req = build_synthesis_request(
            summaries=summaries,
            custom_rules=self._custom_rules,
            recent_commits=self._recent_commits,
            user_feedback=user_feedback,
            temperature=temperature,
        )
        synth_resp = self._provider.generate(synth_req)
        self._record_metric("synthesis", synth_resp)
        return parse_commit_response(synth_resp.text)

    def stream_commit(
        self,
        diff: StagedDiff,
        on_chunk: Callable[[StreamChunk], None] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
        user_feedback: str | None = None,
        temperature: float = 0.1,
    ) -> CommitMessage:
        """Stream generated text chunks and return a validated CommitMessage."""
        if not diff.files and diff.original_char_count == 0:
            raise CommitCLIError("Cannot generate commit message: no staged changes provided.")

        budget = self._get_char_budget()

        # Fast path: diff fits in single request
        if diff.original_char_count <= budget:
            self._prepare_diagnostics_plan(
                diff=diff,
                budget=budget,
                split_reasons={"file_boundary": 0, "hunk_boundary": 0, "line_boundary": 0, "oversized_line": 0},
                chunks=[DiffChunk(chunk_index=1, total_chunks=1, content=diff.raw_diff, files=[f.path for f in diff.files])],
            )
            request = build_generation_request(
                diff=diff,
                custom_rules=self._custom_rules,
                recent_commits=self._recent_commits,
                user_feedback=user_feedback,
                temperature=temperature,
            )
            if on_progress:
                on_progress(1, 1, "generating")

            accumulated_parts: list[str] = []
            final_chunk: StreamChunk | None = None
            for chunk in self._provider.stream(request):
                accumulated_parts.append(chunk.text)
                if chunk.is_done:
                    final_chunk = chunk
                if on_chunk is not None:
                    on_chunk(chunk)

            if final_chunk is not None:
                self._record_metric("synthesis", final_chunk)

            full_text = "".join(accumulated_parts).strip()
            if not full_text:
                raise CommitParseError("Generation stream completed without producing any text content.")
            return parse_commit_response(full_text)

        # Chunked hierarchical generation path
        split_reasons = {}
        chunks = create_diff_chunks(diff, budget, split_reasons=split_reasons)
        self._prepare_diagnostics_plan(diff, budget, split_reasons, chunks)
        if len(chunks) == 1:
            request = build_generation_request(
                diff=diff,
                custom_rules=self._custom_rules,
                recent_commits=self._recent_commits,
                user_feedback=user_feedback,
                temperature=temperature,
            )
            if on_progress:
                on_progress(1, 1, "generating")

            accumulated_parts = []
            final_chunk = None
            for chunk in self._provider.stream(request):
                accumulated_parts.append(chunk.text)
                if chunk.is_done:
                    final_chunk = chunk
                if on_chunk is not None:
                    on_chunk(chunk)
            if final_chunk is not None:
                self._record_metric("synthesis", final_chunk)
            full_text = "".join(accumulated_parts).strip()
            if not full_text:
                raise CommitParseError("Generation stream completed without producing any text content.")
            return parse_commit_response(full_text)

        # Multi-chunk processing
        if self._cached_summaries is None:
            self._cached_summaries = self._analyze_all_chunks(chunks, on_progress=on_progress)

        if on_progress:
            on_progress(len(chunks), len(chunks), "synthesizing")

        summaries = self._reduce_summaries_if_needed(self._cached_summaries, on_progress=on_progress)
        synth_req = build_synthesis_request(
            summaries=summaries,
            custom_rules=self._custom_rules,
            recent_commits=self._recent_commits,
            user_feedback=user_feedback,
            temperature=temperature,
        )

        accumulated_parts = []
        final_chunk = None
        for chunk in self._provider.stream(synth_req):
            accumulated_parts.append(chunk.text)
            if chunk.is_done:
                final_chunk = chunk
            if on_chunk is not None:
                on_chunk(chunk)

        if final_chunk is not None:
            self._record_metric("synthesis", final_chunk)

        full_text = "".join(accumulated_parts).strip()
        if not full_text:
            raise CommitParseError("Generation stream completed without producing any text content.")

        return parse_commit_response(full_text)

    generate_stream = stream_commit
