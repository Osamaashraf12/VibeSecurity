from fastapi import APIRouter
from pydantic import BaseModel
from backend.core.orchestration import Orchestrator

router = APIRouter()

class ScanRequest(BaseModel):
    target: str
    options: dict = {}

@router.post("/vuln-scan")
async def run_vuln_scan(req: ScanRequest):
    return Orchestrator().run_tool("vuln_scan", req.target, req.options)

@router.post("/active-verify")
async def run_active_verifiers(req: ScanRequest):
    return Orchestrator().run_tool("active_verifiers", req.target, req.options)

@router.post("/ai-hacker")
async def run_ai_hacker_api(req: ScanRequest):
    return Orchestrator().run_tool("ai_hacker", req.target, req.options)