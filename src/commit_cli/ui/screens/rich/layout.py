"""Rich appearance layout, styling, animations, and FormattedText token rendering."""

import textwrap
import time
from typing import Any, Optional

from prompt_toolkit.utils import get_cwidth

from commit_cli.models import CommitMessage
from commit_cli.ui.prompts import MainMenuChoice
from commit_cli.ui.render import format_duration
from commit_cli.ui.screens.shared.terminal import is_terminal_too_small


def get_str_width(s: str) -> int:
    """Return visible terminal character column width of a string."""
    return sum(get_cwidth(ch) for ch in s)


def render_rich_size_warning(w: int, h: int, no_color: bool = False) -> list[tuple[str, str]]:
    """Render terminal size warning box for Rich appearance."""
    box_style = "fg:magenta" if not no_color else ""
    lines: list[tuple[str, str]] = []
    lines.append((box_style, "╭─ Warning " + "─" * max(0, w - 2 - len("─ Warning ")) + "╮\n"))
    inner_w = max(1, w - 2)
    inner_h = max(1, h - 2)
    msg_lines = [
        "",
        f"  Terminal size too small ({w}x{h}).",
        "  Minimum required: 50x18.",
        "  Please resize your terminal window.",
        "",
        "  q Quit",
    ]
    pad_needed = inner_h - len(msg_lines)
    if pad_needed > 0:
        msg_lines.extend([""] * pad_needed)
    msg_lines = msg_lines[:inner_h]
    for row in msg_lines:
        vis = row[:inner_w]
        pad = " " * (inner_w - len(vis))
        lines.append((box_style, "│"))
        lines.append(("", vis + pad))
        lines.append((box_style, "│\n"))
    lines.append((box_style, "╰" + "─" * max(0, w - 2) + "╯"))
    return lines


def render_rich_menu_tokens(
    has_staged: bool,
    options: list[tuple[str, MainMenuChoice]],
    selected_idx: int,
    repo_state: Optional[Any],
    diff: Optional[Any],
    cfg: Optional[Any],
    w: int,
    h: int,
    no_color: bool = False,
) -> list[tuple[str, str]]:
    """Build tokens for the Rich full-screen initial selection screen."""
    if is_terminal_too_small(w, h, 50, 18):
        return render_rich_size_warning(w, h, no_color)

    inner_w = w - 2
    inner_h = h - 2
    border_style = "fg:magenta" if not no_color else ""
    sec_hdr_style = "bold fg:magenta" if not no_color else "bold"
    footer_style = "fg:gray" if not no_color else "dim"
    # Subtle pulsing accent animation on header
    if not no_color:
        anim_idx = int(time.monotonic() * 3) % 4
        accent_glyph = ["◆", "◇", "◈", "◇"][anim_idx]
        glyph_style = ["fg:magenta bold", "fg:#e066ff bold", "fg:cyan bold", "fg:#e066ff bold"][anim_idx]
        title_style = "bold fg:magenta"
    else:
        accent_glyph = "◆"
        glyph_style = "bold"
        title_style = "bold"
    # Dynamic spacing flags
    has_model_blank = inner_h >= 22
    has_div_blank = inner_h >= 21
    has_staged_blank = inner_h >= 20
    has_files_blank = inner_h >= 19
    # Rounded top border
    dashes_count = max(0, inner_w - 11)
    top_tokens: list[tuple[str, str]] = [
        (border_style, "╭─ "),
        (glyph_style, f"{accent_glyph} "),
        (title_style, "COMMIT"),
        (border_style, " " + "─" * dashes_count + "╮\n"),
    ]
    content_rows: list[list[tuple[str, str]]] = []
    # Row 1: Repository & Branch
    repo_name = "Commit"
    branch_str = "main"
    if repo_state is not None:
        repo_name = repo_state.root.name if (repo_state.root and repo_state.root.name) else "Commit"
        if repo_state.head_commit is None and (repo_state.is_detached or not repo_state.branch):
            branch_str = "initial commit"
        elif repo_state.is_detached:
            head_short = repo_state.head_commit[:7] if repo_state.head_commit else "unknown"
            branch_str = f"Detached HEAD ({head_short})"
        elif repo_state.branch:
            branch_str = repo_state.branch
        else:
            branch_str = "initial commit"
    left_prefix = "  Repository: "
    right_prefix = "Branch: "
    right_suffix = "  "
    right_text_len = len(right_prefix) + len(branch_str) + len(right_suffix)
    left_prefix_len = len(left_prefix)
    max_repo_len = max(5, inner_w - left_prefix_len - right_text_len - 2)
    if len(repo_name) > max_repo_len:
        repo_name = repo_name[: max(1, max_repo_len - 3)] + "..."
    left_full_len = left_prefix_len + len(repo_name)
    spacing = max(1, inner_w - left_full_len - right_text_len)
    content_rows.append([
        ("dim" if not no_color else "", left_prefix),
        ("bold", repo_name),
        ("", " " * spacing),
        ("dim" if not no_color else "", right_prefix),
        ("bold fg:cyan" if not no_color else "bold", branch_str),
        ("", right_suffix),
    ])
    # Row 2: Model and Provider
    model_name = cfg.model if cfg and getattr(cfg, "model", None) else "qwen2.5:7b"
    content_rows.append([
        ("dim" if not no_color else "", "  Model: "),
        ("bold fg:cyan" if not no_color else "bold", model_name),
        ("dim" if not no_color else "", " · Ollama (Local)"),
    ])
    if has_model_blank:
        content_rows.append([])
    # STAGED CHANGES Section
    content_rows.append([(sec_hdr_style, "  STAGED CHANGES")])
    diff_obj = diff if diff is not None else None
    f_count = len(diff_obj.files) if diff_obj and getattr(diff_obj, "files", None) else 0
    if f_count > 0:
        f_word = "file" if f_count == 1 else "files"
        ins_count = getattr(diff_obj, "total_additions", 0)
        del_count = getattr(diff_obj, "total_deletions", 0)
        ins_word = "insertion" if ins_count == 1 else "insertions"
        del_word = "deletion" if del_count == 1 else "deletions"
        content_rows.append([
            ("bold", f"  {f_count:,} {f_word} changed"),
            ("", "       "),
            ("fg:green bold" if not no_color else "", f"+{ins_count:,} {ins_word}"),
            ("", "       "),
            ("fg:red bold" if not no_color else "", f"-{del_count:,} {del_word}"),
        ])
        status_counts = [
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "A"), "added", "fg:green"),
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "M"), "modified", "fg:yellow"),
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "D"), "deleted", "fg:red"),
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "R"), "renamed", "fg:cyan"),
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "C"), "copied", "fg:magenta"),
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "T"), "type changed", "fg:blue"),
            (sum(1 for x in diff_obj.files if getattr(getattr(x, "status", None), "value", None) == "U"), "unmerged", "fg:red"),
        ]
        non_zero = [(cnt, label, col) for cnt, label, col in status_counts if cnt > 0]
        if non_zero:
            bk_tokens: list[tuple[str, str]] = [("", "  ")]
            for idx, (cnt, label, col) in enumerate(non_zero):
                if idx > 0:
                    bk_tokens.append(("dim" if not no_color else "", " · "))
                bk_tokens.append((col if not no_color else "", f"{cnt:,} {label}"))
            content_rows.append(bk_tokens)
        else:
            content_rows.append([("dim" if not no_color else "", "  0 changes")])
    else:
        content_rows.append([("dim" if not no_color else "", "  No staged changes.")])
        content_rows.append([("dim" if not no_color else "", "  Stage changes using 'git add <files>' to generate a commit.")])
        content_rows.append([("dim" if not no_color else "", "  0 files changed       +0 insertions       -0 deletions")])
    if has_staged_blank:
        content_rows.append([])
    # FILES Section
    content_rows.append([(sec_hdr_style, "  FILES")])
    if f_count > 0:
        status_styles = {
            "A": "fg:green",
            "M": "fg:yellow",
            "D": "fg:red",
            "R": "fg:cyan",
            "C": "fg:magenta",
            "T": "fg:blue",
            "U": "fg:red",
        }
        for f in diff_obj.files[:3]:
            s_char = getattr(getattr(f, "status", None), "value", "M")
            col_style = status_styles.get(s_char, "") if not no_color else ""
            p_str = getattr(f, "path", str(f))
            max_p_len = inner_w - 10
            if len(p_str) > max_p_len and max_p_len > 5:
                p_str = "..." + p_str[-(max_p_len - 3):]
            content_rows.append([
                ("", "    "),
                (col_style, s_char),
                ("", f"  {p_str}"),
            ])
        if f_count > 3:
            rem = f_count - 3
            content_rows.append([
                ("dim" if not no_color else "", f"       ... +{rem:,} more files")
            ])
    else:
        content_rows.append([("dim" if not no_color else "", "    (no files staged)")])
    if has_files_blank:
        content_rows.append([])
    # ACTIONS Section
    content_rows.append([(sec_hdr_style, "  ACTIONS")])
    for i, (label, _) in enumerate(options):
        if i == selected_idx:
            pointer = "> " if no_color else "❯ "
            sel_style = "bold" if no_color else "bold fg:magenta"
            content_rows.append([
                (sel_style, f"  {pointer}{label}")
            ])
        else:
            content_rows.append([
                ("", f"    {label}")
            ])
    footer_tokens = [(footer_style, "  ↑/↓ Navigate     Enter Select     q Quit")]
    if len(content_rows) + 1 > inner_h:
        content_rows = content_rows[: max(0, inner_h - 1)]
    pad_needed = max(0, inner_h - len(content_rows) - 1)
    final_rows = content_rows + [[] for _ in range(pad_needed)] + [footer_tokens]
    final_rows = final_rows[:inner_h]
    out_tokens: list[tuple[str, str]] = []
    out_tokens.extend(top_tokens)
    for row in final_rows:
        vis_w = sum(get_str_width(text) for _, text in row)
        line_toks: list[tuple[str, str]] = [(border_style, "│")]
        if vis_w > inner_w:
            curr = 0
            for style, text in row:
                t_w = get_str_width(text)
                if curr + t_w <= inner_w:
                    line_toks.append((style, text))
                    curr += t_w
                else:
                    rem = inner_w - curr
                    if rem > 0:
                        clipped = ""
                        for ch in text:
                            ch_w = get_cwidth(ch)
                            if get_str_width(clipped) + ch_w <= rem:
                                clipped += ch
                            else:
                                break
                        if clipped:
                            line_toks.append((style, clipped))
                            curr += get_str_width(clipped)
                    break
            pad = inner_w - curr
            if pad > 0:
                line_toks.append(("", " " * pad))
        else:
            line_toks.extend(row)
            pad = inner_w - vis_w
            if pad > 0:
                line_toks.append(("", " " * pad))
        line_toks.append((border_style, "│\n"))
        out_tokens.extend(line_toks)
    bot_line = "╰" + "─" * max(0, w - 2) + "╯"
    out_tokens.append((border_style, bot_line))
    return out_tokens


def render_rich_guided_tokens(
    app_state: str,
    candidate_msg: Optional[CommitMessage],
    snapshot: Optional[Any],
    repo_state: Optional[Any],
    cfg: Optional[Any],
    is_generating: bool,
    start_time: float,
    phase_desc: str,
    cur_chunk: int,
    tot_chunks: int,
    review_scroll_offset: int = 0,
    gen_duration: Optional[float] = None,
    regeneration_error: Optional[str] = None,
    spinner_frames: Optional[list[str]] = None,
    w: int = 80,
    h: int = 24,
    no_color: bool = False,
    diff_scroll_offset: int = 0,
) -> list[tuple[str, str]]:
    """Build tokens for the Rich full-screen generation and review views."""
    if spinner_frames is None:
        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    if is_terminal_too_small(w, h, 50, 18):
        return render_rich_size_warning(w, h, no_color)

    inner_w = w - 2
    inner_h = h - 2
    border_style = "fg:magenta" if not no_color else ""
    sec_hdr_style = "bold fg:magenta" if not no_color else "bold"
    footer_style = "fg:gray" if not no_color else "dim"

    diff_obj = snapshot.diff if snapshot else None
    f_count = len(diff_obj.files) if diff_obj and getattr(diff_obj, "files", None) else 0
    f_word = "file" if f_count == 1 else "files"
    ins_count = getattr(diff_obj, "total_additions", 0) if diff_obj else 0
    del_count = getattr(diff_obj, "total_deletions", 0) if diff_obj else 0
    # Header with title and decorative borders
    top_title = "Commit" if app_state == "generating" else "Commit Preview"
    max_title_len = max(4, inner_w - 6)
    if len(top_title) > max_title_len:
        top_title = top_title[:max_title_len]
    title_width = len(top_title) + 2
    top_left_dashes = max(1, (inner_w - title_width) // 2)
    top_right_dashes = max(1, inner_w - title_width - top_left_dashes)
    top_tokens = [
        (border_style, "╭" + "─" * top_left_dashes + " "),
        ("bold fg:cyan" if not no_color else "bold", top_title),
        (border_style, " " + "─" * top_right_dashes + "╮\n"),
    ]
    # Stable Header rows
    repo_name = "Commit"
    branch_str = "main"
    if repo_state is not None:
        repo_name = repo_state.root.name if (repo_state.root and repo_state.root.name) else "Commit"
        if repo_state.head_commit is None and (repo_state.is_detached or not repo_state.branch):
            branch_str = "initial commit"
        elif repo_state.is_detached:
            head_short = repo_state.head_commit[:7] if repo_state.head_commit else "unknown"
            branch_str = f"Detached HEAD ({head_short})"
        elif repo_state.branch:
            branch_str = repo_state.branch
        else:
            branch_str = "initial commit"
    left_prefix = f"  {repo_name} / {branch_str}"
    model_name = cfg.model if cfg and getattr(cfg, "model", None) else "qwen2.5:7b"
    right_prefix = f"{model_name} (Local)  "
    max_left = max(5, inner_w - len(right_prefix) - 2)
    if len(left_prefix) > max_left:
        left_prefix = left_prefix[: max(1, max_left - 3)] + "..."
    sp = max(1, inner_w - len(left_prefix) - len(right_prefix))
    content_rows: list[list[tuple[str, str]]] = []
    content_rows.append([])
    content_rows.append([
        ("bold", left_prefix),
        ("", " " * sp),
        ("dim" if not no_color else "", right_prefix),
    ])
    content_rows.append([])
    # Embedded section divider for staged changes
    sc_title = "STAGED CHANGES"
    div_len = max(5, inner_w - len(sc_title) - 8)
    content_rows.append([
        ("fg:gray" if not no_color else "dim", "  ─── "),
        (sec_hdr_style, sc_title),
        ("fg:gray" if not no_color else "dim", " " + "─" * div_len),
    ])
    ins_word = "insertion" if ins_count == 1 else "insertions"
    del_word = "deletion" if del_count == 1 else "deletions"
    if f_count > 0:
        c_line = f"  {f_count:,} {f_word} changed       +{ins_count:,} {ins_word}       -{del_count:,} {del_word}"
        if len(c_line) <= inner_w - 2:
            content_rows.append([
                ("bold", f"  {f_count:,} {f_word} changed"),
                ("", "       "),
                ("fg:green bold" if not no_color else "", f"+{ins_count:,} {ins_word}"),
                ("", "       "),
                ("fg:red bold" if not no_color else "", f"-{del_count:,} {del_word}"),
            ])
        else:
            content_rows.append([
                ("bold", f"  {f_count:,} {f_word} changed"),
                ("dim" if not no_color else "", " ("),
                ("fg:green" if not no_color else "", f"+{ins_count:,}"),
                ("dim" if not no_color else "", ", "),
                ("fg:red" if not no_color else "", f"-{del_count:,}"),
                ("dim" if not no_color else "", ")"),
            ])
    else:
        content_rows.append([("dim" if not no_color else "", "  0 files changed  (+0, -0)")])
    content_rows.append([])
    if app_state == "generating":
        # Generation centerpiece
        content_rows.append([])
        gen_hdr = "GENERATING COMMIT MESSAGE"
        gh_pad = max(0, (inner_w - len(gen_hdr)) // 2)
        content_rows.append([
            ("", " " * gh_pad),
            ("bold fg:cyan" if not no_color else "bold", gen_hdr),
        ])
        content_rows.append([])
        elapsed_val = time.monotonic() - start_time
        spin_idx = int(elapsed_val * 6) % len(spinner_frames)
        spinner_char = spinner_frames[spin_idx]
        act_text = f"Processing"
        spin_block = f"{spinner_char} {act_text}"
        sb_pad = max(0, (inner_w - len(spin_block)) // 2)
        content_rows.append([
            ("", " " * sb_pad),
            ("bold fg:magenta" if not no_color else "bold", f"{spinner_char} "),
            ("bold", act_text),
        ])
        content_rows.append([])
        ph_pad = max(0, (inner_w - len(phase_desc)) // 2)
        content_rows.append([
            ("", " " * ph_pad),
            ("dim" if not no_color else "", phase_desc),
        ])
        content_rows.append([])
        if tot_chunks > 0:
            chunk_str = f"Chunk {cur_chunk} / {tot_chunks}"
            ch_pad = max(0, (inner_w - len(chunk_str)) // 2)
            content_rows.append([
                ("", " " * ch_pad),
                ("bold", chunk_str),
            ])
            bar_width = min(28, max(10, inner_w - 20))
            ratio = min(1.0, max(0.0, cur_chunk / tot_chunks))
            filled = int(ratio * bar_width)
            if filled < bar_width:
                bar_str = "━" * filled + "╺" + "━" * (bar_width - filled - 1)
            else:
                bar_str = "━" * bar_width
            b_pad = max(0, (inner_w - bar_width) // 2)
            content_rows.append([
                ("", " " * b_pad),
                ("fg:cyan bold" if not no_color else "bold", bar_str),
            ])
        else:
            content_rows.append([])
            content_rows.append([])
        content_rows.append([])
        elapsed_str = f"Elapsed {format_duration(elapsed_val)}"
        el_pad = max(0, (inner_w - len(elapsed_str)) // 2)
        content_rows.append([
            ("", " " * el_pad),
            ("fg:yellow bold" if not no_color else "dim", elapsed_str),
        ])
        footer_left = "  Map-Reduce Analysis"
        footer_right = "Working...  "
        f_sp = max(1, inner_w - len(footer_left) - len(footer_right))
        footer_row = [
            (footer_style, footer_left),
            ("", " " * f_sp),
            ("fg:cyan bold" if not no_color else "dim", footer_right),
        ]
        pad = inner_h - len(content_rows) - 1
        final_rows = content_rows + [[] for _ in range(max(0, pad))] + [footer_row]
    else:  # app_state == "review"
        content_rows.append([])
        content_rows.append([("bold fg:magenta" if not no_color else "bold", "  PROPOSED COMMIT MESSAGE")])
        content_rows.append([])

        max_content_w = max(20, inner_w - 6)
        all_review_lines: list[list[tuple[str, str]]] = []

        subj = candidate_msg.title() if candidate_msg else ""
        title_avail = max(10, max_content_w - 9)
        wrapped_title = textwrap.wrap(subj, width=title_avail) or [subj]
        all_review_lines.append([
            ("dim" if not no_color else "", "  Title: "),
            ("bold fg:cyan" if not no_color else "bold", wrapped_title[0]),
        ])
        for tl in wrapped_title[1:]:
            all_review_lines.append([
                ("", "         "),
                ("bold fg:cyan" if not no_color else "bold", tl),
            ])

        all_review_lines.append([])

        has_body = bool(candidate_msg and candidate_msg.body and candidate_msg.body.strip())
        all_review_lines.append([("dim" if not no_color else "", "  Description:")])

        if has_body and candidate_msg is not None and candidate_msg.body is not None:
            raw_body_lines = candidate_msg.body.strip().splitlines()
            for bl in raw_body_lines:
                stripped = bl.strip()
                if not stripped:
                    all_review_lines.append([])
                    continue
                if stripped.startswith(("-", "*", "•")):
                    b_content = stripped.lstrip("-*•").strip()
                    b_avail = max(10, max_content_w - 6)
                    wrapped_b = textwrap.wrap(b_content, width=b_avail) or [b_content]
                    all_review_lines.append([
                        ("bold fg:cyan" if not no_color else "", "    • "),
                        ("", wrapped_b[0]),
                    ])
                    for cont_l in wrapped_b[1:]:
                        all_review_lines.append([
                            ("", "      "),
                            ("", cont_l),
                        ])
                else:
                    t_avail = max(10, max_content_w - 4)
                    wrapped_t = textwrap.wrap(stripped, width=t_avail) or [stripped]
                    for tl in wrapped_t:
                        all_review_lines.append([
                            ("", "    "),
                            ("", tl),
                        ])
        else:
            all_review_lines.append([
                ("", "    "),
                ("dim" if not no_color else "", "(none)"),
            ])

        if candidate_msg and candidate_msg.breaking_change and candidate_msg.breaking_change.strip():
            all_review_lines.append([])
            bc_text = candidate_msg.breaking_change.strip()
            bc_avail = max(10, max_content_w - 18)
            wrapped_bc = textwrap.wrap(bc_text, width=bc_avail) or [bc_text]
            all_review_lines.append([
                ("bold fg:red" if not no_color else "bold", "  Breaking Change: "),
                ("", wrapped_bc[0]),
            ])
            for bcl in wrapped_bc[1:]:
                all_review_lines.append([
                    ("", "                   "),
                    ("", bcl),
                ])

        curr_len = len(content_rows)
        fixed_bottom_rows = 3  # duration_row, empty line, footer_row
        available_slots = max(1, inner_h - curr_len - fixed_bottom_rows)

        if len(all_review_lines) > available_slots:
            max_rev_scroll = max(0, len(all_review_lines) - available_slots + 1)
            review_scroll_offset = max(0, min(review_scroll_offset, max_rev_scroll))
            slice_lines = all_review_lines[review_scroll_offset : review_scroll_offset + available_slots - 1]
            rem_lines = len(all_review_lines) - (review_scroll_offset + len(slice_lines))
            content_rows.extend(slice_lines)
            content_rows.append([("dim" if not no_color else "", f"  ... ({rem_lines} more lines, ↑/↓ to scroll)")])
        else:
            content_rows.extend(all_review_lines)

        if regeneration_error:
            duration_row = [("fg:red bold" if not no_color else "bold", f"  [!] Regeneration failed: {regeneration_error}")]
        else:
            dur_text = format_duration(gen_duration if gen_duration is not None else 0.0)
            duration_row = [("dim" if not no_color else "", f"  Generated in {dur_text}")]

        footer_row = [
            ("", "  "),
            ("bold fg:magenta" if not no_color else "bold", "[Enter]"), ("", " Commit   "),
            ("bold fg:magenta" if not no_color else "bold", "[e]"), ("", " Edit   "),
            ("bold fg:magenta" if not no_color else "bold", "[r]"), ("", " Regenerate   "),
            ("bold fg:magenta" if not no_color else "bold", "[q]"), ("", " Quit"),
        ]

        pad = max(0, inner_h - len(content_rows) - fixed_bottom_rows)
        final_rows = content_rows + [[] for _ in range(pad)] + [duration_row, [], footer_row]

    final_rows = final_rows[:inner_h]
    out_tokens = []
    out_tokens.extend(top_tokens)
    for row in final_rows:
        vis_w = sum(get_str_width(text) for _, text in row)
        line_toks = [(border_style, "│")]
        if vis_w > inner_w:
            curr = 0
            for style, text in row:
                t_w = get_str_width(text)
                if curr + t_w <= inner_w:
                    line_toks.append((style, text))
                    curr += t_w
                else:
                    rem = inner_w - curr
                    if rem > 0:
                        clipped = ""
                        for ch in text:
                            ch_w = get_cwidth(ch)
                            if get_str_width(clipped) + ch_w <= rem:
                                clipped += ch
                            else:
                                break
                        if clipped:
                            line_toks.append((style, clipped))
                            curr += get_str_width(clipped)
                    break
            pad_s = inner_w - curr
            if pad_s > 0:
                line_toks.append(("", " " * pad_s))
        else:
            line_toks.extend(row)
            pad_s = inner_w - vis_w
            if pad_s > 0:
                line_toks.append(("", " " * pad_s))
        line_toks.append((border_style, "│\n"))
        out_tokens.extend(line_toks)
    bot_line = "╰" + "─" * max(0, w - 2) + "╯"
    out_tokens.append((border_style, bot_line))
    return out_tokens
