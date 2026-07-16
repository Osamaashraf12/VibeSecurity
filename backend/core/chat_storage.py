"""File-backed chat history storage."""

from __future__ import annotations

import json
from typing import Any

from backend.core.paths import CHAT_HISTORY_FILE, ensure_runtime_dirs

MAX_CHAT_MESSAGES = 50


def _read_store() -> dict[str, list[dict[str, Any]]]:
    if not CHAT_HISTORY_FILE.exists():
        return {}
    try:
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_store(store: dict[str, list[dict[str, Any]]]) -> None:
    ensure_runtime_dirs()
    tmp_path = CHAT_HISTORY_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2, ensure_ascii=True)
    tmp_path.replace(CHAT_HISTORY_FILE)


def get_chat_history(persona: str, limit: int = MAX_CHAT_MESSAGES) -> list[dict[str, Any]]:
    history = _read_store().get(persona, [])
    return history[-limit:] if isinstance(history, list) else []


def append_chat_messages(persona: str, messages: list[dict[str, Any]]) -> None:
    store = _read_store()
    history = store.setdefault(persona, [])
    history.extend(messages)
    store[persona] = history[-MAX_CHAT_MESSAGES:]
    _write_store(store)


def clear_chat_history(persona: str | None = None) -> None:
    if persona is None:
        _write_store({})
        return

    store = _read_store()
    store.pop(persona, None)
    _write_store(store)
