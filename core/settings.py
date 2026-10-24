import os
from . import config
from .llm import get_installed_models, pull_model
from .ui import Theme


def _explain_keep_alive(val: str) -> str:
    if val == "0m" or val == "0":
        return "Free RAM immediately"
    elif val == "5m":
        return "Standard (5 min idle unload)"
    elif val == "15m":
        return "Balanced (15 min idle unload)"
    elif val == "30m":
        return "Always Fast (30 min warm cache)"
    elif val == "-1":
        return "Never unload (Indefinite)"
    return f"Unload after {val}"


def initial_setup_if_needed() -> None:
    """Prompt the user for setup on first run if config.json does not exist."""
    if os.path.exists(config.CONFIG_PATH):
        return

    print(f"\n{Theme.BOLD}{Theme.BLUE}=== AI Commit - Quick Setup ==={Theme.RESET}")
    print(f"{Theme.DIM}Let's pick your default model and memory profile (press Enter for recommended defaults).{Theme.RESET}\n")

    cfg = dict(config.DEFAULT_CONFIG)

    # 1. Models
    installed = get_installed_models(cfg["ollama_url"])
    installed_names = [m["name"] for m in installed]

    print(f"{Theme.BOLD}1. Select AI Model:{Theme.RESET}")
    if "qwen2.5-coder:7b" in installed_names:
        print(f"   {Theme.GREEN}[+] Recommended model 'qwen2.5-coder:7b' is installed!{Theme.RESET}")
        choice = input(f"   Use 'qwen2.5-coder:7b'? [Y/n]: ").strip().lower()
        if choice == "n":
            manage_models_menu(cfg)
    elif installed:
        print(f"   Found {len(installed)} installed model(s):")
        for i, m in enumerate(installed, 1):
            print(f"   [{i}] {m['name']} ({m['size_gb']:.1f} GB)")
        c = input(f"   Select model [1-{len(installed)}, Enter for 1]: ").strip()
        if c.isdigit() and 1 <= int(c) <= len(installed):
            cfg["model"] = installed[int(c) - 1]["name"]
        else:
            cfg["model"] = installed[0]["name"]
    else:
        print(f"   {Theme.YELLOW}No models found in Ollama yet.{Theme.RESET}")
        pull = input(f"   Download recommended 'qwen2.5-coder:7b' (4.7 GB)? [Y/n]: ").strip().lower()
        if pull != "n":
            if pull_model("qwen2.5-coder:7b", cfg["ollama_url"]):
                cfg["model"] = "qwen2.5-coder:7b"

    # 2. Memory
    print(f"\n{Theme.BOLD}2. Memory Profile:{Theme.RESET}")
    print(f"   [1] Free RAM Immediately (0m)   - Frees GPU/RAM right after commit")
    print(f"   [2] Standard (5m)               - Frees RAM after 5 min idle (Default)")
    print(f"   [3] Always Fast (30m)           - Warm cache for instant repeat commits")
    mem = input(f"   Select memory profile [1-3, Enter for Standard]: ").strip()
    mem_map = {"1": "0m", "2": "5m", "3": "30m"}
    if mem in mem_map:
        cfg["keep_alive"] = mem_map[mem]

    config.save_config(cfg)
    print(f"\n{Theme.GREEN}[+] Setup saved to config.json! You can change this anytime with 'commit --settings'.{Theme.RESET}\n")


def manage_models_menu(cfg: dict) -> None:
    """Unified, friendly model selection and downloading menu."""
    while True:
        installed = get_installed_models(cfg["ollama_url"])
        installed_names = [m["name"] for m in installed]

        Theme.print_header("Model Selection")
        print(f"  Current Active Model: {Theme.BOLD}{Theme.CYAN}{cfg.get('model')}{Theme.RESET}\n")

        options = []

        # Installed models
        if installed:
            print(f"  {Theme.BOLD}Installed on your computer:{Theme.RESET}")
            for m in installed:
                is_active = " *(active)*" if m["name"] == cfg.get("model") else ""
                tag = f"{Theme.GREEN}[ACTIVE]{Theme.RESET}" if is_active else ""
                idx = len(options) + 1
                options.append(("select", m["name"]))
                print(f"    [{idx}] {m['name']} ({m['size_gb']:.1f} GB) {tag}")
            print()

        # Available to download
        print(f"  {Theme.BOLD}Available to download (one-click):{Theme.RESET}")
        for m_name, m_size, m_desc in config.RECOMMENDED_MODELS:
            if m_name not in installed_names:
                idx = len(options) + 1
                options.append(("download", m_name))
                print(f"    [{idx}] {m_name} ({m_size}) - {Theme.DIM}{m_desc}{Theme.RESET}")

        idx_custom = len(options) + 1
        options.append(("custom", ""))
        print(f"    [{idx_custom}] Download custom model name...")

        print(f"\n  {Theme.CYAN}[B]{Theme.RESET} Back (keep current model)")

        choice = input(f"\n{Theme.BOLD}Select an option [1-{len(options)}, B to cancel]:{Theme.RESET} ").strip().lower()

        if choice in ("b", "q", "0", ""):
            break

        if choice.isdigit():
            c_int = int(choice)
            if 1 <= c_int <= len(options):
                action, model_target = options[c_int - 1]
                if action == "select":
                    cfg["model"] = model_target
                    config.save_config(cfg)
                    Theme.print_success(f"Switched active model to '{model_target}'.")
                    break
                elif action == "download":
                    confirm = input(f"\nDownload '{model_target}' from Ollama? [Y/n]: ").strip().lower()
                    if confirm != "n":
                        if pull_model(model_target, cfg["ollama_url"]):
                            cfg["model"] = model_target
                            config.save_config(cfg)
                            Theme.print_success(f"Downloaded and set active model to '{model_target}'.")
                            break
                elif action == "custom":
                    custom_name = input(f"\n{Theme.BOLD}Enter exact model name from ollama.com (e.g. 'mistral', or Enter to cancel):{Theme.RESET} ").strip()
                    if custom_name:
                        if pull_model(custom_name, cfg["ollama_url"]):
                            cfg["model"] = custom_name
                            config.save_config(cfg)
                            Theme.print_success(f"Downloaded and set active model to '{custom_name}'.")
                            break
        else:
            Theme.print_error("Invalid selection. Enter a number or 'B' to go back.")


def manage_memory_menu(cfg: dict) -> None:
    """Friendly memory profile selection menu."""
    while True:
        Theme.print_header("Memory & RAM Settings")
        print(f"  Current Setting: {Theme.BOLD}{Theme.CYAN}{_explain_keep_alive(cfg.get('keep_alive'))}{Theme.RESET}\n")

        print(f"  Choose how Ollama manages memory on your computer:\n")
        print(f"    {Theme.CYAN}[1]{Theme.RESET} {Theme.BOLD}Low RAM / Game Mode (0m){Theme.RESET}")
        print(f"        {Theme.DIM}Frees all VRAM & system memory immediately after each commit.{Theme.RESET}\n")

        print(f"    {Theme.CYAN}[2]{Theme.RESET} {Theme.BOLD}Standard (5m) - Recommended{Theme.RESET}")
        print(f"        {Theme.DIM}Keeps model ready for 5 minutes of idle time, then frees memory.{Theme.RESET}\n")

        print(f"    {Theme.CYAN}[3]{Theme.RESET} {Theme.BOLD}Balanced (15m){Theme.RESET}")
        print(f"        {Theme.DIM}Keeps model loaded during active coding sessions with short pauses.{Theme.RESET}\n")

        print(f"    {Theme.CYAN}[4]{Theme.RESET} {Theme.BOLD}Always Fast (30m){Theme.RESET}")
        print(f"        {Theme.DIM}Retains model in memory for 30 mins for instant repeat commits.{Theme.RESET}\n")

        print(f"    {Theme.CYAN}[5]{Theme.RESET} {Theme.BOLD}Custom Duration{Theme.RESET} (e.g. '10m', '1h', '-1' for indefinite)")
        print(f"    {Theme.CYAN}[B]{Theme.RESET} Back (keep current)")

        choice = input(f"\n{Theme.BOLD}Select profile [1-5, B to cancel]:{Theme.RESET} ").strip().lower()

        if choice in ("b", "q", "0", ""):
            break

        c_map = {"1": "0m", "2": "5m", "3": "15m", "4": "30m"}
        if choice in c_map:
            cfg["keep_alive"] = c_map[choice]
            config.save_config(cfg)
            Theme.print_success(f"Memory profile set to: {_explain_keep_alive(cfg['keep_alive'])}")
            break
        elif choice == "5":
            custom = input(f"{Theme.BOLD}Enter duration (e.g. '10m', '1h', or Enter to cancel):{Theme.RESET} ").strip()
            if custom:
                cfg["keep_alive"] = custom
                config.save_config(cfg)
                Theme.print_success(f"Memory duration set to '{custom}'.")
                break
        else:
            Theme.print_error("Invalid selection. Enter 1-5 or 'B' to go back.")


def manage_advanced_menu(cfg: dict) -> None:
    """Advanced developer settings menu."""
    while True:
        Theme.print_header("Advanced Settings")
        print(f"  {Theme.CYAN}[1]{Theme.RESET} Ollama API URL:   {Theme.DIM}{cfg.get('ollama_url')}{Theme.RESET}")
        print(f"  {Theme.CYAN}[2]{Theme.RESET} Max Diff Size:    {Theme.DIM}{cfg.get('max_diff_chars'):,} characters{Theme.RESET}")
        print(f"  {Theme.CYAN}[3]{Theme.RESET} Reset All Settings to Factory Defaults")
        print(f"  {Theme.CYAN}[B]{Theme.RESET} Back")

        choice = input(f"\n{Theme.BOLD}Select option [1-3, B to back]:{Theme.RESET} ").strip().lower()

        if choice in ("b", "q", "0", ""):
            break

        if choice == "1":
            new_url = input(f"\nEnter Ollama API URL [{cfg['ollama_url']}] (or Enter to cancel): ").strip()
            if new_url:
                cfg["ollama_url"] = new_url
                config.save_config(cfg)
                Theme.print_success(f"Ollama URL updated to '{new_url}'.")
        elif choice == "2":
            new_size = input(f"\nEnter Max Diff Characters [{cfg['max_diff_chars']}] (or Enter to cancel): ").strip()
            if new_size.isdigit():
                cfg["max_diff_chars"] = int(new_size)
                config.save_config(cfg)
                Theme.print_success(f"Max diff size updated to {int(new_size):,} chars.")
        elif choice == "3":
            confirm = input(f"\n{Theme.YELLOW}Reset all settings to defaults? (y/N):{Theme.RESET} ").strip().lower()
            if confirm == "y":
                cfg.clear()
                cfg.update(config.DEFAULT_CONFIG)
                config.save_config(cfg)
                Theme.print_success("All settings reset to defaults.")
                break


def interactive_settings() -> None:
    """Main settings hub: clean, friendly, and intuitive."""
    from .history import display_history
    cfg = config.load_config()

    while True:
        try:
            Theme.print_header("Settings")
            print(f"  {Theme.CYAN}[1]{Theme.RESET} AI Model:          {Theme.BOLD}{cfg.get('model')}{Theme.RESET} (Change or download)")
            print(f"  {Theme.CYAN}[2]{Theme.RESET} Memory & RAM:      {Theme.BOLD}{_explain_keep_alive(cfg.get('keep_alive'))}{Theme.RESET}")
            print(f"  {Theme.CYAN}[3]{Theme.RESET} Commit History:    {Theme.DIM}View recent commit history log{Theme.RESET}")
            print(f"  {Theme.CYAN}[4]{Theme.RESET} Advanced:          {Theme.DIM}Ollama URL, Diff limits, Factory reset{Theme.RESET}")
            print(f"  {Theme.CYAN}[B]{Theme.RESET} Done / Back to Commit")

            choice = input(f"\n{Theme.BOLD}Select [1-4, or B to exit]:{Theme.RESET} ").strip().lower()

            if choice in ("b", "q", "0", ""):
                config.save_config(cfg)
                break
            elif choice == "1":
                manage_models_menu(cfg)
            elif choice == "2":
                manage_memory_menu(cfg)
            elif choice == "3":
                display_history()
            elif choice == "4":
                manage_advanced_menu(cfg)
            else:
                Theme.print_error("Invalid option. Choose 1, 2, 3, 4, or B.")
        except KeyboardInterrupt:
            print()
            config.save_config(cfg)
            break
