import os
import sys
import tempfile
import subprocess
import threading
import itertools
import time
from .git_utils import run_git

class Theme:
    # Colors
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    DIM = '\033[2m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    @staticmethod
    def print_header(text):
        print(f"\n{Theme.BOLD}{Theme.BLUE}=== {text.upper()} ==={Theme.RESET}")
        
    @staticmethod
    def print_success(text):
        print(f"{Theme.GREEN}✔ {text}{Theme.RESET}")
        
    @staticmethod
    def print_info(text):
        print(f"{Theme.CYAN}ℹ {text}{Theme.RESET}")
        
    @staticmethod
    def print_warning(text):
        print(f"{Theme.YELLOW}⚠ {text}{Theme.RESET}")
        
    @staticmethod
    def print_error(text):
        print(f"{Theme.RED}✖ {text}{Theme.RESET}")
        
    @staticmethod
    def print_dim(text):
        print(f"{Theme.DIM}{text}{Theme.RESET}")

class Spinner:
    """Context manager that shows an animated spinner on one line."""
    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = ""):
        self.message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            print(f"\r{Theme.CYAN}{frame} {self.message}{Theme.RESET}",
                  end="", flush=True)
            time.sleep(0.08)
        # Clear the spinner line
        print(f"\r{' ' * (len(self.message) + 4)}\r", end="", flush=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()


# For Windows we need to enable ANSI colors
if os.name == 'nt':
    os.system('color')

def display_staged_files(files: list[str]) -> None:
    """Print a compact list of staged files before generation."""
    Theme.print_header("Staged Files")
    for f in files:
        print(f"  {Theme.DIM}·{Theme.RESET} {f}")
    print()


def display_commit(title, description):
    Theme.print_header("Commit Preview")
    print(f"{Theme.BOLD}Title:{Theme.RESET}\n{Theme.CYAN}{title}{Theme.RESET}\n")
    print(f"{Theme.BOLD}Description:{Theme.RESET}\n{description}\n")
    print(f"{Theme.DIM}─" * 50 + Theme.RESET)


def edit_in_editor(title, description):
    content = f"{title}\n\n{description}"
    
    fd, path = tempfile.mkstemp(suffix=".txt", text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
        
    editor = os.environ.get('EDITOR', 'notepad' if os.name == 'nt' else 'nano')
    subprocess.run([editor, path])
    
    with open(path, 'r', encoding='utf-8') as f:
        new_content = f.read().strip()
        
    os.remove(path)
    
    if not new_content:
        return title, description
        
    lines = new_content.splitlines()
    new_title = lines[0].strip()
    new_desc = "\n".join(lines[1:]).strip()
    
    return new_title, new_desc
