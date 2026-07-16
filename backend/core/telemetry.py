"""Lightweight file-backed telemetry helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from backend.core.paths import LLM_CALL_LOG_FILE, ensure_runtime_dirs


def log_llm_call(
    provider: str,
    model: str,
    node_name: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    was_fallback: bool = False,
    error: str | None = None,
    duration_ms: int | None = None,
    session_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one LLM call record to the local runtime JSONL log."""
    ensure_runtime_dirs()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "node_name": node_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "was_fallback": was_fallback,
        "error": error,
        "duration_ms": duration_ms,
        "session_id": session_id,
    }
    if extra:
        record["extra"] = extra

    with open(LLM_CALL_LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True))
        handle.write("\n")
