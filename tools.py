# tools.py

import os
import subprocess
import difflib
import time as _time
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax

from utils import console
from web_tools import read_website, search_internet

# ─────────────────────────────────────────────────────────────
#  LOCAL SYSTEM TOOL FUNCTIONS
# ─────────────────────────────────────────────────────────────

def show_diff(path: str, old_content: str, new_content: str):
    console.print(f"\n[bold yellow]📝 Diff for {path}:[/bold yellow]")
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile='original',
        tofile='updated'
    )
    diff_text = "".join(diff)
    if diff_text:
        console.print(Syntax(diff_text, "diff", theme="monokai", background_color="default"))
    else:
        console.print("[dim]No changes detected in diff.[/dim]")

def view_file(path: str, start_line: int = 1, end_line: int = 500) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            total = len(lines)
            selected = lines[max(0, start_line-1):min(total, end_line)]
            content = "".join(selected)
            return f"--- {path} (Lines {start_line}-{min(total, end_line)} of {total}) ---\n{content}"
    except Exception as e:
        return f"Error viewing file: {e}"

def _simulate_writing(path: str, content: str):
    """Aesthetic simulation of writing code line by line."""
    lines = content.splitlines()
    total_lines = len(lines)
    
    console.print(f"\n[bold #FF8F70]◌ protocol.write: {path}[/bold #FF8F70]")
    
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    with Progress(
        SpinnerColumn(spinner_name="dots", style="#FF8F70"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None, style="dim grey50", complete_style="#FF8F70"),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task(f"[dim]Committing {total_lines} lines...", total=total_lines)
        for line in lines:
            # Small delay to simulate "writing" line by line
            _time.sleep(0.01) 
            progress.advance(task)
    
    console.print(f"    [green]✔ {path} updated successfully.[/green]")

def replace_file_content(path: str, target: str, replacement: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if target not in content:
            return f"Error: The target string was not found exactly as specified in {path}. Make sure whitespace and indentation match perfectly."
        
        new_content = content.replace(target, replacement, 1) # Only replace first occurrence for safety
        
        show_diff(path, content, new_content)
        
        console.print(f"\n[bold #FF8F70]◌ protocol.staging: Review the changes above.[/bold #FF8F70]")
        confirm = console.input("    [dim white]Type 'accept' to commit or anything else to abort: [/dim white]").strip().lower()
        
        if confirm != 'accept':
            return "Modification aborted by user. Rewrite according to user preference."

        _simulate_writing(path, new_content)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return f"Successfully updated {path}."
    except Exception as e:
        return f"Error updating file: {e}"

def write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        
        # Staging
        console.print(f"\n[bold #FF8F70]◌ protocol.staging: {path}[/bold #FF8F70]")
        console.print(Panel(Syntax(content, "python", theme="monokai", background_color="default"), title="Proposed Content"))
        
        confirm = console.input("    [dim white]Type 'accept' to create/overwrite or anything else to abort: [/dim white]").strip().lower()
        
        if confirm != 'accept':
            return "File creation aborted by user. Rewrite according to user preference."

        _simulate_writing(path, content)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"File successfully written to {path}"
    except Exception as e:
        return f"Error writing file: {e}"

def list_dir(path: str, recursive: bool = False) -> str:
    try:
        if not recursive:
            items = os.listdir(path)
            return "\n".join(items) if items else "Directory is empty."
        else:
            results = []
            for root, dirs, files in os.walk(path):
                level = root.replace(path, '').count(os.sep)
                indent = ' ' * 4 * level
                results.append(f"{indent}{os.path.basename(root)}/")
                sub_indent = ' ' * 4 * (level + 1)
                for f in files:
                    results.append(f"{sub_indent}{f}")
            return "\n".join(results)
    except Exception as e:
        return f"Error listing directory: {e}"

def delete_path(path: str) -> str:
    warning_panel = Panel(
        Text(path, style="bold red", justify="center"),
        title="[bold yellow]⚠️ AGENT REQUESTS FILE/DIR DELETION ⚠️[/bold yellow]",
        border_style="red"
    )
    console.print(warning_panel)
    while True:
        confirm = input("Allow this deletion? (y/n): ").strip().lower()
        if confirm == 'y':
            break
        elif confirm == 'n':
            return "Deletion denied by the user."
    try:
        with console.status(f"[bold red]Deleting {path}...[/bold red]"):
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
                return f"Directory successfully deleted: {path}"
            else:
                os.remove(path)
                return f"File successfully deleted: {path}"
    except Exception as e:
        return f"Error deleting path: {e}"

def search_code(query: str, path: str = ".") -> str:
    try:
        results = []
        for root, dirs, files in os.walk(path):
            if any(part.startswith('.') or part == '__pycache__' for part in root.split(os.sep)):
                continue
            for file in files:
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f):
                            if query in line:
                                results.append(f"{filepath} (Line {i+1}): {line.strip()}")
                except Exception:
                    pass
        return "\n".join(results[:50]) if results else f"No matches found for '{query}'."
    except Exception as e:
        return f"Error searching code: {e}"

def run_command(command: str) -> str:
    if command.strip().lower().startswith("cd "):
        target_dir = command.strip()[3:].strip().strip("\"'")
        try:
            os.chdir(target_dir)
            return f"Successfully changed directory to {os.getcwd()}"
        except Exception as e:
            return f"Error changing directory: {e}"

    safe_commands = ['ls', 'dir', 'pwd', 'cd', 'git status', 'git diff', 'type', 'cat', 'grep']
    is_safe = any(command.strip().startswith(cmd) for cmd in safe_commands)

    if not is_safe:
        warning_panel = Panel(
            Text(command, style="bold cyan", justify="left"),
            title="[bold yellow]🖥️ AGENT REQUESTS SHELL EXECUTION 🖥️[/bold yellow]",
            border_style="yellow"
        )
        console.print(warning_panel)
        while True:
            confirm = input("Allow this command? (y/n): ").strip().lower()
            if confirm == 'y':
                break
            elif confirm == 'n':
                return "Command execution denied by the user."
    else:
        console.print(f"[dim]⚡ Auto-executing safe command: {command}[/dim]")

    try:
        with console.status(f"[bold cyan]Running: {command}[/bold cyan]"):
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300
            )
        out = result.stdout.strip()
        err = result.stderr.strip()
        final_out = ""
        if out: final_out += f"STDOUT:\n{out}\n"
        if err: final_out += f"STDERR:\n{err}\n"
        if not final_out:
            final_out = f"Command executed successfully with exit code {result.returncode} and no output."
        return final_out
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 300 seconds."
    except Exception as e:
        return f"Error executing command: {e}"

def run_in_new_terminal(command: str) -> str:
    warning_panel = Panel(
        Text(command, style="bold magenta", justify="left"),
        title="[bold yellow]🪟 AGENT REQUESTS SPAWNING DETACHED TERMINAL 🪟[/bold yellow]",
        border_style="yellow"
    )
    console.print(warning_panel)
    while True:
        confirm = input("Allow terminal spawn? (y/n): ").strip().lower()
        if confirm == 'y':
            break
        elif confirm == 'n':
            return "Terminal spawn denied by the user."
    try:
        subprocess.Popen(f'start cmd /k "{command}"', shell=True)
        return f"Successfully spawned new detached terminal running: {command}"
    except Exception as e:
        return f"Error spawning terminal: {e}"

# ─────────────────────────────────────────────────────────────
#  TOOL SCHEMAS
# ─────────────────────────────────────────────────────────────

tools = [
    {
        "type": "function",
        "function": {
            "name": "view_file",
            "description": "Read a specific range of lines from a file. Use this for large files to stay within context limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": { "type": "string", "description": "Path to the file." },
                    "start_line": { "type": "integer", "description": "First line to read (1-indexed)." },
                    "end_line": { "type": "integer", "description": "Last line to read (inclusive)." }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_file_content",
            "description": "Surgically replace a block of text in a file. The 'target' string must match EXACTLY (including whitespace) what is in the file. Only replaces the first occurrence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "target": { "type": "string", "description": "The exact block of text to be replaced." },
                    "replacement": { "type": "string", "description": "The new text to insert." }
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing one with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "content": { "type": "string" }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List contents of a directory. Can be recursive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "recursive": { "type": "boolean", "description": "Whether to list all nested subdirectories." }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a terminal command. Use this carefully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command string to execute in the shell."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_path",
            "description": "Delete a file or a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute or relative path to delete."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Recursively search all files in a directory for a specific text/code string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The exact text or code snippet to search for."
                    },
                    "path": {
                        "type": "string",
                        "description": "The directory path to search within. Defaults to '.'."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_in_new_terminal",
            "description": "Spawn a completely detached, separate Windows terminal window to run a command (e.g. starting a server).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command line string to execute in the new terminal."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_website",
            "description": "Fetch the text content of a webpage (e.g. for reading documentation or articles). Automatically removes HTML tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": { "type": "string", "description": "The URL of the website to read." }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "Search DuckDuckGo or the internet for a specific query to find modern documentation, links, or fixes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": { "type": "string", "description": "The topic or error to search for." },
                    "max_results": { "type": "integer", "description": "Number of links to fetch (default 5)." }
                },
                "required": ["query"]
            }
        }
    }
]

# ─────────────────────────────────────────────────────────────
#  TOOL ROUTER
# ─────────────────────────────────────────────────────────────

def map_tool_call(tool_call):
    name = tool_call.function.name
    args = tool_call.function.arguments
    if isinstance(args, str):
        import json
        try:
            args = json.loads(args)
        except:
            pass

    if name == "view_file":
        return view_file(args.get("path"), args.get("start_line", 1), args.get("end_line", 500))
    elif name == "replace_file_content":
        return replace_file_content(args.get("path"), args.get("target"), args.get("replacement"))
    elif name == "write_file":
        return write_file(args.get("path"), args.get("content"))
    elif name == "list_dir":
        return list_dir(args.get("path"), args.get("recursive", False))
    elif name == "run_command":
        return run_command(args.get("command"))
    elif name == "delete_path":
        return delete_path(args.get("path"))
    elif name == "search_code":
        return search_code(args.get("query"), args.get("path", "."))
    elif name == "run_in_new_terminal":
        return run_in_new_terminal(args.get("command"))
    elif name == "read_website":
        return read_website(args.get("url"))
    elif name == "search_internet":
        return search_internet(args.get("query"), args.get("max_results", 5))
    else:
        return f"Error: Unknown tool {name}"
