import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Ensure absolute backend imports work regardless of the launch directory.
file_path = Path(__file__).resolve()
backend_dir = file_path.parent
project_root = backend_dir.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(1, str(backend_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger("backend.agents.hunter_agent").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

from backend.api import (  # noqa: E402
    routes_ai,
    routes_config,
    routes_hunter,
    routes_recipes,
    routes_recon,
    routes_report,
    routes_scan,
    routes_workflow,
)

from backend.core.llm_client import LLMClient  # noqa: E402
from backend.core.orchestration import Orchestrator  # noqa: E402
from backend.core.paths import ensure_runtime_dirs  # noqa: E402
from backend.core.task_manager import task_manager  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[*] VibeSecurity Backend Initializing...")
    ensure_runtime_dirs()

    try:
        app.state.llm_client = LLMClient()
    except Exception as exc:
        print(f"[!] AI Server Unreachable: {exc}")
        app.state.llm_client = None

    try:
        from backend.core.openrouter_client import OpenRouterClient

        app.state.openrouter_client = OpenRouterClient()
        print("[+] OpenRouter Client initialized")
    except Exception as exc:
        print(f"[!] OpenRouter Client unavailable: {exc}")
        app.state.openrouter_client = None

    app.state.orchestrator = Orchestrator()
    app.state.task_manager = task_manager

    from backend.core.loader import load_plugins

    load_plugins()

    print("[+] System Ready")
    yield
    print("[*] System Shutting Down")

    try:
        from backend.agents.hunter_agent.hacker_agent import _active_tasks

        if _active_tasks:
            logger.info("[main] Cancelling %s active Hunter Agent tasks...", len(_active_tasks))
            for task in list(_active_tasks):
                task.cancel()
            import asyncio as _asyncio

            await _asyncio.gather(*_active_tasks, return_exceptions=True)
            logger.info("[main] All Hunter Agent tasks cancelled.")
    except Exception as exc:
        logger.warning("[main] Hunter Agent task cancellation failed: %s", exc)

    task_manager.shutdown(wait=True, cancel_futures=True)


app = FastAPI(title="VibeSecurity AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:8000").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

FRONTEND_BASE = project_root / "frontend"
if (FRONTEND_BASE / "static").exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_BASE / "static")), name="static")

app.include_router(routes_ai.router, prefix="/api", tags=["AI Engine"])
app.include_router(routes_report.router, tags=["Reporting"])
app.include_router(routes_config.router, prefix="/api/config", tags=["Configuration"])

app.include_router(
    routes_recon.router,
    prefix="/recon",
    tags=["Reconnaissance"],
)
app.include_router(
    routes_scan.router,
    prefix="/exploit",
    tags=["Vulnerability"],
)
app.include_router(
    routes_workflow.router,
    prefix="/workflow",
    tags=["Workflow Engine"],
)
app.include_router(
    routes_recipes.router,
    prefix="/recipes",
    tags=["Custom Recipes"],
)
app.include_router(
    routes_hunter.router,
    prefix="/api/hunter",
    tags=["Hunter Agent"],
)


@app.get("/api/quota/status", tags=["Quota"])
async def get_quota_status():
    """Return current OpenRouter API quota status."""
    openrouter = getattr(app.state, "openrouter_client", None)
    if openrouter:
        return openrouter.get_quota_status()
    return {"error": "OpenRouter unavailable", "remaining": 0, "limit": 0}


@app.get("/status/{task_id}", tags=["Task Polling"])
async def get_task_status(task_id: str):
    """Poll the status of a background task by its ID."""
    return task_manager.get_status(task_id)


@app.get("/status/chain/{chain_id}", tags=["Task Polling"])
async def get_chain_status(chain_id: str):
    """Poll the status of a workflow chain."""
    status = task_manager.get_status(chain_id)
    return {
        "chain_id": chain_id,
        "state": status.get("state", "NOT_FOUND"),
        "status": status.get("status", "Unknown"),
        "result": status.get("result"),
        "error": status.get("error"),
    }


@app.get("/")
async def read_index():
    index_path = FRONTEND_BASE / "templates" / "index.html"
    return FileResponse(index_path) if index_path.exists() else {"error": "UI missing"}
