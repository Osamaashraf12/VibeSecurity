"""Session manager for the Hunter Agent LangGraph pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from backend.agents.hunter_agent.graph import build_graph
from backend.agents.hunter_agent.state import build_initial_state, make_status
from backend.core.paths import HUNTER_SESSIONS_DIR, ensure_runtime_dirs

logger = logging.getLogger(__name__)

_sessions: dict[str, HunterSession] = {}
_graph = None
_active_tasks: set[asyncio.Task] = set()


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


class HunterSession:
    """Tracks one Hunter Agent scan session."""

    def __init__(self, session_id: str, target: str):
        self.session_id = session_id
        self.target = target
        self.status_log: list[dict[str, Any]] = []
        self.complete = False
        self.current_phase = "initializing"
        self.result: dict[str, Any] | None = None
        self.error: str | None = None
        self.start_time = time.time()
        self._task: asyncio.Task | None = None

    @property
    def snapshot_path(self):
        return HUNTER_SESSIONS_DIR / f"{self.session_id}.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "target": self.target,
            "complete": self.complete,
            "current_phase": self.current_phase,
            "error": self.error,
            "duration": int(time.time() - self.start_time),
            "start_time": self.start_time,
            "status_log": self.status_log,
            "result": self.result,
        }

    def save_snapshot(self) -> None:
        ensure_runtime_dirs()
        tmp_path = self.snapshot_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=True)
        tmp_path.replace(self.snapshot_path)

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> HunterSession:
        session = cls(
            session_id=data.get("session_id", ""),
            target=data.get("target", "(recovered)"),
        )
        session.complete = bool(data.get("complete", True))
        session.current_phase = data.get("current_phase", "recovered")
        session.error = data.get("error")
        session.result = data.get("result")
        session.status_log = data.get("status_log", [])
        session.start_time = data.get("start_time", time.time())
        return session


async def start_scan(target: str) -> str:
    """Start a new Hunter Agent scan and return its session id."""
    session_id = f"hunter_{uuid.uuid4().hex}"
    session = HunterSession(session_id, target)
    session.status_log.append(make_status("init", f"Starting Hunter Agent scan on {target}"))
    session.save_snapshot()

    _sessions[session_id] = session

    task = asyncio.create_task(_run_pipeline(session))
    session._task = task
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)

    logger.info("[hunter_agent] Started session %s for %s", session_id, target)
    return session_id


async def _run_pipeline(session: HunterSession) -> None:
    """Execute the LangGraph pipeline as a background task."""
    try:
        session.current_phase = "katana"
        session.save_snapshot()

        graph = _get_graph()
        initial_state = build_initial_state(session.target)
        initial_state["_start_time"] = session.start_time

        logger.info("[hunter_agent] Pipeline starting for %s", session.target)
        result = await graph.ainvoke(initial_state)

        if result.get("status_log"):
            session.status_log.extend(result["status_log"])

        session.result = result.get("report")
        session.current_phase = "complete"
        session.complete = True
        session.status_log.append(make_status("complete", "Scan complete. Report ready."))
        session.save_snapshot()

        logger.info("[hunter_agent] Pipeline complete for %s", session.target)

    except Exception as exc:
        logger.error("[hunter_agent] Pipeline failed: %s", exc, exc_info=True)
        session.error = str(exc)
        session.current_phase = "error"
        session.complete = True
        session.status_log.append(make_status("error", f"Pipeline failed: {exc}"))
        session.save_snapshot()


def get_session(session_id: str) -> HunterSession | None:
    """Get a live session or recover a completed snapshot from disk."""
    session = _sessions.get(session_id)
    if session:
        return session

    snapshot_path = HUNTER_SESSIONS_DIR / f"{session_id}.json"
    if not snapshot_path.exists():
        return None

    try:
        with open(snapshot_path, "r", encoding="utf-8") as handle:
            recovered = HunterSession.from_snapshot(json.load(handle))
        if not recovered.complete:
            recovered.complete = True
            recovered.current_phase = "recovered"
            recovered.error = "Session recovered after server restart. The live pipeline is no longer running."
            recovered.status_log.append(
                make_status("recovery", "Session recovered from runtime snapshot.")
            )
        return recovered
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[hunter_agent] Failed to recover session %s: %s", session_id, exc)
        return None


def get_all_sessions() -> list[dict[str, Any]]:
    return [session.to_dict() for session in _sessions.values()]
