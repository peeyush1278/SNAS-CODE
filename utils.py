# utils.py

import json
import re
from rich.console import Console

console = Console()

def _scrub_hallucinated_json(text: str) -> str:
    """Remove raw JSON tool-call blocks that the model sometimes hallucinates."""
    if not text:
        return ""
    text = re.sub(r'```(?:json)?\s*\{\s*"name".*?\}\s*```', '', text, flags=re.DOTALL)
    text = re.sub(r'\{\s*"name"\s*:\s*".*?"(?:.|\n)*?\}', '', text, flags=re.DOTALL)
    return text.strip()

def _parse_response(response):
    """Convert an Ollama response object into a plain dict for the history."""
    msg = {"role": response.message.role, "content": response.message.content or ""}
    if getattr(response.message, "tool_calls", None):
        msg["tool_calls"] = [
            {
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            } for tc in response.message.tool_calls
        ]
    return msg

def _try_fallback_parse(msg_dict):
    """If the model printed raw JSON instead of using native tool calls, try to rescue it."""
    if msg_dict.get("tool_calls") or not msg_dict.get("content"):
        return
    text = msg_dict["content"].strip()
    
    # Try to find JSON block
    import json
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            parsed = json.loads(json_str)
            # Handle nested "function" key (Ollama schema style)
            if "function" in parsed and isinstance(parsed["function"], dict):
                func_data = parsed["function"]
            else:
                func_data = parsed

            if isinstance(func_data, dict) and "name" in func_data:
                # Handle "parameters" vs "arguments"
                args = func_data.get("arguments") or func_data.get("parameters") or {}
                msg_dict["tool_calls"] = [{
                    "function": {
                        "name": func_data["name"],
                        "arguments": args
                    }
                }]
                console.print(f"    [dim cyan]⚡ Rescued tool call from content: {func_data['name']}[/dim cyan]")
        except Exception:
            pass

class _DictToObj:
    """Tiny helper to let dict-based tool calls work with map_tool_call."""
    def __init__(self, **kw):
        self.__dict__.update(kw)

def get_available_models():
    """Fetch the list of available local models using the Ollama library."""
    from ollama import Client
    try:
        client = Client()
        models_resp = client.list()
        model_list = []
        for m in models_resp.models:
            # Handle different versions of ollama-python
            name = getattr(m, 'model', getattr(m, 'name', 'Unknown'))
            size = getattr(m, 'size', 0)
            size_gb = size / (1024**3)
            model_list.append(f"- {name} ({size_gb:.1f} GB)")
        return "\n".join(model_list)
    except Exception as e:
        return f"Error fetching models: {e}"

def auto_select_models():
    """Automatically detect and select Brain and Worker models from local Ollama library."""
    from ollama import Client
    try:
        client = Client()
        models_resp = client.list()
        all_models = []
        for m in models_resp.models:
            name = getattr(m, 'model', getattr(m, 'name', 'Unknown'))
            size = getattr(m, 'size', 0)
            all_models.append({'name': name, 'size': size})
        
        if not all_models:
            return "gemma2:latest", "phi3:mini" # Fallback defaults

        # Sort by size (descending) - assume larger is smarter (Brain)
        all_models.sort(key=lambda x: x['size'], reverse=True)
        
        brain = all_models[0]['name']
        
        if len(all_models) > 1:
            # Pick a smaller model for worker if possible, or just the second largest
            # Ideally look for 'mini', 'small', 'tiny' in name
            worker_candidates = [m['name'] for m in all_models if any(x in m['name'].lower() for x in ['mini', 'small', 'tiny', '3b', '1b', 'phi'])]
            if worker_candidates and worker_candidates[0] != brain:
                worker = worker_candidates[0]
            else:
                worker = all_models[1]['name']
        else:
            worker = brain
            
        return brain, worker
    except Exception:
        return "gemma2:latest", "phi3:mini" # Hard fallbacks
