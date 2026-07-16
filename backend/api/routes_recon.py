from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any
import shutil

router = APIRouter()

# CLI tools used across modules
_REQUIRED_TOOLS = [
    "subfinder", "puredns", "alterx", "dnsx", "httpx",
    "katana", "gau", "gauplus", "gospider", "hakrawler",
    "waybackurls", "waymore", "gobuster", "ffuf",
    "jsluice", "trufflehog", "mantra", "jsecret", "jsleak",
    "gf", "uro", "urinteresting", "nuclei",
]

import asyncio

@router.get("/health")
async def recon_health():
    """Check which CLI recon tools are installed and available."""
    tools = {}
    for tool in _REQUIRED_TOOLS:
        tools[tool] = await asyncio.to_thread(lambda t: shutil.which(t) is not None, tool)

    installed = sum(1 for v in tools.values() if v)
    total = len(tools)
    return {
        "status": "healthy" if installed == total else "degraded",
        "installed": installed,
        "total": total,
        "tools": tools,
    }

class ScanRequest(BaseModel):
    target: str
    options: Dict[str, Any] = {}

# Notice we removed 'async' here
def run_tool_generic(request: Request, tool_key: str, req: ScanRequest):
    """
    Generic helper to execute tools via the global Orchestrator.
    Runs in a background thread to prevent blocking the FastAPI event loop.
    """
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized.")
    
    try:
        result = orchestrator.run_tool(tool_key, req.target, req.options)
        
        if isinstance(result, dict) and result.get("error"):
            raise HTTPException(status_code=400, detail=result.get("error"))
            
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ API Error ({tool_key}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools")
def list_tools():
    from backend.core.registry import TOOL_REGISTRY
    return [
        {"key": t.key, "name": t.name, "category": t.category, "requires": t.requires} 
        for t in TOOL_REGISTRY.values()
    ]

# --- ASSET DISCOVERY ENDPOINTS (Removed async/await) ---

@router.post("/asset/root-hunter")
def run_root_hunter(request: Request, req: ScanRequest):
    return {"status": "skipped"}

@router.post("/asset/subdomain-enum")
def run_subdomain_enum(request: Request, req: ScanRequest):
    return run_tool_generic(request, "sub_enumer", req)

@router.post("/asset/subdomain-brute")
def run_subdomain_brute(request: Request, req: ScanRequest):
    return run_tool_generic(request, "sub_bforcer", req)

@router.post("/asset/subdomain-permute")
def run_subdomain_permute(request: Request, req: ScanRequest):
    return run_tool_generic(request, "sub_permuter", req)

@router.post("/asset/subdomain-check")
def run_subdomain_check(request: Request, req: ScanRequest):
    return run_tool_generic(request, "sub_checker", req)

# --- CONTENT DISCOVERY ENDPOINTS ---

@router.post("/content/tech-detect")
def run_tech_detect(request: Request, req: ScanRequest):
    return run_tool_generic(request, "tech_detector", req)

@router.post("/content/crawl")
def run_crawler(request: Request, req: ScanRequest):
    return run_tool_generic(request, "sub_crawler", req)

@router.post("/content/js-analyze")
def run_js_analyze(request: Request, req: ScanRequest):
    return run_tool_generic(request, "js_analyzer", req)

@router.post("/content/link-analyze")
def run_link_analyze(request: Request, req: ScanRequest):
    return run_tool_generic(request, "link_analyzer", req)

@router.post("/content/git-leaks")
def run_git_leaks(request: Request, req: ScanRequest):
    return {"status": "skipped"}

@router.post("/content/param-reflect")
def run_param_reflect(request: Request, req: ScanRequest):
    return {"status": "skipped"}