"""Common formatting, notifications, status, and diagnostic renderers."""

from typing import Optional

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from commit_cli.diagnostics import GenerationDiagnostics
from commit_cli.ui.console import get_console
from commit_cli.ui.theme import get_preset_style


def format_duration(seconds: float) -> str:
    """Format duration in seconds as MM:SS (or HH:MM:SS if >= 1 hour)."""
    secs = int(max(0, seconds))
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{rem_secs:02d}"
    return f"{minutes:02d}:{rem_secs:02d}"


def format_progress_phase(cur: int, tot: int, ph: str) -> str:
    """Format chunk analysis and synthesis progress into a clean status string."""
    if ph == "analyzing":
        if tot > 1:
            return f"Analyzing chunk {cur}/{tot}"
        return "Analyzing staged changes"
    elif ph == "reducing":
        if tot > 1:
            return f"Reducing chunk summaries ({cur}/{tot})"
        return "Reducing chunk summaries"
    elif ph == "synthesizing":
        return "Synthesizing final commit message"
    elif ph == "generating":
        return "Generating commit message"
    else:
        ph_clean = ph.replace("_", " ").capitalize()
        if tot > 1:
            return f"{ph_clean} ({cur}/{tot})"
        return ph_clean


def clear_rendered_lines(n: int, console: Console) -> None:
    """Move cursor up n lines and clear each line, restoring cursor to top."""
    if n > 0 and console.is_terminal:
        console.file.write("\r" + ("\x1b[1A\x1b[2K" * n))
        console.file.flush()


def render_success(
    message: str,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render a success message with literal text safety."""
    c = console or get_console(preset=preset)
    style = get_preset_style(preset)

    text = Text()
    text.append(f"{style.icon_success} ", style="success")
    text.append(message, style="default")
    c.print(text)


def render_warning(
    message: str,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render a warning message with literal text safety (defaults to stderr)."""
    c = console or get_console(stderr=True, preset=preset)
    style = get_preset_style(preset)

    text = Text()
    text.append(f"{style.icon_warning} ", style="warning")
    text.append(message, style="default")
    c.print(text)


def render_error(
    message: str,
    detail: Optional[str] = None,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render an error message with literal text safety (defaults to stderr)."""
    c = console or get_console(stderr=True, preset=preset)
    style = get_preset_style(preset)

    if preset == "rich" and detail:
        content = Group(
            Text(message, style="error"),
            Text(detail, style="muted"),
        )
        panel = Panel(
            content,
            title=f"{style.icon_error} Error",
            box=box.ROUNDED,
            border_style="red",
            expand=False,
        )
        c.print(panel)
        return

    text = Text()
    text.append(f"{style.icon_error} ", style="error")
    text.append(message, style="error")
    if detail:
        text.append(f"\n  {detail}", style="muted")
    c.print(text)


def render_chunk_progress(
    current: int,
    total: int,
    phase: str,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render honest progress during large-diff multi-chunk analysis and synthesis."""
    c = console or get_console(preset=preset)
    resolved_preset = (preset or "minimal").lower()

    if phase == "analyzing":
        if current == 1:
            if resolved_preset == "minimal":
                c.print("Analyzing staged changes...")
            else:
                c.print("\n[bold]Analyzing staged changes...[/bold]\n")

    elif phase == "chunk_done":
        if resolved_preset == "minimal":
            c.print(f"Chunk {current} of {total}  ✔")
        else:
            c.print(f"Chunk {current} of {total}  [bold green]✔[/bold green]")

    elif phase == "synthesizing":
        if resolved_preset == "minimal":
            c.print("\nSynthesizing final commit message...\n")
        else:
            c.print("\n[bold cyan]Synthesizing final commit message...[/bold cyan]\n")


def render_generation_status(
    status: str,
    detail: Optional[str] = None,
    is_error: bool = False,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render a generation lifecycle status update."""
    c = console or get_console(preset=preset)
    style = get_preset_style(preset)

    if is_error:
        icon = style.icon_error
        status_style = "error"
    else:
        icon = style.icon_info
        status_style = "info"

    msg = Text()
    msg.append(f"{icon} ", style=status_style)
    msg.append(status, style=status_style)
    if detail:
        msg.append(f": {detail}", style="muted")
    c.print(msg)


def render_provisional_output(
    text: str,
    is_complete: bool = False,
    is_error: bool = False,
    error_message: Optional[str] = None,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render streamed model output clearly labeled as provisional.

    Streamed content is treated as untrusted literal text.
    """
    c = console or get_console(preset=preset)
    style = get_preset_style(preset)

    if is_error:
        err_text = Text()
        err_text.append(f"{style.icon_error} Generation failed: ", style="error")
        err_text.append(error_message or "Unknown error", style="error")
        c.print(err_text)
        return

    if not text.strip():
        c.print(Text("(No output received)", style="muted"))
        return

    status_label = (
        "Provisional output (stream ended — pending validation)"
        if is_complete
        else "Provisional output (generating...)"
    )

    if preset == "rich":
        content_group = Group(
            Text(status_label, style="provisional"),
            Text(),
            Text(text, style="default"),
        )
        panel = Panel(
            content_group,
            title="Model Generation Stream",
            box=box.ROUNDED,
            border_style="yellow",
            expand=False,
        )
        c.print(panel)
    else:
        c.print(f"[{status_label}]")
        c.print(Text(text))


def render_generation_diagnostics(
    diagnostics: GenerationDiagnostics,
    console: Optional[Console] = None,
    preset: str = "minimal",
) -> None:
    """Render comprehensive generation diagnostics and context observability."""
    c = console or get_console(preset=preset)
    resolved_preset = (preset or "minimal").lower()
    style = get_preset_style(resolved_preset)

    if resolved_preset == "minimal":
        c.print("\n=======================================================")
        c.print(" GENERATION DIAGNOSTICS")
        c.print("=======================================================\n")

        # 1. Model
        c.print("MODEL")
        if diagnostics.model:
            m = diagnostics.model
            c.print(f"  Model Name:             {m.model_name}")
            c.print(f"  Server Version:         {m.server_version or 'Unknown'}")
            c.print(f"  Architecture:           {m.architecture or 'Unknown'}")
            c.print(f"  Parameter Size:         {m.parameter_size or 'Unknown'}")
            c.print(f"  Quantization:           {m.quantization_level or 'Unknown'}")
            adv = f"{m.advertised_context_length:,} tokens" if m.advertised_context_length else "Unknown"
            mf = f"{m.modelfile_num_ctx:,} tokens" if m.modelfile_num_ctx else "Unknown"
            req = f"{m.request_num_ctx:,} tokens" if m.request_num_ctx else "Unknown"
            rt = f"{m.runtime_loaded_num_ctx:,} tokens" if m.runtime_loaded_num_ctx else "Unknown"
            c.print(f"  Context Length:         advertised: {adv} | modelfile: {mf}")
            c.print(f"                          requested: {req} | loaded runtime: {rt}")
        else:
            c.print("  Model information unavailable.")

        # 2. Diff
        c.print("\nDIFF")
        if diagnostics.diff:
            d = diagnostics.diff
            c.print(f"  Staged Files:           {d.staged_files}")
            c.print(f"  Total Lines:            +{d.total_additions:,} / -{d.total_deletions:,}")
            c.print(f"  Raw Diff Size:          {d.raw_diff_chars:,} chars ({d.raw_diff_lines:,} lines)")
            c.print(f"  Spool Size:             {d.spool_size_bytes:,} bytes")
            c.print(f"  Estimated Diff Tokens:  {d.estimated_tokens:,} ({d.estimation_method})")
            c.print(f"  Planned Chunks:         {d.planned_chunks} (budget: {d.per_chunk_budget_chars:,} chars/chunk)")
            trunc_str = f"Yes (from {d.original_chars:,} chars)" if d.is_truncated else "No"
            c.print(f"  Diff Truncated:         {trunc_str}")

        # 3. Context Budget
        c.print("\nCONTEXT BUDGET")
        if diagnostics.context_budget:
            b = diagnostics.context_budget
            c.print(f"  Effective Context:      {b.effective_context_tokens:,} tokens")
            c.print(
                f"  Reserved Overhead:      {b.total_overhead_tokens:,} tokens "
                f"(sys: ~{b.system_prompt_overhead_tokens}, schema: ~{b.schema_overhead_tokens}, "
                f"meta: ~{b.metadata_overhead_tokens}, out: ~{b.reserved_output_tokens})"
            )
            c.print(f"  Safety Margin:          {b.safety_margin_tokens:,} tokens")
            c.print(
                f"  Available Diff Tokens:  {b.available_diff_tokens:,} tokens "
                f"(practical cap: {b.practical_diff_tokens:,} tokens)"
            )
            c.print(f"  Ratio:                  {b.chars_per_token_ratio:.1f} chars/token")
            c.print(f"  Diff Char Budget:       {b.estimated_char_budget:,} chars")
            fb_note = " [fallback]" if b.is_fallback_budget else ""
            c.print(f"  Context Reason:         {b.context_reason}{fb_note}")
            safety_str = "SAFE (within limits)" if b.is_budget_safe else "WARNING (exceeds safe limits)"
            c.print(f"  Budget Assessment:      {safety_str}")
        else:
            c.print("  Context budget unavailable.")

        # 4. Chunk Planning
        c.print("\nCHUNK PLANNING")
        if diagnostics.chunk_plan:
            cp = diagnostics.chunk_plan
            c.print(f"  Total Chunks:           {cp.total_chunks}")
            c.print(f"  Single File Chunks:     {cp.single_file_chunks}")
            c.print(f"  Multi File Chunks:      {cp.multi_file_chunks}")
            c.print(f"  Chunk Char Budget:      {cp.chunk_budget_chars:,} chars")
            c.print(f"  Char Distribution:      min {cp.min_chars:,} | avg {cp.avg_chars:.1f} | max {cp.max_chars:,}")
            c.print(
                f"  Est. Chunk Tokens:      min {cp.min_est_tokens:,} | avg {cp.avg_est_tokens:.1f} | "
                f"max {cp.max_est_tokens:,}"
            )
            c.print(f"  Oversized Chunks:       {cp.oversized_chunks}")
        else:
            c.print("  Chunk plan unavailable.")

        # 5. Model Requests & Tokens
        c.print("\nMODEL REQUESTS & TOKENS")
        c.print(f"  Total Requests:         {diagnostics.total_requests}")
        c.print(f"  Total Latency:          {diagnostics.total_latency_seconds:.2f}s")
        tot_p = f"{diagnostics.total_prompt_tokens:,}" if diagnostics.total_prompt_tokens is not None else "-"
        avg_p = f"{diagnostics.avg_prompt_tokens:.1f}" if diagnostics.avg_prompt_tokens is not None else "-"
        c.print(f"  Prompt Tokens:          total {tot_p} | avg {avg_p}")
        tot_g = f"{diagnostics.total_generated_tokens:,}" if diagnostics.total_generated_tokens is not None else "-"
        avg_g = f"{diagnostics.avg_generated_tokens:.1f}" if diagnostics.avg_generated_tokens is not None else "-"
        c.print(f"  Generated Tokens:       total {tot_g} | avg {avg_g}")
        rate = (
            f"{diagnostics.avg_tokens_per_second:.1f} tokens/s"
            if diagnostics.avg_tokens_per_second is not None
            else "-"
        )
        c.print(f"  Generation Rate:        {rate}")
        c.print(f"  Ollama Stop Reasons:    {diagnostics.stop_reasons}")

        # 6. Map-Reduce Execution
        c.print("\nMAP-REDUCE SUMMARY")
        c.print(f"  Map Chunks Processed:   {len(diagnostics.chunk_requests)}")
        c.print(f"  Reduction Passes:       {len(diagnostics.reduction_passes)}")
        fits_str = "Yes" if diagnostics.final_synthesis_fits_budget else "No (exceeded)"
        c.print(f"  Fits Synthesis Budget:  {fits_str}")

        if diagnostics.chunk_requests:
            c.print("\nPER-CHUNK REQUEST BREAKDOWN")
            c.print(f"  {'#':<4} {'Type':<12} {'Chars':>8} {'EstTok':>8} {'PromptTok':>10} {'GenTok':>8} {'Latency':>8}")
            c.print(f"  {'-'*4} {'-'*12} {'-'*8} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
            for req in diagnostics.chunk_requests:
                chars_str = f"{req.char_count:,}" if req.char_count else "-"
                et = str(req.estimated_tokens) if req.estimated_tokens is not None else "-"
                pt = str(req.prompt_tokens) if req.prompt_tokens is not None else "-"
                gt = str(req.generated_tokens) if req.generated_tokens is not None else "-"
                lat = f"{req.latency_seconds:.2f}s"
                c.print(f"  {req.chunk_index:<4} {req.chunk_type:<12} {chars_str:>8} {et:>8} {pt:>10} {gt:>8} {lat:>8}")
        c.print("")
        return

    # Table Rendering
    # 1. Model Info
    t_model = Table(title="Model & Runtime", box=box.ROUNDED if style.use_panels else box.SIMPLE, show_header=False)
    t_model.add_column("Property", style="bold", no_wrap=True)
    t_model.add_column("Value")
    if diagnostics.model:
        m = diagnostics.model
        t_model.add_row("Model Name", m.model_name)
        t_model.add_row("Server Version", m.server_version or "Unknown")
        t_model.add_row("Architecture", m.architecture or "Unknown")
        t_model.add_row("Parameter Size", m.parameter_size or "Unknown")
        t_model.add_row("Quantization", m.quantization_level or "Unknown")
        t_model.add_row(
            "Advertised num_ctx",
            f"{m.advertised_context_length:,} tokens" if m.advertised_context_length else "Unknown",
        )
        t_model.add_row("Modelfile num_ctx", f"{m.modelfile_num_ctx:,} tokens" if m.modelfile_num_ctx else "Unknown")
        t_model.add_row("Request num_ctx", f"{m.request_num_ctx:,} tokens" if m.request_num_ctx else "Unknown")
        t_model.add_row(
            "Loaded Runtime num_ctx",
            f"{m.runtime_loaded_num_ctx:,} tokens" if m.runtime_loaded_num_ctx else "Unknown",
        )
    else:
        t_model.add_row("Status", "Unavailable")
    c.print(t_model)

    # 2. Diff & Context Budget
    t_diff = Table(title="Staged Diff", box=box.ROUNDED if style.use_panels else box.SIMPLE, show_header=False)
    t_diff.add_column("Property", style="bold", no_wrap=True)
    t_diff.add_column("Value")
    if diagnostics.diff:
        d = diagnostics.diff
        t_diff.add_row("Staged Files", str(d.staged_files))
        t_diff.add_row("Total Lines", f"+{d.total_additions:,} / -{d.total_deletions:,}")
        t_diff.add_row("Raw Diff Size", f"{d.raw_diff_chars:,} chars ({d.raw_diff_lines:,} lines)")
        t_diff.add_row("Spool File Size", f"{d.spool_size_bytes:,} bytes")
        t_diff.add_row("Estimated Diff Tokens", f"{d.estimated_tokens:,} ({d.estimation_method})")
        t_diff.add_row(
            "Planned Chunks",
            f"{d.planned_chunks} (budget: {d.per_chunk_budget_chars:,} chars/chunk)",
        )
        t_diff.add_row("Truncated", "Yes" if d.is_truncated else "No")
    else:
        t_diff.add_row("Status", "Unavailable")
    c.print(t_diff)

    # 3. Context Budgeting
    t_budget = Table(title="Context Budgeting", box=box.ROUNDED if style.use_panels else box.SIMPLE, show_header=False)
    t_budget.add_column("Property", style="bold", no_wrap=True)
    t_budget.add_column("Value")
    if diagnostics.context_budget:
        b = diagnostics.context_budget
        t_budget.add_row("Effective Context Window", f"{b.effective_context_tokens:,} tokens")
        t_budget.add_row(
            "Reserved Overhead",
            f"{b.total_overhead_tokens:,} tokens "
            f"(sys: ~{b.system_prompt_overhead_tokens}, schema: ~{b.schema_overhead_tokens}, "
            f"meta: ~{b.metadata_overhead_tokens}, out: ~{b.reserved_output_tokens})",
        )
        t_budget.add_row("Safety Margin", f"{b.safety_margin_tokens:,} tokens")
        t_budget.add_row(
            "Available Diff Tokens",
            f"{b.available_diff_tokens:,} tokens (practical cap: {b.practical_diff_tokens:,} tokens)",
        )
        t_budget.add_row("Chars / Token Ratio", f"{b.chars_per_token_ratio:.1f} chars/token (heuristic)")
        t_budget.add_row("Diff Character Budget", f"{b.estimated_char_budget:,} chars")
        fb_note = " [fallback]" if b.is_fallback_budget else ""
        t_budget.add_row("Context Reason", f"{b.context_reason}{fb_note}")
        safety_val = "[green]SAFE (within budget limits)[/green]" if b.is_budget_safe else "[bold red]WARNING (exceeds safe limits)[/bold red]"
        t_budget.add_row("Budget Assessment", safety_val)
    else:
        t_budget.add_row("Status", "Unavailable")
    c.print(t_budget)

    # 4. Chunk Plan
    t_plan = Table(title="Chunk Planning", box=box.ROUNDED if style.use_panels else box.SIMPLE, show_header=False)
    t_plan.add_column("Property", style="bold", no_wrap=True)
    t_plan.add_column("Value")
    if diagnostics.chunk_plan:
        cp = diagnostics.chunk_plan
        t_plan.add_row("Total Chunks", str(cp.total_chunks))
        t_plan.add_row("Single File / Multi File", f"{cp.single_file_chunks} / {cp.multi_file_chunks}")
        t_plan.add_row("Per-Chunk Budget", f"{cp.chunk_budget_chars:,} chars")
        t_plan.add_row(
            "Char Distribution",
            f"min {cp.min_chars:,} | avg {cp.avg_chars:.1f} | max {cp.max_chars:,}",
        )
        t_plan.add_row(
            "Est. Token Distribution",
            f"min {cp.min_est_tokens:,} | avg {cp.avg_est_tokens:.1f} | max {cp.max_est_tokens:,}",
        )
        t_plan.add_row("Oversized Chunks", str(cp.oversized_chunks))
    else:
        t_plan.add_row("Status", "Unavailable")
    c.print(t_plan)

    # 5. Performance & Metrics
    t_perf = Table(title="Model Request & Token Metrics", box=box.ROUNDED if style.use_panels else box.SIMPLE, show_header=False)
    t_perf.add_column("Metric", style="bold", no_wrap=True)
    t_perf.add_column("Value")
    t_perf.add_row("Total Requests", str(diagnostics.total_requests))
    t_perf.add_row("Total Latency", f"{diagnostics.total_latency_seconds:.2f}s")
    tot_p = f"{diagnostics.total_prompt_tokens:,}" if diagnostics.total_prompt_tokens is not None else "-"
    avg_p = f"{diagnostics.avg_prompt_tokens:.1f}" if diagnostics.avg_prompt_tokens is not None else "-"
    t_perf.add_row("Prompt Tokens", f"total {tot_p} | avg {avg_p}")
    tot_g = f"{diagnostics.total_generated_tokens:,}" if diagnostics.total_generated_tokens is not None else "-"
    avg_g = f"{diagnostics.avg_generated_tokens:.1f}" if diagnostics.avg_generated_tokens is not None else "-"
    t_perf.add_row("Generated Tokens", f"total {tot_g} | avg {avg_g}")
    rate = (
        f"{diagnostics.avg_tokens_per_second:.1f} tokens/s"
        if diagnostics.avg_tokens_per_second is not None
        else "-"
    )
    t_perf.add_row("Generation Rate", rate)
    t_perf.add_row("Ollama Stop Reasons", str(diagnostics.stop_reasons))
    c.print(t_perf)

    # 6. Per-Chunk Breakdown
    if diagnostics.chunk_requests:
        fits_note = "[green]Yes[/green]" if diagnostics.final_synthesis_fits_budget else "[bold red]No[/bold red]"
        t_chunks = Table(
            title=f"Per-Chunk Request Breakdown [dim](Passes: {len(diagnostics.reduction_passes)} | Fits Synthesis Budget: {fits_note})[/dim]",
            box=box.ROUNDED if style.use_panels else box.SIMPLE,
        )
        t_chunks.add_column("#", justify="right", style="bold")
        t_chunks.add_column("Type", style="cyan")
        t_chunks.add_column("Files", justify="right")
        t_chunks.add_column("Chars", justify="right")
        t_chunks.add_column("Lines", justify="right")
        t_chunks.add_column("Est. Tokens", justify="right")
        t_chunks.add_column("Prompt Tokens", justify="right")
        t_chunks.add_column("Gen. Tokens", justify="right")
        t_chunks.add_column("Latency", justify="right", style="green")

        for req in diagnostics.chunk_requests:
            fc = str(req.file_count) if req.file_count else "-"
            cc = f"{req.char_count:,}" if req.char_count else "-"
            lc = f"{req.line_count:,}" if req.line_count else "-"
            et = f"{req.estimated_tokens:,}" if req.estimated_tokens is not None else "-"
            pt = f"{req.prompt_tokens:,}" if req.prompt_tokens is not None else "-"
            gt = f"{req.generated_tokens:,}" if req.generated_tokens is not None else "-"
            lat = f"{req.latency_seconds:.2f}s"
            t_chunks.add_row(str(req.chunk_index), req.chunk_type, fc, cc, lc, et, pt, gt, lat)

        c.print(t_chunks)
    c.print("")
