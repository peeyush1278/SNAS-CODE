# tools.py

import os
import subprocess
import difflib
import time as _time
import re
import threading
import queue
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax

from .utils import console
from .web_tools import read_website, search_internet

# ─────────────────────────────────────────────────────────────
#  DEFAULT IGNORE LIST (EXCLUDES)
# ─────────────────────────────────────────────────────────────
DEFAULT_EXCLUDES = {
    '.git', 'node_modules', 'venv', '.venv', '__pycache__', 'dist', 
    'build', '.next', 'snas_code.egg-info', '.pytest_cache', '.idea', 
    '.vscode', 'bower_components', '.sass-cache'
}

def is_ignored(path_str: str) -> bool:
    """Return True if any part of the path is in the default exclude list or starts with '.'."""
    normalized = os.path.normpath(path_str)
    parts = normalized.split(os.sep)
    for part in parts:
        if part in DEFAULT_EXCLUDES:
            return True
        if part.startswith('.') and part not in ['.', '..']:
            return True
    return False

# ─────────────────────────────────────────────────────────────
#  BACKGROUND PROCESS MANAGEMENT
# ─────────────────────────────────────────────────────────────
BACKGROUND_PROCESSES = {}

class BackgroundProcess:
    def __init__(self, command: str):
        self.command = command
        self.process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            errors='replace'
        )
        self.output_queue = queue.Queue()
        self.stdout_thread = threading.Thread(target=self._read_stream, args=(self.process.stdout, "STDOUT"))
        self.stderr_thread = threading.Thread(target=self._read_stream, args=(self.process.stderr, "STDERR"))
        self.stdout_thread.daemon = True
        self.stderr_thread.daemon = True
        self.stdout_thread.start()
        self.stderr_thread.start()
        self.start_time = _time.time()
        self.log = []

    def _read_stream(self, stream, prefix):
        for line in iter(stream.readline, ''):
            formatted_line = f"[{prefix}] {line}"
            self.output_queue.put(formatted_line)
            self.log.append(formatted_line)
        stream.close()

    def get_new_output(self) -> str:
        lines = []
        while not self.output_queue.empty():
            lines.append(self.output_queue.get())
        if not lines:
            if self.process.poll() is not None:
                return f"[System] Process finished with exit code {self.process.returncode}."
            return "[System] No new output."
        return "".join(lines)

    def get_full_log(self) -> str:
        return "".join(self.log)

    def is_running(self) -> bool:
        return self.process.poll() is None

    def kill(self):
        if self.is_running():
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            return "Process terminated."
        return "Process is already stopped."

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
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
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
            _time.sleep(0.005) 
            progress.advance(task)
    
    console.print(f"    [green]✔ {path} updated successfully.[/green]")

def replace_file_content(path: str, target: str, replacement: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if target not in content:
            return f"Error: The target string was not found exactly as specified in {path}. Make sure whitespace and indentation match perfectly."
        
        new_content = content.replace(target, replacement, 1) 
        
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
        # Determine language for syntax highlight
        ext = os.path.splitext(path)[1].lstrip('.') or 'python'
        console.print(Panel(Syntax(content, ext, theme="monokai", background_color="default"), title="Proposed Content"))
        
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
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."

        if not recursive:
            items = os.listdir(path)
            filtered = [item for item in items if not is_ignored(os.path.join(path, item))]
            return "\n".join(filtered) if filtered else "Directory is empty or all contents are ignored."
        else:
            results = []
            file_count = 0
            max_files = 500
            for root, dirs, files in os.walk(path):
                # Prune ignored directories in-place!
                dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d))]
                
                if is_ignored(root):
                    continue
                
                level = os.path.normpath(root).replace(os.path.normpath(path), '').count(os.sep)
                indent = ' ' * 4 * level
                results.append(f"{indent}{os.path.basename(root)}/")
                sub_indent = ' ' * 4 * (level + 1)
                
                for f in files:
                    file_path = os.path.join(root, f)
                    if is_ignored(file_path):
                        continue
                    
                    results.append(f"{sub_indent}{f}")
                    file_count += 1
                    if file_count >= max_files:
                        results.append(f"{sub_indent}... (Recursive listing capped at {max_files} files to prevent context bloat)")
                        break
                if file_count >= max_files:
                    break
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
        max_matches = 50
        
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d))]
            
            if is_ignored(root):
                continue
                
            for file in files:
                filepath = os.path.join(root, file)
                if is_ignored(filepath):
                    continue
                    
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for i, line in enumerate(f):
                            if query in line:
                                results.append(f"{filepath} (Line {i+1}): {line.strip()}")
                                if len(results) >= max_matches:
                                    results.append(f"\n... (Search results capped at {max_matches} matches)")
                                    break
                except Exception:
                    pass
                if len(results) >= max_matches:
                    break
            if len(results) >= max_matches:
                break
        return "\n".join(results) if results else f"No matches found for '{query}'."
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
#  NEW INTEGRATED TOOLS
# ─────────────────────────────────────────────────────────────

def git_status() -> str:
    try:
        res = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True, errors='replace')
        if res.returncode != 0:
            return "Error running git status. Make sure git is initialized and path is clean."
        out = res.stdout.strip()
        if not out:
            return "Git repository is clean. No modifications."
        return f"--- Git Status ---\n{out}"
    except Exception as e:
        return f"Error checking git status: {e}"

def git_diff() -> str:
    try:
        res = subprocess.run("git diff", shell=True, capture_output=True, text=True, errors='replace')
        if res.returncode != 0:
            return "Error running git diff. Make sure git is initialized."
        out = res.stdout.strip()
        if not out:
            res_staged = subprocess.run("git diff --cached", shell=True, capture_output=True, text=True, errors='replace')
            out_staged = res_staged.stdout.strip()
            if out_staged:
                return f"--- Git Diff (Staged Changes) ---\n{out_staged}"
            return "No unstaged changes in the repository."
        return f"--- Git Diff ---\n{out}"
    except Exception as e:
        return f"Error running git diff: {e}"

def make_directory(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
        return f"Successfully created directory: {path}"
    except Exception as e:
        return f"Error creating directory: {e}"

def run_background_command(command: str) -> str:
    global BACKGROUND_PROCESSES
    proc_id = str(len(BACKGROUND_PROCESSES) + 1)
    
    warning_panel = Panel(
        Text(f"Process ID {proc_id}: {command}", style="bold magenta", justify="left"),
        title="[bold yellow]🖥️ AGENT SPAWNING BACKGROUND TASK 🖥️[/bold yellow]",
        border_style="magenta"
    )
    console.print(warning_panel)
    while True:
        confirm = input("Allow spawning this background task? (y/n): ").strip().lower()
        if confirm == 'y':
            break
        elif confirm == 'n':
            return "Spawn denied by the user."
            
    try:
        bg_proc = BackgroundProcess(command)
        BACKGROUND_PROCESSES[proc_id] = bg_proc
        return f"Spawned background process with ID '{proc_id}'. Use 'get_background_process_output' with ID '{proc_id}' to read its logs, or 'kill_background_process' to stop it."
    except Exception as e:
        return f"Error launching background command: {e}"

def get_background_process_output(proc_id: str) -> str:
    global BACKGROUND_PROCESSES
    if proc_id not in BACKGROUND_PROCESSES:
        return f"Error: No background process with ID '{proc_id}' exists."
    bg_proc = BACKGROUND_PROCESSES[proc_id]
    output = bg_proc.get_new_output()
    running_status = "RUNNING" if bg_proc.is_running() else "FINISHED"
    return f"--- Process ID '{proc_id}' ({running_status}) ---\n{output}"

def kill_background_process(proc_id: str) -> str:
    global BACKGROUND_PROCESSES
    if proc_id not in BACKGROUND_PROCESSES:
        return f"Error: No background process with ID '{proc_id}' exists."
    bg_proc = BACKGROUND_PROCESSES[proc_id]
    result = bg_proc.kill()
    return f"Process ID '{proc_id}': {result}"

# ─────────────────────────────────────────────────────────────
#  TOOL SCHEMAS
# ─────────────────────────────────────────────────────────────

tools = [
    {
        "type": "function",
        "function": {
            "name": "view_file",
            "description": "Read a specific range of lines from a file. Highly recommended for reading source code to fit in context.",
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
            "description": "List contents of a directory. Capable of recursive listing. Skips huge vendor folders automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": { "type": "string" },
                    "recursive": { "type": "boolean", "description": "Whether to list all nested subdirectories recursively." }
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
            "description": "Recursively search all files in a directory for a specific text/code string. Super fast, ignores huge dependency directories.",
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
            "description": "Spawn a completely detached, separate Windows terminal window to run a command.",
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
            "description": "Fetch the text content of a webpage (removes HTML tags). Useful for developer docs.",
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
            "description": "Search the internet (DuckDuckGo) for a query to locate errors or standard libraries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": { "type": "string", "description": "The search term." },
                    "max_results": { "type": "integer", "description": "Number of links to fetch (default 5)." }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Retrieve the current git status (modified, untracked, deleted files) of the workspace.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Get detailed git differences of staged or unstaged modifications in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "make_directory",
            "description": "Create a new directory structure recursively.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": { "type": "string", "description": "Directory path to create." }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_background_command",
            "description": "Spawn a long-running terminal command (e.g. dev server, heavy build) in the background asynchronously.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": { "type": "string", "description": "The command string to launch in the background." }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_background_process_output",
            "description": "Read the latest stdout/stderr console logs generated by a background task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proc_id": { "type": "string", "description": "The process ID (PID) key assigned during spawning." }
                },
                "required": ["proc_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "kill_background_process",
            "description": "Forcefully terminate a running background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "proc_id": { "type": "string", "description": "The process ID key to stop." }
                },
                "required": ["proc_id"]
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
    elif name == "git_status":
        return git_status()
    elif name == "git_diff":
        return git_diff()
    elif name == "make_directory":
        return make_directory(args.get("path"))
    elif name == "run_background_command":
        return run_background_command(args.get("command"))
    elif name == "get_background_process_output":
        return get_background_process_output(args.get("proc_id"))
    elif name == "kill_background_process":
        return kill_background_process(args.get("proc_id"))
    else:
        return f"Error: Unknown tool {name}"
