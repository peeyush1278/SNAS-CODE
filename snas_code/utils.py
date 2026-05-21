# utils.py

import json
import re
import os
from rich.console import Console

console = Console()

def load_env_file():
    """Manually parse .env file in the project root if it exists, to avoid external dependencies."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        os.environ[k] = v
        except Exception:
            pass

# Load env variables immediately on import
load_env_file()

def repair_and_parse_json(text: str) -> dict:
    """Robust parser that cleans and extracts JSON from potentially malformed LLM responses."""
    if not text:
        raise ValueError("Empty input text")
        
    text = text.strip()
    
    # 1. Try simple loads first
    try:
        return json.loads(text)
    except Exception:
        pass
        
    # 2. Extract block between first '{' and last '}'
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        start_arr = text.find('[')
        end_arr = text.rfind(']')
        if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
            json_str = text[start_arr:end_arr+1]
        else:
            raise ValueError("No JSON bounds found in text")
    else:
        json_str = text[start:end+1]
        
    # 3. Strip markdown codeblock lines if present inside our substring
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0].strip()
        
    # Try parsing again after block extraction
    try:
        return json.loads(json_str)
    except Exception:
        pass
        
    # 4. Perform aggressive regex-based JSON healing
    cleaned = json_str
    
    # Remove trailing commas before closing braces/brackets
    cleaned = re.sub(r',\s*\}', '}', cleaned)
    cleaned = re.sub(r',\s*\]', ']', cleaned)
    
    # Try parsing
    try:
        return json.loads(cleaned)
    except Exception:
        pass
        
    # Replace single quotes with double quotes safely for dict representations
    # Keys: 'key': -> "key":
    cleaned_quotes = re.sub(r"'\s*(\w+)\s*'\s*:", r'"\1":', cleaned)
    # String values: : 'value' -> : "value"
    cleaned_quotes = re.sub(r":\s*'\s*([^']*)\s*'", r': "\1"', cleaned_quotes)
    # String values in arrays: [ 'value1', 'value2' ] -> [ "value1", "value2" ]
    cleaned_quotes = re.sub(r"'\s*([^']*)\s*'\s*([,\]])", r'"\1"\2', cleaned_quotes)
    cleaned_quotes = re.sub(r"([,\[])\s*'\s*([^']*)\s*'", r'\1"\2"', cleaned_quotes)
    
    try:
        return json.loads(cleaned_quotes)
    except Exception:
        pass
        
    # Fallback to standard loads on cleaned
    return json.loads(cleaned)

def _scrub_hallucinated_json(text: str) -> str:
    """Remove raw JSON tool-call blocks that the model sometimes hallucinates."""
    if not text:
        return ""
    text = re.sub(r'```(?:json)?\s*\{\s*"name".*?\}\s*```', '', text, flags=re.DOTALL)
    text = re.sub(r'\{\s*"name"\s*:\s*".*?"(?:.|\n)*?\}', '', text, flags=re.DOTALL)
    return text.strip()

def _parse_response(response):
    """Convert an Ollama response object into a plain dict for history."""
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
    
    try:
        parsed = repair_and_parse_json(text)
        # Handle nested "function" key (Ollama schema style)
        if "function" in parsed and isinstance(parsed["function"], dict):
            func_data = parsed["function"]
        else:
            func_data = parsed

        if isinstance(func_data, dict) and "name" in func_data:
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

def check_ollama_status() -> dict:
    """Verify if the local Ollama daemon is active and return information about available models."""
    from ollama import Client
    try:
        client = Client()
        models_resp = client.list()
        models = getattr(models_resp, 'models', [])
        return {
            "online": True,
            "model_count": len(models),
            "models": [getattr(m, 'model', getattr(m, 'name', 'Unknown')) for m in models]
        }
    except Exception as e:
        return {
            "online": False,
            "error": str(e),
            "model_count": 0,
            "models": []
        }

def get_available_models():
    """Fetch the list of available local models using the Ollama library."""
    status = check_ollama_status()
    if not status["online"]:
        return f"Error: Ollama is unreachable. Please make sure it is running."
    
    model_list = []
    from ollama import Client
    try:
        client = Client()
        models_resp = client.list()
        for m in models_resp.models:
            name = getattr(m, 'model', getattr(m, 'name', 'Unknown'))
            size = getattr(m, 'size', 0)
            size_gb = size / (1024**3)
            model_list.append(f"- {name} ({size_gb:.1f} GB)")
        return "\n".join(model_list)
    except Exception as e:
        return f"Error fetching models: {e}"

def auto_select_models():
    """Automatically detect and select Brain and Worker models from local Ollama library, supporting env overrides."""
    # Check env-vars first
    env_brain = os.environ.get("SANS_BRAIN_MODEL")
    env_worker = os.environ.get("SANS_WORKER_MODEL")
    
    if env_brain and env_worker:
        return env_brain, env_worker

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
            return env_brain or "gemma2:latest", env_worker or "phi3:mini"
            
        # Sort by size (descending) - assume larger is smarter (Brain)
        all_models.sort(key=lambda x: x['size'], reverse=True)
        
        brain = env_brain or all_models[0]['name']
        
        if env_worker:
            worker = env_worker
        elif len(all_models) > 1:
            # Pick a smaller model for worker if possible
            worker_candidates = [m['name'] for m in all_models if any(x in m['name'].lower() for x in ['mini', 'small', 'tiny', '3b', '1b', 'phi'])]
            if worker_candidates and worker_candidates[0] != brain:
                worker = worker_candidates[0]
            else:
                # If the second model is not the same as brain, use it
                worker = all_models[1]['name'] if all_models[1]['name'] != brain else all_models[0]['name']
        else:
            worker = brain
            
        return brain, worker
    except Exception:
        return env_brain or "gemma2:latest", env_worker or "phi3:mini"
