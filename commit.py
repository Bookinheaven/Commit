import sys
from core.config import MAX_DIFF_CHARS
from core.git_utils import check_git_repo, get_staged_diff, commit_changes
from core.ui import display_commit, edit_in_editor, Theme
from core.parser import split_diff_by_file, filter_noise_files, batch_file_diffs
from core.llm import generate_title, generate_description, summarize_diff_chunk

def main():
    try:
        check_git_repo()

        diff = get_staged_diff()

        if not diff.strip():
            Theme.print_warning("No staged changes found. Please stage files using 'git add' first.")
            return

        if len(diff) > MAX_DIFF_CHARS:
            Theme.print_warning(f"Large diff detected ({len(diff):,} characters). Initiating Map-Reduce summarization...")
            
            file_diffs = split_diff_by_file(diff)
            file_diffs = filter_noise_files(file_diffs)
            
            batches = batch_file_diffs(file_diffs, MAX_DIFF_CHARS)
            
            Theme.print_info(f"Split diff into {len(batches)} optimal chunk(s). Summarizing chunks...")
            
            summaries = []
            for i, batch in enumerate(batches, 1):
                Theme.print_dim(f"  -> Analyzing chunk {i}/{len(batches)}...")
                summary = summarize_diff_chunk(batch)
                summaries.append(summary)
                
            Theme.print_success("Map-Reduce complete.")
            
            diff = "COMBINED SUMMARY OF LARGE DIFF:\n\n" + "\n".join(summaries)
        else:
            Theme.print_info("Analyzing staged changes...")

        Theme.print_info("Generating commit title...")

        while True:
            title = generate_title(diff)

            Theme.print_info("Generating commit description...")
            description = generate_description(diff, title)

            while True:
                display_commit(title, description)

                print(f"  {Theme.CYAN}[Y]{Theme.RESET} Commit")
                print(f"  {Theme.CYAN}[E]{Theme.RESET} Edit message")
                print(f"  {Theme.CYAN}[R]{Theme.RESET} Regenerate")
                print(f"  {Theme.CYAN}[N]{Theme.RESET} Cancel")

                choice = input(f"\n{Theme.BOLD}Choice:{Theme.RESET} ").strip().lower()

                if choice == "y":
                    commit_changes(title, description)
                    Theme.print_success("Commit created successfully!")
                    return
                elif choice == "e":
                    title, description = edit_in_editor(title, description)
                elif choice == "r":
                    Theme.print_info("Regenerating...")
                    break
                elif choice == "n":
                    Theme.print_warning("Cancelled.")
                    return
                else:
                    Theme.print_error("Invalid choice.")

    except RuntimeError as e:
        Theme.print_error(str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()