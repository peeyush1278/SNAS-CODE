# main.py

import time
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass # Fallback for very old versions or restricted environments

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.live import Live

from config import MODEL_NAME
from utils import console
from tools import tools
from agent import SansAgent

def main():
    # Creative Edition Palette: Vibrant Peach (#FF8F70), Deep Charcoal, Soft White
    PEACH = "#FF8F70"
    
    style = Style.from_dict({
        'prompt': f'bold {PEACH}',
    })
    
    try:
        session = PromptSession(style=style)
        is_interactive = True
    except Exception:
        is_interactive = False
        console.print("[dim]No interactive console detected.[/dim]")

    from config import BRAIN_MODEL
    console.print()
    
    # Large Creative ASCII Banner
    ascii_art = f"""
[bold {PEACH}]   _____  ___   _   _  ____     ____  ___  ____  _____ [/bold {PEACH}]
[bold {PEACH}]  / ___/ / _ \ | \ | |/ ___/   / ___// _ \|  _ \| ____|[/bold {PEACH}]
[bold {PEACH}]  \___ \/ /_\ \|  \| |\___ \  | |   / / \ \ | | |  _|  [/bold {PEACH}]
[bold {PEACH}]  ___/ / /___/ | |\  | ___/ /  | |__/ /_/ / |_| | |___ [/bold {PEACH}]
[bold {PEACH}] /____/_/   \_\|_| \_|/____/   \____\____/|____/|_____|[/bold {PEACH}]
    """
    
    console.print(Align.center(ascii_art))
    console.print(Align.center(f"[black on {PEACH}]  > Strategic Orchestrator: SANS Edition  [/black on {PEACH}]"))
    console.print()
    
    # Initialization Sequence (Creativity)
    init_steps = [
        "● core systems online",
        "● neural weights loaded",
        "● agentic protocols active",
    ]
    with Live(auto_refresh=False) as live:
        for i in range(len(init_steps)):
            live.update(Align.center(Text("\n".join(init_steps[:i+1]), style="dim")), refresh=True)
            time.sleep(0.15)
    
    console.print()

    # Refined Capabilities Panel
    tools_table = Table(show_header=False, box=None, padding=(0, 2))
    tools_table.add_column(style=PEACH)
    tools_table.add_column(style="dim white")
    
    tool_icons = {
        "view_file": "view", "write_file": "edit", "list_dir": "list",
        "run_command": "exec", "delete_path": "rm", "search_code": "find",
        "run_in_new_terminal": "term", "read_website": "web", "search_internet": "search"
    }
    
    for t in tools[:9]:
        fn = t["function"]
        label = tool_icons.get(fn["name"], "tool")
        tools_table.add_row(f"[{label}]", fn["description"][:70].lower() + "...")
        
    console.print(Align.center(Panel(tools_table, border_style="dim", padding=(1, 2), subtitle=f"[dim]{BRAIN_MODEL}[/dim]")))
    console.print()

    agent = SansAgent()

    while True:
        try:
            if is_interactive:
                user_input = session.prompt("❯ ")
            else:
                user_input = input("❯ ")
            
            if not user_input.strip():
                continue
            if user_input.strip().lower() in ["/exit", "exit", "quit"]:
                break
        except (KeyboardInterrupt, EOFError):
            break

        agent.chat(user_input)

if __name__ == "__main__":
    main()
