"""Central filesystem layout for VibeSecurity."""

from __future__ import annotations

import os
from pathlib import Path


def _project_root() -> Path:
    configured = os.getenv("VIBESEC_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _project_root()


def _configured_path(env_name: str, default: Path) -> Path:
    raw = os.getenv(env_name)
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


STATIC_DIR = _configured_path("VIBESEC_STATIC_DIR", PROJECT_ROOT / "data" / "static")
RUNTIME_DIR = _configured_path("VIBESEC_RUNTIME_DIR", PROJECT_ROOT / "var")

PROMPTS_DIR = STATIC_DIR / "prompts"
GF_PATTERNS_DIR = STATIC_DIR / "gf_patterns"
PAYLOADS_DIR = STATIC_DIR / "payloads"
WORDLISTS_DIR = STATIC_DIR / "wordlists"

SCAN_RESULTS_DIR = RUNTIME_DIR / "scan_results"
GENERATED_PAYLOADS_DIR = RUNTIME_DIR / "generated_payloads"
LOGS_DIR = RUNTIME_DIR / "logs"
HUNTER_SESSIONS_DIR = RUNTIME_DIR / "hunter_sessions"
RECIPES_FILE = RUNTIME_DIR / "recipes.json"
CHAT_HISTORY_FILE = RUNTIME_DIR / "chat_history.json"
LLM_CALL_LOG_FILE = LOGS_DIR / "llm_calls.jsonl"
QUOTA_FILE = RUNTIME_DIR / "quota_status.json"


def ensure_runtime_dirs() -> None:
    """Create runtime directories used by long-running scans and local state."""
    for path in (
        RUNTIME_DIR,
        SCAN_RESULTS_DIR,
        GENERATED_PAYLOADS_DIR,
        LOGS_DIR,
        HUNTER_SESSIONS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def resolve_runtime_path(*parts: str) -> Path:
    """Resolve a path below the configured runtime directory."""
    return (RUNTIME_DIR.joinpath(*parts)).resolve()


def resolve_static_path(*parts: str) -> Path:
    """Resolve a path below the configured static resource directory."""
    return (STATIC_DIR.joinpath(*parts)).resolve()
