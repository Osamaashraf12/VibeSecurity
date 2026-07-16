import sys
from pathlib import Path

# Ensure the project root is in sys.path FIRST so all absolute imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import os
import requests
from dotenv import load_dotenv, set_key, find_dotenv

from backend.core.registry import TOOL_REGISTRY
from backend.core.paths import PROMPTS_DIR
from backend.core.schemas import (
    SubenumerArgs, SubbforcerArgs, SubpermuterArgs, SubcheckerArgs,
    SubcrawlerArgs, JsAnalyzerArgs, LinkAnalyzerArgs, TechDetectorArgs, AIHackerArgs,
)

# Load env from the project root or current directory
load_dotenv(find_dotenv())

class LLMClient:
    # --- DEFAULTS (Fallbacks) ---
    DEFAULT_AGENT_LOOP = """
OPERATIONAL LOOP
You operate as a manual penetration tester analyzing HTTP traffic. Follow this sequence strictly:
1. CONSUME: Read the provided HTTP Request/Response pairs.
2. MAP LOGIC: Identify the purpose of the endpoint.
3. HYPOTHESIZE: Flag specific parameters, headers, or API routes that are vulnerable.
4. REPORT: Output a precise, technical explanation of the vulnerability and exploit payload.
"""

    DEFAULT_MODULES = """
Asset Discovery: root_hunter, sub_enumer, sub_bforcer, sub_permuter, sub_checker
Content Discovery: tech_detector, sub_crawler, js_analyzer, link_analyzer, git_hunter, param_reflector
Exploitation: vuln_scan
"""

    def __init__(self):
        # 1. Dynamic Path Resolution
        self.ROOT_DIR = Path(__file__).resolve().parent.parent.parent
        self.PROMPTS_DIR = PROMPTS_DIR

        # 2. Setup Gists and URLs
        self.GIST_ID_MAIN = "bdc88302226dbad149676f6b1b299a52"
        self.GIST_ID_HACKER = "18bff2245696248fb9387ecf1c1dad48"
        
        self.urls = {
            "main": os.getenv("OLLAMA_URL_MAIN"),
            "hacker": os.getenv("OLLAMA_URL_HACKER")
        }
        
        self._refresh_urls()

        # 3. Load Context Assets
        self.context_assets = {}
        self._load_context_assets()

        # 4. Define Personas & Base Models
        self.base_models_map = {
            "chat": "mistral:7b",
            "parser_user": "qwen2.5:7b",
            "hacker": "deepseek-r1:14b"
        }

        self.active_agents = {}
        # Chat history is file-backed and cached in memory for performance.
        self.histories = {}

        # 5. Initialization Sequence
        if self.urls["main"] or self.urls["hacker"]:
            self._ensure_base_models()
            self._create_agents_factory()
            self._keep_agents_alive()
            print("\n[+] System Ready. Agents online and locked in memory.")
        else:
            print("\n[!] System Ready (Offline Mode). LLM URLs not found.")

    def _fetch_url_from_gist(self, gist_id):
        """Fetches a URL from a specific GitHub Gist."""
        try:
            api_url = f"https://api.github.com/gists/{gist_id}"
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                content = response.json()['files']['ollama_url.txt']['content']
                return content.split()[0].strip()
        except Exception as e:
            print(f"[-] URL Fetch Warning for {gist_id}: {e}")
        return None

    def _refresh_urls(self):
        """Fetches dynamic Ollama URLs for both main and hacker servers."""
        print("Fetching Cloudflare URLs from Gists...")
        env_path = find_dotenv(usecwd=True) or (self.ROOT_DIR / ".env")
        
        main_url = self._fetch_url_from_gist(self.GIST_ID_MAIN)
        if main_url:
            self.urls["main"] = main_url
            set_key(str(env_path), "OLLAMA_URL_MAIN", main_url)
            os.environ["OLLAMA_URL_MAIN"] = main_url
            print(f"[+] Main URL: {main_url}")

        hacker_url = self._fetch_url_from_gist(self.GIST_ID_HACKER)
        if hacker_url:
            self.urls["hacker"] = hacker_url
            set_key(str(env_path), "OLLAMA_URL_HACKER", hacker_url)
            os.environ["OLLAMA_URL_HACKER"] = hacker_url
            print(f"[+] Hacker URL: {hacker_url}")

    def _get_url(self, persona):
        """Routes to the correct server based on persona."""
        if persona == "hacker":
            return self.urls["hacker"]
        return self.urls["main"]

    def _read_file_or_default(self, filename, default_value, label):
        """Helper to safely read a file from PROMPTS_DIR or return default."""
        filepath = self.PROMPTS_DIR / filename
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                print(f"    Loaded {label} from {filepath.name}")
                return content
        else:
            print(f"    Missing {filename}, using default {label}.")
            return default_value.strip()

    def _load_context_assets(self):
        """Loads agent_loop and modules from disk."""
        print("\n--- Loading Context Assets ---")
        self.PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

        self.context_assets["AGENT_LOOP"] = self._read_file_or_default("agent_loop.txt", self.DEFAULT_AGENT_LOOP, "Agent Loop")
        self.context_assets["MODULES"] = self._read_file_or_default("modules.txt", self.DEFAULT_MODULES, "Modules")

    def _ensure_base_models(self):
        """Checks if base models exist on their respective servers; pulls them if not."""
        print("\n--- Checking Base Models ---")
        
        for persona, model in self.base_models_map.items():
            base_url = self._get_url(persona)
            if not base_url:
                continue
                
            tags_endpoint = f"{base_url}/api/tags"
            pull_endpoint = f"{base_url}/api/pull"
            
            try:
                r = requests.get(tags_endpoint, timeout=3)
                installed_models = [m["name"] for m in r.json().get("models", [])]
            except Exception:
                installed_models = []

            if model not in installed_models:
                print(f"[-] Pulling base model: {model} on {base_url}...")
                try:
                    requests.post(pull_endpoint, json={"name": model}, timeout=30)
                except Exception as e:
                    print(f"[!] Failed to pull {model}: {e}")
            else:
                print(f"[+] Base model ready: {model}")

    def _create_agents_factory(self):
        """Reads persona files and creates custom Agents in Ollama."""
        print("\n--- Factory: Creating Custom Agents ---")

        for persona, base_model in self.base_models_map.items():
            base_url = self._get_url(persona)
            if not base_url:
                self.active_agents[persona] = base_model
                continue
                
            create_endpoint = f"{base_url}/api/create"
            prompt_file = self.PROMPTS_DIR / f"hat_{persona}.txt"

            if prompt_file.exists():
                with open(prompt_file, "r", encoding="utf-8") as f:
                    specific_instruction = f.read().strip()
            else:
                specific_instruction = f"You are a helpful assistant specialized in {persona}."

            # Isolate Hacker Context vs Standard Agent Context
            if persona == "hacker":
                context_block = f"\n# OPERATIONAL LOGIC\n{self.context_assets['AGENT_LOOP']}\n"
            else:
                context_block = f"\n# KNOWLEDGE BASE\n{self.context_assets['MODULES']}\n"
            
            full_system_prompt = f"{specific_instruction}\n\n{context_block}".strip()
            agent_name = f"agent_{base_model}_{persona}".replace(":", "_")

            print(f"[*] Building '{agent_name}' on {base_url}...") 
            payload = {"model": agent_name, "from": base_model, "system": full_system_prompt}
            try:
                res = requests.post(create_endpoint, json=payload, timeout=30)
                res.raise_for_status()
                self.active_agents[persona] = agent_name
                print("    Success")
            except Exception as e:
                print(f"    Failed: {e}")
                self.active_agents[persona] = base_model

    def _keep_agents_alive(self):
        """Send a request to keep the created custom agents loaded indefinitely."""
        print("\n--- Persistence: Keeping Agents Alive ---")
        
        for persona, agent_name in self.active_agents.items():
            base_url = self._get_url(persona)
            if not base_url:
                continue
                
            generate_endpoint = f"{base_url}/api/generate"
            payload = {"model": agent_name, "keep_alive": -1}
            try:
                requests.post(generate_endpoint, json=payload, timeout=300)
                print(f"    Kept alive: {agent_name}")
            except requests.exceptions.ReadTimeout:
                print(f"    Kept alive (signal sent, took longer than 300s): {agent_name}")
            except Exception as e:
                print(f"    Persistence warning: {e}")

    def get_ollama_tools_schema(self):
        """Generates the JSON schema array for Ollama tool calling."""
        schema_map = {
            "sub_enumer": SubenumerArgs,
            "sub_bforcer": SubbforcerArgs,
            "sub_permuter": SubpermuterArgs,
            "sub_checker": SubcheckerArgs,
            "sub_crawler": SubcrawlerArgs,
            "js_analyzer": JsAnalyzerArgs,
            "link_analyzer": LinkAnalyzerArgs,
            "tech_detector": TechDetectorArgs,
            "ai_hacker": AIHackerArgs,
        }
        
        tools_array = []
        for key, model_class in schema_map.items():
            if key in TOOL_REGISTRY:
                metadata = TOOL_REGISTRY[key]
                tools_array.append({
                    "type": "function",
                    "function": {
                        "name": key,
                        "description": metadata.description,
                        "parameters": model_class.model_json_schema()
                    }
                })
        return tools_array

    def chat(self, user_input, persona, history=False, format=None, tools=None):
        """Sends a message to the agent."""
        base_url = self._get_url(persona)
        if not base_url:
            return {"error": f"LLM Client not connected for persona: {persona}."}

        chat_endpoint = f"{base_url}/api/chat"
        model = self.active_agents.get(persona, self.base_models_map.get(persona, "mistral:7b"))
        user_msg = {"role": "user", "content": user_input}

        if history:
            # Load history from local runtime storage if not cached.
            if persona not in self.histories:
                try:
                    from backend.core.chat_storage import get_chat_history
                    self.histories[persona] = get_chat_history(persona)
                except Exception:
                    self.histories[persona] = []
            messages = self.histories[persona] + [user_msg]
        else:
            messages = [user_msg]

        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        if tools is not None:
            payload["tools"] = tools
        if format:
            payload["format"] = format

        try:
            response = requests.post(chat_endpoint, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            ai_msg = result.get('message', {'role': 'assistant', 'content': ''})

            # Check for structured tool_calls returned by Ollama
            if 'tool_calls' in ai_msg and ai_msg['tool_calls']:
                return {"tool_calls": ai_msg['tool_calls']}

            if history:
                self.histories[persona].append(user_msg)
                self.histories[persona].append(ai_msg)
                # Persist to local runtime storage.
                try:
                    from backend.core.chat_storage import append_chat_messages
                    append_chat_messages(persona, [user_msg, ai_msg])
                except Exception:
                    pass  # Non-fatal
                
            return result

        except Exception as e:
            return {"error": str(e)}

    def clear_history(self, persona=None):
        if persona:
            if persona in self.histories:
                self.histories[persona] = []
                print(f"[*] History cleared for '{persona}'.")
        else:
            self.histories = {}
            print("[*] All histories cleared.")
        # Clear from local runtime storage too.
        try:
            from backend.core.chat_storage import clear_chat_history
            clear_chat_history(persona)
        except Exception:
            pass  # Non-fatal

    def get_running_models(self):
        """Fetches currently loaded models from all configured Ollama servers."""
        all_models = []
        unique_urls = set(url for url in self.urls.values() if url)
        
        for base_url in unique_urls:
            ps_endpoint = f"{base_url}/api/ps"
            try:
                response = requests.get(ps_endpoint, timeout=5)
                response.raise_for_status()
                data = response.json()
                if "models" in data:
                    all_models.extend(data["models"])
            except Exception as e:
                print(f"    Failed to fetch loaded models from {base_url}: {e}")
                
        return {"models": all_models}
