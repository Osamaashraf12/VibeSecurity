"""HTTP routes for the Hunter Agent."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.agents.hunter_agent.hacker_agent import get_session, start_scan

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Hunter Agent"])


class HunterScanRequest(BaseModel):
    target: str


@router.post("/start")
async def hunter_start(req: HunterScanRequest):
    try:
        session_id = await start_scan(req.target)
        return {"session_id": session_id, "status": "started", "target": req.target}
    except Exception as exc:
        logger.error("Hunter start failed: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/status/{session_id}")
async def hunter_status(session_id: str, cursor: int = 0):
    session = get_session(session_id)
    if not session:
        return JSONResponse(status_code=404, content={
            "error": "Session not found. The server may have restarted.",
            "entries": [],
            "next_cursor": 0,
            "complete": False,
            "recoverable": False,
            "phase": "error",
        })

    entries = session.status_log[cursor:]
    return {
        "entries": entries,
        "next_cursor": cursor + len(entries),
        "complete": session.complete,
        "phase": session.current_phase,
        "error": session.error,
    }


@router.get("/report/{session_id}")
async def hunter_report(session_id: str):
    session = get_session(session_id)
    if not session:
        return JSONResponse(status_code=404, content={
            "error": "Session not found.",
            "complete": True,
        })

    if not session.complete:
        return JSONResponse(status_code=202, content={
            "status": "in_progress",
            "phase": session.current_phase,
        })

    if session.error:
        return JSONResponse(status_code=500, content={
            "error": session.error,
            "complete": True,
        })

    return session.result or {"error": "No report generated"}
