from fastapi import APIRouter
from backend.core.registry import TOOL_REGISTRY

router = APIRouter()

# --- Flow Metadata Map ---
# Maps each tool key to the "In: ... | Out: ..." string that the frontend
# flow builder uses to render input/output port circles on canvas nodes.
FLOW_META_MAP = {
    "target_input": "Out: Target",
    "sub_enumer":   "In: Target | Out: Subdomains",
    "sub_bforcer":  "In: Target, Wordlist | Out: Subdomains",
    "sub_permuter": "In: Subdomains | Out: Permutations",
    "sub_checker":  "In: Subdomains | Out: Live Hosts",
    "sub_Vhost":    "In: Live Hosts, Wordlist | Out: VHosts",
    "sub_crawler":  "In: Live Hosts | Out: URLs",
    "js_analyzer":  "In: URLs | Out: JS Secrets",
    "link_analyzer":"In: URLs, JS Data | Out: Patterns",
    "tech_detector":"In: URLs | Out: Tech Stack",
    "vuln_scan":    "In: URLs, Tech Stack | Out: Vulns",
    "active_verifiers": "In: Patterns, Tech Stack | Out: Verified Vulns",
    "logic_probers":"In: URLs | Out: Logic Flaws",
}

# Tools that should NOT appear in any frontend module list
# (internal utilities or tools that have their own dedicated page)
_HIDDEN_TOOL_KEYS = {"ai_hacker"}

@router.get("/tools")
async def get_tools_config():
    """
    Returns the frontend TOOLS_CONFIG JSON dynamically built from the backend TOOL_REGISTRY.
    """
    inputs = [
        { "id": "target_input", "name": "User input", "description": "Enter target domain", "flowMeta": "Out: Target", "type": "input" }
    ]
    
    asset_discovery = []
    content_discovery = []
    vulnerability_scanning = []
    
    for key, meta in TOOL_REGISTRY.items():
        # Skip hidden/internal tools
        if meta.key in _HIDDEN_TOOL_KEYS:
            continue

        # Build the frontend object
        tool_obj = {
            "id": meta.key,
            "name": meta.name,
            "description": meta.description,
            "flowMeta": FLOW_META_MAP.get(meta.key, f"In: Target | Out: {meta.name}"),
            "type": "recon" if meta.category in ["asset", "content"] else "vuln",
            "availableTools": []
        }
        
        if meta.available_tools:
            for t_id, t_name in meta.available_tools.items():
                tool_obj["availableTools"].append({"id": t_id, "name": t_name})
                
        if meta.category == "asset":
            asset_discovery.append(tool_obj)
        elif meta.category == "content":
            content_discovery.append(tool_obj)
        elif meta.category == "exploitation":
            vulnerability_scanning.append(tool_obj)
            
    return {
        "inputs": inputs,
        "assetDiscovery": asset_discovery,
        "contentDiscovery": content_discovery,
        "vulnerabilityScanning": vulnerability_scanning
    }
