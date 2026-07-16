import importlib
from pathlib import Path
from typing import Callable, Optional
import sys

from backend.core.registry import TOOL_REGISTRY
from backend.core.schemas import ToolContext

# Temporarily store tools during import collection
_PLUGIN_REGISTRY = []
PLUGIN_FUNCS = {}

def vibe_tool(submodule: str, tool_id: str, tool_name: str, category: str, ext: str = "txt"):
    """
    Decorator to mark a function as a VibeSecurity dynamically loaded tool.
    
    :param submodule: The parent module defined in registry.py (e.g. 'sub_enumer')
    :param tool_id: Internal ID for orchestrator (e.g. 'amass')
    :param tool_name: Frontend display name (e.g. 'Amass')
    :param category: Output grouping category (e.g. 'asset', 'content')
    :param ext: Output file extension (e.g. 'txt', 'json')
    """
    def decorator(func: Callable):
        _PLUGIN_REGISTRY.append({
            "func": func,
            "submodule": submodule,
            "tool_id": tool_id,
            "tool_name": tool_name,
            "category": category,
            "ext": ext
        })
        return func
    return decorator
_plugins_loaded = False

def load_plugins(mcp_server=None, safe_execute_fn=None, create_context_fn=None):
    """
    Scans the `backend/modules` directory for any wrapper files,
    imports them to trigger the @vibe_tool decorators,
    and dynamically binds them to the FastMCP server and internal TOOL_REGISTRY.
    """
    global _plugins_loaded
    if _plugins_loaded:
        print("ℹ️ [Loader] Plugins already loaded, skipping re-scan.", file=sys.stderr)
        return
    _plugins_loaded = True
    modules_dir = Path(__file__).resolve().parent.parent / "modules"
    
    # 1. Dynamically import all python files in recon and exploitation folders
    # The @vibe_tool decorator is the gatekeeper — only decorated functions register.
    for path in modules_dir.rglob("*.py"):
        if path.name.startswith("__") or path.name.startswith("_"):
            continue

        # Construct the full python module path (e.g., backend.modules.recon.asset.amass_wrapper)
        vibe_root = modules_dir.parent.parent
        try:
            rel_path = path.relative_to(vibe_root)
            module_name = ".".join(rel_path.with_suffix("").parts)
            importlib.import_module(module_name)
        except Exception as e:
            print(f"⚠️ [Loader] Failed to import {path.name}: {e}", file=sys.stderr)

    # 2. Register collected plugins into submodules and MCP
    for plugin in _PLUGIN_REGISTRY:
        sub = plugin["submodule"]
        t_id = plugin["tool_id"]
        t_name = plugin["tool_name"]
        cat = plugin["category"]
        ext = plugin["ext"]
        run_func = plugin["func"]
        
        PLUGIN_FUNCS[t_id] = run_func
        
        # A. Register in Frontend/Registry Submodule config
        if sub in TOOL_REGISTRY:
            if TOOL_REGISTRY[sub].available_tools is None:
                TOOL_REGISTRY[sub].available_tools = {}
            TOOL_REGISTRY[sub].available_tools[t_id] = t_name
        else:
            print(f"⚠️ [Loader] Submodule '{sub}' not found in registry.py for tool '{t_id}'.", file=sys.stderr)
            
        # B. Register dynamically in FastMCP (Only if server provided)
        if mcp_server and safe_execute_fn and create_context_fn:
            mcp_name = f"run_{t_id}"
            
            # Use a factory pattern to capture variables and bind them tightly
            def make_proxy(_run_func, _t_id, _cat, _ext, _mcp_name):
                def mcp_proxy(target: str, options: Optional[dict] = None) -> str:
                    ctx = create_context_fn(target, options)
                    return safe_execute_fn(ctx, _run_func, _t_id, _cat, _ext)
                mcp_proxy.__name__ = _mcp_name
                mcp_proxy.__doc__ = f"Autoloaded via Plugin System: {t_name}"
                return mcp_proxy
                
            mcp_proxy = make_proxy(run_func, t_id, cat, ext, mcp_name)
            
            mcp_server.add_tool(mcp_proxy)
        
    print(f"✅ [Loader] Successfully auto-discovered and registered {len(_PLUGIN_REGISTRY)} tools.", file=sys.stderr)
