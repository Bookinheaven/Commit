#!/usr/bin/env python3
import sys
from core import config, settings
from core.git_utils import (
    check_git_repo, get_staged_diff, get_staged_files, get_unstaged_files,
    stage_all, get_repo_root, commit_changes, push_changes, get_custom_rules
)
from core.ui import display_commit, display_staged_files, edit_in_editor, Theme, Spinner, Icons
from core.parser import split_diff_by_file, filter_noise_files, batch_file_diffs
from core.llm import check_ollama, generate_commit_message, summarize_diff_chunk
from core import history


def get_diff(raw_diff: str) -> str:
    """Return diff ready for the LLM, filtering noise files and using Map-Reduce for large diffs."""
    # Always filter lockfiles and noisy files first to save massive token overhead
    file_diffs = filter_noise_files(split_diff_by_file(raw_diff))
    filtered_diff = "".join(file_diffs)

    if len(filtered_diff) <= config.MAX_DIFF_CHARS:
        return filtered_diff

    Theme.print_warning(f"Large diff ({len(filtered_diff):,} chars). Switching to Map-Reduce mode...")

    batches = batch_file_diffs(file_diffs, config.MAX_DIFF_CHARS)
    Theme.print_info(f"Processing {len(batches)} chunk(s)...")

    summaries = []
    for i, batch in enumerate(batches, 1):
        with Spinner(f"Summarising chunk {i}/{len(batches)}..."):
            summary = summarize_diff_chunk(batch)
        summaries.append(summary)

    Theme.print_success("Map-Reduce complete.")
    return "COMBINED SUMMARY:\n\n" + "\n".join(summaries)


def main():
    try:
        # CLI history log shortcut
        if any(arg in sys.argv[1:] for arg in ("--history", "-l", "--log")):
            history.display_history()
            return

        # CLI settings shortcut
        if any(arg in sys.argv[1:] for arg in ("--settings", "-s", "--setup", "-c")):
            settings.interactive_settings()
            return

        # Check for first-time run configuration
        settings.initial_setup_if_needed()

        check_git_repo()

        # Fast local pre-checks with Auto-Stage prompt
        staged = get_staged_files()
        if not staged:
            unstaged = get_unstaged_files()
            if unstaged:
                Theme.print_warning(f"No staged changes found, but {len(unstaged)} modified/untracked file(s) exist.")
                for f in unstaged[:5]:
                    print(f"  {Theme.DIM}[{Icons.BULLET}]{Theme.RESET} {f}")
                if len(unstaged) > 5:
                    print(f"  {Theme.DIM}... and {len(unstaged) - 5} more file(s){Theme.RESET}")

                auto_stage = input(f"\n{Theme.BOLD}Stage all changes (git add -A)? [Y/n]:{Theme.RESET} ").strip().lower()
                if auto_stage in ("", "y", "yes"):
                    stage_all()
                    staged = get_staged_files()
                    Theme.print_success("Staged all changes.")
                else:
                    Theme.print_warning("No staged changes. Run 'git add' first.")
                    return
            else:
                Theme.print_warning("No staged changes. Run 'git add' first.")
                return

        raw = get_staged_diff()
        if not raw.strip():
            Theme.print_warning("No diff detected in staged changes (e.g. only untracked or empty files).")
            return

        display_staged_files(staged)

        # Check for repository-level .commitrules
        custom_rules = get_custom_rules()
        if custom_rules:
            Theme.print_info("Loaded custom rules from .commitrules.")

        # Verify Ollama is reachable before doing LLM-heavy work
        with Spinner("Checking Ollama..."):
            check_ollama()
        Theme.print_success("Ollama is running.")

        # Spinner around diff preparation if large
        diff = get_diff(raw)

        feedback = None
        temp = 0.1

        while True:
            spinner_msg = "Generating commit message..." if not feedback else "Regenerating commit message with feedback..."
            with Spinner(spinner_msg):
                title, description = generate_commit_message(
                    diff, feedback=feedback, temperature=temp, custom_rules=custom_rules
                )

            while True:
                display_commit(title, description)
                print(f"  {Theme.CYAN}[Y]{Theme.RESET} Commit")
                print(f"  {Theme.CYAN}[P]{Theme.RESET} Commit & Push")
                print(f"  {Theme.CYAN}[E]{Theme.RESET} Edit")
                print(f"  {Theme.CYAN}[R]{Theme.RESET} Regenerate")
                print(f"  {Theme.CYAN}[S]{Theme.RESET} Settings")
                print(f"  {Theme.CYAN}[N]{Theme.RESET} Cancel")

                choice = input(f"\n{Theme.BOLD}Choice:{Theme.RESET} ").strip().lower()

                if choice in ("y", "p"):
                    commit_changes(title, description)
                    history.save(get_repo_root(), title, description)
                    Theme.print_success("Committed!")

                    if choice == "p":
                        try:
                            with Spinner("Pushing to remote..."):
                                push_changes()
                            Theme.print_success("Pushed to remote successfully!")
                        except Exception as e:
                            Theme.print_error(f"Push failed: {e}")
                            Theme.print_info("You can push manually later with: git push")
                    return
                elif choice == "e":
                    title, description = edit_in_editor(title, description)
                elif choice == "r":
                    print(f"\n{Theme.DIM}Provide guidance (e.g. 'focus on bugfix', 'shorter bullets', 'use fix(auth)') or press Enter to retry as-is:{Theme.RESET}")
                    user_feedback = input(f"{Theme.BOLD}Feedback:{Theme.RESET} ").strip()
                    feedback = user_feedback if user_feedback else None
                    # If retrying without feedback, raise temperature to avoid identical output
                    temp = 0.7 if not feedback else 0.2
                    break  # back to outer loop to regenerate
                elif choice == "s":
                    settings.interactive_settings()
                    regen = input(f"\n{Theme.BOLD}Regenerate commit message with updated settings? (y/n):{Theme.RESET} ").strip().lower()
                    if regen == "y":
                        diff = get_diff(raw)
                        break
                elif choice == "n":
                    Theme.print_warning("Cancelled.")
                    return
                else:
                    Theme.print_error("Invalid choice. Use Y, P, E, R, S, or N.")

    except KeyboardInterrupt:
        print()
        Theme.print_warning("Cancelled by user.")
        sys.exit(0)
    except RuntimeError as e:
        Theme.print_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()