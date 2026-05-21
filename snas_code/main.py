# main.py

import time
import sys
import os
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass 

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.live import Live
from rich.syntax import Syntax

from .config import MODEL_NAME
from .utils import console, check_ollama_status
from .tools import tools
from .agent import SansAgent

class SansCompleter(Completer):
    def __init__(self):
        self.path_completer = PathCompleter(only_directories=False, expanduser=True)
        self.slash_commands = [
            "/help", "/reset", "/clear", "/model", "/models", "/history", "/compact", "/config", "/exit", "/quit"
        ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd in self.slash_commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
        else:
            for completion in self.path_completer.get_completions(document, complete_event):
                yield completion

def handle_slash_command(user_input: str, agent: SansAgent, session: PromptSession) -> bool:
    parts = user_input.strip().split()
    cmd = parts[0].lower()
    
    if cmd in ["/exit", "/quit"]:
        console.print("[bold red]Goodbye![/bold red]")
        return False
        
    elif cmd == "/help":
        table = Table(title="[bold #FF8F70]SANS CODE: Slash Commands[/bold #FF8F70]", box=None, padding=(0, 2))
        table.add_column("Command", style="bold cyan")
        table.add_column("Description", style="dim white")
        table.add_row("/help", "Show this help screen")
        table.add_row("/reset or /clear", "Reset conversational history/context")
        table.add_row("/model [brain] [worker]", "View or configure active local models")
        table.add_row("/models", "List installed Ollama models with sizes")
        table.add_row("/history", "View recent CLI command history")
        table.add_row("/compact", "Manually compress historical conversation context")
        table.add_row("/config", "Show active prompts and settings")
        table.add_row("/exit or /quit", "Exit SANS CODE CLI")
        console.print(Panel(table, border_style="#FF8F70"))
        
    elif cmd in ["/reset", "/clear"]:
        agent.history = [agent.history[0]]
        console.print("[green]✔ Chat history successfully reset to system prompt.[/green]")
        
    elif cmd == "/model":
        from . import config
        if len(parts) == 1:
            console.print(f"[bold #FF8F70]Active Models:[/bold #FF8F70]\n  [cyan]Brain (Architect):[/cyan] {agent.model}\n  [cyan]Worker (Builder):[/cyan] {config.WORKER_MODEL}")
        elif len(parts) == 2:
            new_model = parts[1]
            agent.model = new_model
            console.print(f"[green]✔ Brain model set to '{new_model}'[/green]")
        elif len(parts) >= 3:
            new_brain = parts[1]
            new_worker = parts[2]
            agent.model = new_brain
            config.WORKER_MODEL = new_worker
            console.print(f"[green]✔ Brain model set to '{new_brain}', Worker set to '{new_worker}'[/green]")
            
    elif cmd == "/models":
        status = check_ollama_status()
        if not status["online"]:
            console.print("[bold red]✖ Ollama is offline. Cannot list models.[/bold red]")
        else:
            table = Table(title="[bold #FF8F70]Installed Ollama Models[/bold #FF8F70]")
            table.add_column("Model Name", style="bold cyan")
            table.add_column("Size", style="dim white")
            try:
                from ollama import Client
                client = Client()
                models_resp = client.list()
                for m in models_resp.models:
                    name = getattr(m, 'model', getattr(m, 'name', 'Unknown'))
                    size = getattr(m, 'size', 0)
                    size_gb = size / (1024**3)
                    table.add_row(name, f"{size_gb:.2f} GB")
                console.print(table)
            except Exception as e:
                console.print(f"[red]Error fetching models: {e}[/red]")
                
    elif cmd == "/history":
        try:
            history_strings = list(session.history.load_history_strings())
            if not history_strings:
                console.print("[dim]Command history is empty.[/dim]")
            else:
                console.print("[bold #FF8F70]Recent Commands:[/bold #FF8F70]")
                for i, item in enumerate(history_strings[-15:]):
                    console.print(f"  [dim]{i+1}:[/dim] {item}")
        except Exception as e:
            console.print(f"[red]Error reading history: {e}[/red]")
            
    elif cmd == "/compact":
        before = len(agent.history)
        from .agent import prune_agent_history
        agent.history = prune_agent_history(agent.history, limit=10)
        after = len(agent.history)
        console.print(f"[green]✔ Compacted context: {before} turns -> {after} turns.[/green]")
        
    elif cmd == "/config":
        from .config import BRAIN_SYSTEM_PROMPT, WORKER_MODEL
        console.print(Panel(Syntax(BRAIN_SYSTEM_PROMPT, "markdown", background_color="default"), title="Lead Architect Prompt"))
        console.print(f"[cyan]Brain Model:[/cyan] {agent.model}")
        console.print(f"[cyan]Worker Model:[/cyan] {WORKER_MODEL}")
        
    else:
        console.print(f"[red]Unknown command: {cmd}. Type /help for assistance.[/red]")
        
    return True

def main():
    PEACH = "#FF8F70"
    
    style = Style.from_dict({
        'prompt': f'bold {PEACH}',
    })
    
    # Establish persistent history
    history_file = os.path.expanduser("~/.snas_code_history")
    
    try:
        session = PromptSession(style=style, history=FileHistory(history_file), completer=SansCompleter())
        is_interactive = True
    except Exception:
        is_interactive = False
        console.print("[dim]No interactive console detected.[/dim]")
    
    from .config import BRAIN_MODEL
    console.print()
    
    # Large ASCII Banner
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
    
    # Initialization Sequence
    init_steps = [
        "● core systems online",
        "● neural weights loaded",
        "● agentic protocols active",
    ]
    with Live(auto_refresh=False) as live:
        for i in range(len(init_steps)):
            live.update(Align.center(Text("\n".join(init_steps[:i+1]), style="dim")), refresh=True)
            time.sleep(0.1)
    
    # startup status check for local Ollama server
    status = check_ollama_status()
    if status["online"]:
        status_text = f"[green]● Ollama Connection: ONLINE[/green] (Detected {status['model_count']} models)"
    else:
        status_text = f"[bold red]● Ollama Connection: OFFLINE[/bold red]\n[dim white]  Warning: Local Ollama daemon unreachable. Run 'ollama serve' to activate SANS CODE fully.[/dim white]"
        
    console.print(Align.center(Panel(Text.from_markup(status_text), border_style="dim", subtitle="System Status Check")))
    console.print()

    # Refined Capabilities Panel
    tools_table = Table(show_header=False, box=None, padding=(0, 2))
    tools_table.add_column(style=PEACH)
    tools_table.add_column(style="dim white")
    
    tool_icons = {
        "view_file": "view", "write_file": "edit", "list_dir": "list",
        "run_command": "exec", "delete_path": "rm", "search_code": "find",
        "run_in_new_terminal": "term", "read_website": "web", "search_internet": "search",
        "git_status": "git.status", "git_diff": "git.diff", "make_directory": "mkdir",
        "run_background_command": "bg.exec", "get_background_process_output": "bg.logs",
        "kill_background_process": "bg.kill"
    }
    
    for t in tools:
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
                
            # Intercept slash commands
            if user_input.strip().startswith("/"):
                keep_running = handle_slash_command(user_input, agent, session)
                if not keep_running:
                    break
                continue
                
            if user_input.strip().lower() in ["exit", "quit"]:
                break
        except (KeyboardInterrupt, EOFError):
            break

        agent.chat(user_input)

if __name__ == "__main__":
    main()
