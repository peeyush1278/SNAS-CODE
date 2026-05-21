# agent.py

import json
import os
import re
import time as _time
from ollama import Client
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.rule import Rule

from .config import BRAIN_MODEL, WORKER_MODEL, BRAIN_SYSTEM_PROMPT, WORKER_SYSTEM_PROMPT
from .utils import console, _scrub_hallucinated_json, _parse_response, _try_fallback_parse, _DictToObj, repair_and_parse_json
from .tools import tools, map_tool_call

def prune_agent_history(history, limit=16):
    """Keep the system prompt, user initial instruction, and last few conversation turns.
    Prune heavy tool payload outputs to avoid context overflow while preserving flow metadata."""
    if len(history) <= limit:
        return history
        
    system_msg = history[0]
    initial_user = None
    for msg in history[1:]:
        if msg.get("role") == "user":
            initial_user = msg
            break
            
    recent_turns = history[-limit:]
    
    new_history = [system_msg]
    if initial_user and initial_user not in recent_turns:
        new_history.append(initial_user)
        
    # Ensure no duplicates and truncate huge tool outputs
    for msg in recent_turns:
        if msg not in new_history:
            if msg.get("role") == "tool" and len(msg.get("content", "")) > 1500:
                truncated_content = msg["content"][:1500] + f"\n... [Tool output truncated: {len(msg['content'])-1500} chars hidden to save context] ..."
                msg = msg.copy()
                msg["content"] = truncated_content
            new_history.append(msg)
            
    return new_history

class WorkerAgent:
    def __init__(self):
        self.client = Client()
        self.history = [{"role": "system", "content": WORKER_SYSTEM_PROMPT}]

    def execute_task(self, model: str, task_prompt: str):
        task_history = [{"role": "system", "content": WORKER_SYSTEM_PROMPT}, {"role": "user", "content": task_prompt}]
        
        step_counter = 0
        max_steps = 10
        
        while step_counter < max_steps:
            # Smart context compaction
            task_history = prune_agent_history(task_history, limit=14)
            
            try:
                response_stream = self.client.chat(
                    model=model, 
                    messages=task_history, 
                    tools=tools,
                    stream=True,
                    options={"num_ctx": 8192}
                )
                
                collected_content = ""
                collected_tool_calls = []
                in_thinking = False
                last_tool_call_index = -1
                printed_args_map = {}
                
                for chunk in response_stream:
                    msg = chunk.message
                    if getattr(msg, "thinking", None):
                        if not in_thinking:
                            console.print(f"\n[dim white]╭─ analysis[/dim white]")
                            in_thinking = True
                        console.print(f"[italic grey50]{msg.thinking}[/italic grey50]", end="")
                    
                    if msg.content or getattr(msg, "tool_calls", None):
                        if in_thinking:
                            console.print(f"\n[dim white]╰───────────[/dim white]\n")
                            in_thinking = False
                            
                        if msg.content:
                            console.print(f"[#D9D3C9]{msg.content}[/#D9D3C9]", end="")
                            collected_content += msg.content
                        if getattr(msg, "tool_calls", None):
                            collected_tool_calls = msg.tool_calls
                            for i, tc in enumerate(msg.tool_calls):
                                if i > last_tool_call_index:
                                    console.print(f"\n[bold #FF8F70]↳ tool.stream: {tc.function.name}[/bold #FF8F70] ", end="")
                                    last_tool_call_index = i
                                    printed_args_map[i] = 0
                                
                                args_str = str(tc.function.arguments)
                                if len(args_str) > printed_args_map[i]:
                                    new_content = args_str[printed_args_map[i]:]
                                    console.print(f"[dim cyan]{new_content}[/dim cyan]", end="")
                                    printed_args_map[i] = len(args_str)
                
                if in_thinking:
                    console.print(f"\n[dim white]╰───────────[/dim white]\n")
                
                console.print()
            except Exception as e:
                return f"Worker Error ({model}): {e}"

            msg_dict = {
                "role": "assistant",
                "content": collected_content,
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in (collected_tool_calls or [])
                ] if collected_tool_calls else None
            }
            
            # Fallback JSON rescue using the robust healing utility
            if not msg_dict.get("tool_calls") and msg_dict.get("content"):
                _try_fallback_parse(msg_dict)
            
            task_history.append(msg_dict)

            if not msg_dict.get("tool_calls"):
                return msg_dict.get("content", "Task completed.")

            for tool_call in msg_dict["tool_calls"]:
                step_counter += 1
                func = tool_call["function"]
                args = func.get('arguments', {})
                
                console.print(f"\n    [bold #FF8F70]↳ system.call({model}): {func['name']}[/bold #FF8F70]")
                if args:
                    console.print(f"    [dim grey50]params: {args}[/dim grey50]")
                
                tc_obj = _DictToObj(function=_DictToObj(name=func['name'], arguments=func['arguments']))
                
                # USER CONFIRMATION
                console.print(f"\n    [bold #FF8F70]◌ protocol.authorize: {func['name']}[/bold #FF8F70]")
                
                confirm = console.input("    [dim white]Allow execution? (y/n): [/dim white]").strip().lower()
                if confirm != 'y':
                    result = "User denied execution of this tool."
                    console.print("    [red]✖ Aborted.[/red]")
                else:
                    # Execute tool call
                    result = map_tool_call(tc_obj)
                    
                    # Premium UX: Prettify and highlight code output for the developer
                    if func['name'] == 'view_file' and 'path' in args:
                        try:
                            f_path = args['path']
                            s_line = args.get('start_line', 1)
                            e_line = args.get('end_line', 500)
                            with open(f_path, 'r', encoding='utf-8', errors='ignore') as f_read:
                                lines = f_read.readlines()
                                total = len(lines)
                                selected = lines[max(0, s_line-1):min(total, e_line)]
                                view_content = "".join(selected)
                            ext = os.path.splitext(f_path)[1].lstrip('.') or 'python'
                            console.print(Panel(Syntax(view_content, ext, theme="monokai", background_color="default"), title=f"View: {f_path} (Lines {s_line}-{min(total, e_line)})"))
                        except Exception:
                            pass
                
                res_str = str(result)
                if len(res_str) > 500:
                    res_display = res_str[:500] + "... (truncated)"
                else:
                    res_display = res_str
                console.print(f"    [dim green]Result: {res_display}[/dim green]")
                
                task_history.append({
                    "role": "tool",
                    "content": res_str,
                    "name": func['name']
                })
        
        return "Worker reached max steps."

class SansAgent:
    def __init__(self):
        from .utils import get_available_models
        self.client = Client()
        models_str = get_available_models()
        self.model = BRAIN_MODEL
        full_system_prompt = BRAIN_SYSTEM_PROMPT.replace("{available_models}", models_str)
        self.history = [{"role": "system", "content": full_system_prompt}]
        self.worker = WorkerAgent()
    
    def chat(self, user_input: str):
        self.history.append({"role": "user", "content": user_input})

        console.print()
        console.print(Rule("[bold #FF8F70]SANS CODE[/bold #FF8F70]", style="dim white"))
        console.print()

        # Brain can also inspect git status & git diff directly!
        investigation_tool_names = ["view_file", "list_dir", "search_code", "read_website", "search_internet", "git_status", "git_diff"]
        brain_tools = [t for t in tools if t["function"]["name"] in investigation_tool_names]

        step_counter = 0
        while step_counter < 10:
            # Compact the history to optimize VRAM
            self.history = prune_agent_history(self.history, limit=16)
            
            console.print(f"[dim white]●[/dim white] [bold grey50]orchestrator active ({self.model})...[/bold grey50]")
            try:
                response_stream = self.client.chat(
                    model=self.model, 
                    messages=self.history, 
                    tools=brain_tools, 
                    stream=True,
                    keep_alive=-1,
                    options={"num_ctx": 32768}
                )
                
                collected_content = ""
                collected_tool_calls = []
                in_thinking = False
                last_tool_call_index = -1
                printed_args_map = {}
                
                for chunk in response_stream:
                    msg = chunk.message
                    if getattr(msg, "thinking", None):
                        if not in_thinking:
                            console.print(f"\n[dim white]╭─ analysis[/dim white]")
                            in_thinking = True
                        console.print(f"[italic grey50]{msg.thinking}[/italic grey50]", end="")
                    
                    if msg.content or getattr(msg, "tool_calls", None):
                        if in_thinking:
                            console.print(f"\n[dim white]╰───────────[/dim white]\n")
                            in_thinking = False
                            
                        if msg.content:
                            console.print(f"[#D9D3C9]{msg.content}[/#D9D3C9]", end="")
                            collected_content += msg.content
                        if getattr(msg, "tool_calls", None):
                            collected_tool_calls = msg.tool_calls
                            for i, tc in enumerate(msg.tool_calls):
                                if i > last_tool_call_index:
                                    console.print(f"\n[bold #FF8F70]↳ tool.stream: {tc.function.name}[/bold #FF8F70] ", end="")
                                    last_tool_call_index = i
                                    printed_args_map[i] = 0
                                
                                args_str = str(tc.function.arguments)
                                if len(args_str) > printed_args_map[i]:
                                    new_content = args_str[printed_args_map[i]:]
                                    console.print(f"[dim cyan]{new_content}[/dim cyan]", end="")
                                    printed_args_map[i] = len(args_str)
                
                if in_thinking:
                    console.print(f"\n[dim white]╰───────────[/dim white]\n")
                
                console.print()
            except Exception as e:
                console.print(f"[bold red]Error communicating with Brain Model: {e}[/bold red]")
                return

            msg_dict = {
                "role": "assistant",
                "content": collected_content,
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in (collected_tool_calls or [])
                ] if collected_tool_calls else None
            }
            
            self.history.append(msg_dict)

            # Process delegation block
            if msg_dict.get("content"):
                try:
                    content = msg_dict["content"].strip()
                    # Check for JSON bounds
                    start = content.find('{')
                    end = content.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        json_str = content[start:end+1]
                        
                        # Call robust JSON healer
                        data = repair_and_parse_json(json_str)
                        if isinstance(data, dict) and "tasks" in data:
                            self._handle_delegation(data)
                            return
                except Exception:
                    pass

            if not msg_dict.get("tool_calls"):
                return

            for tool_call in msg_dict["tool_calls"]:
                step_counter += 1
                func = tool_call["function"]
                args = func.get('arguments', {})
                console.print(f"  [dim cyan]◌ investigation step {step_counter}: {func['name']}[/dim cyan]")
                if args:
                    console.print(f"    [dim grey50]context: {args}[/dim grey50]")
                
                tc_obj = _DictToObj(function=_DictToObj(name=func['name'], arguments=func['arguments']))
                result = map_tool_call(tc_obj)
                
                self.history.append({
                    "role": "tool",
                    "content": str(result),
                    "name": func['name']
                })

    def _unload_model(self, model_name: str):
        """Force Ollama to unload a model from VRAM."""
        try:
            self.client.generate(model=model_name, keep_alive=0)
        except Exception:
            pass

    def _handle_delegation(self, data):
        plan = data.get("plan", "Executing tasks...")
        tasks = data.get("tasks", [])

        console.print(Panel(Markdown(plan), title="[bold #FF8F70]Strategic Directive[/bold #FF8F70]", border_style="#FF8F70"))
        
        results = []
        for task in tasks:
            t_id = task.get("id", "?")
            t_model = task.get("model", WORKER_MODEL)
            desc = task.get("description", "No description")
            prompt = task.get("prompt", "")
            
            console.print(f"\n[bold #FF8F70]▶ process.execute {t_id} ({t_model}): {desc}[/bold #FF8F70]")
            
            console.print(f"[dim grey50]◌ swapping models (unloading {self.model})...[/dim grey50]")
            self._unload_model(self.model)
            
            console.print(f"[bold grey50]◌ worker active ({t_model})...[/bold grey50]")
            result = self.worker.execute_task(t_model, prompt)
            
            # SWAP: Unload Worker and reload Brain
            console.print(f"[dim grey50]◌ swapping models (unloading {t_model})...[/dim grey50]")
            self._unload_model(t_model)
            
            console.print(f"[dim grey50]Result: {result[:200]}...[/dim grey50]")
            results.append({"task_id": t_id, "result": result})

        # Smart Git-Integrated Verification
        console.print(f"\n[bold #FF8F70]◌ protocol.verify: Scanning workspace via Git status...[/bold #FF8F70]")
        verification_status = []
        try:
            import subprocess
            res = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True, errors='replace')
            if res.returncode == 0:
                lines = res.stdout.strip().splitlines()
                if lines:
                    console.print(f"  [green]✔ Found modified workspace assets under Git:[/green]")
                    for line in lines:
                        status_char = line[:2]
                        filepath = line[3:]
                        console.print(f"    [green]● {status_char} {filepath}[/green]")
                        verification_status.append(f"Workspace Change: {line}")
                else:
                    console.print("  [dim]No changes detected in workspace (clean repository).[/dim]")
            else:
                raise Exception("Git command failed")
        except Exception:
            # Fallback to the optimized regex-based verification
            console.print("  [dim yellow]◌ Git is not initialized. Using optimized regex verification fallback...[/dim yellow]")
            import os
            import re
            for task in tasks:
                combined_text = task.get("description", "") + " " + task.get("prompt", "")
                found_paths = re.findall(r'\b[a-zA-Z0-9_\-/\\]+\.[a-zA-Z]{2,4}\b', combined_text)
                for path in set(found_paths):
                    if re.match(r'^\d+\.\d+$', path) or path.lower() in ['gemma.cpp', 'llama.cpp']:
                        continue
                    clean_path = path.strip('.,')
                    if os.path.exists(clean_path) and os.path.isfile(clean_path):
                        console.print(f"    [green]✔ verified: {clean_path}[/green]")
                        verification_status.append(f"Verified: {clean_path} exists.")
                    elif any(x in combined_text.lower() for x in ["create", "write", "save", "make"]):
                        console.print(f"    [red]✘ missing: {clean_path}[/red]")
                        verification_status.append(f"Warning: {clean_path} was requested but is not found.")
        
        if verification_status:
            results.append({"system_verification": verification_status})

        console.print(f"\n[bold #FF8F70]◌ synthesis.complete:[/bold #FF8F70]")
        review_prompt = f"All tasks completed. Here are the results:\n{json.dumps(results, indent=2)}\n\nPlease provide a final summary to the user."
        
        self.history.append({"role": "user", "content": review_prompt})
        
        try:
            response_stream = self.client.chat(model=self.model, messages=self.history, keep_alive=-1, stream=True)
            collected_content = ""
            in_thinking = False
            for chunk in response_stream:
                msg = chunk.message
                if getattr(msg, "thinking", None):
                    if not in_thinking:
                        console.print(f"\n[dim white]╭─ analysis[/dim white]")
                        in_thinking = True
                    console.print(f"[italic grey50]{msg.thinking}[/italic grey50]", end="")
                
                if msg.content:
                    if in_thinking:
                        console.print(f"\n[dim white]╰───────────[/dim white]\n")
                        in_thinking = False
                    console.print(f"[#D9D3C9]{msg.content}[/#D9D3C9]", end="")
                    collected_content += msg.content
            
            if in_thinking:
                console.print(f"\n[dim white]╰───────────[/dim white]\n")
            console.print()
            self.history.append({"role": "assistant", "content": collected_content})
        except Exception as e:
            console.print(f"[red]◌ Error in synthesis: {e}[/red]")

    def _prune_history(self):
        # Kept for backward compatibility, now replaced with our superior prune_agent_history
        self.history = prune_agent_history(self.history)
