import sys
from core.config import MAX_DIFF_CHARS
from core.git_utils import check_git_repo, get_staged_diff, get_staged_files, get_repo_root, commit_changes
from core.ui import display_commit, display_staged_files, edit_in_editor, Theme, Spinner
from core.parser import split_diff_by_file, filter_noise_files, batch_file_diffs
from core.llm import check_ollama, generate_title, generate_description, summarize_diff_chunk
from core import history


def get_diff(raw_diff: str) -> str:
    """Return diff ready for the LLM, using Map-Reduce for large diffs."""
    if len(raw_diff) <= MAX_DIFF_CHARS:
        return raw_diff

    Theme.print_warning(f"Large diff ({len(raw_diff):,} chars). Switching to Map-Reduce mode...")

    file_diffs = filter_noise_files(split_diff_by_file(raw_diff))
    batches = batch_file_diffs(file_diffs, MAX_DIFF_CHARS)
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
        check_git_repo()

        # Verify Ollama is reachable before doing anything
        with Spinner("Checking Ollama..."):
            check_ollama()
        Theme.print_success("Ollama is running.")

        # Show staged files upfront
        staged = get_staged_files()
        if not staged:
            Theme.print_warning("No staged changes. Run 'git add' first.")
            return
        display_staged_files(staged)

        raw = get_staged_diff()
        # Spinner around LLM-heavy work
        diff = get_diff(raw)

        while True:
            with Spinner("Generating commit message..."):
                title = generate_title(diff)
                description = generate_description(diff, title)

            while True:
                display_commit(title, description)
                print(f"  {Theme.CYAN}[Y]{Theme.RESET} Commit")
                print(f"  {Theme.CYAN}[E]{Theme.RESET} Edit")
                print(f"  {Theme.CYAN}[R]{Theme.RESET} Regenerate")
                print(f"  {Theme.CYAN}[N]{Theme.RESET} Cancel")

                choice = input(f"\n{Theme.BOLD}Choice:{Theme.RESET} ").strip().lower()

                if choice == "y":
                    commit_changes(title, description)
                    # Feature 12: Save to local history log
                    history.save(get_repo_root(), title, description)
                    Theme.print_success("Committed!")
                    return
                elif choice == "e":
                    title, description = edit_in_editor(title, description)
                elif choice == "r":
                    break  # back to outer loop to regenerate
                elif choice == "n":
                    Theme.print_warning("Cancelled.")
                    return
                else:
                    Theme.print_error("Invalid choice. Use Y, E, R, or N.")

    except RuntimeError as e:
        Theme.print_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()