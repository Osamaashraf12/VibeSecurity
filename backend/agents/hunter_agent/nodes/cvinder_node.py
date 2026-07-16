"""
Hunter Agent — CVINDER Node
==============================
Delegates to the existing cvinder_wrapper.run_cvinder() via ToolContext.
ToolContext.run_command() handles Docker execution automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlparse

from backend.core.paths import PROJECT_ROOT
from backend.core.schemas import ToolContext
from backend.modules.recon.content.cvinder_wrapper import run_cvinder
from backend.agents.hunter_agent.state import HackerState, make_status

logger = logging.getLogger(__name__)

BASE_DIR = PROJECT_ROOT


async def cvinder_node(state: HackerState) -> dict:
    """
    Run CVINDER on the target host via the standard cvinder_wrapper.
    Always sets cvinder_done=True, even on failure.
    """
    target = state["target"]
    parsed = urlparse(target)
    host = parsed.netloc or parsed.path
    if ":" in host:
        host = host.split(":")[0]

    logger.info(f"[cvinder_node] Scanning {host} for CVEs")
    status = [make_status("cvinder", f"Scanning {host} for known CVEs...")]

    try:
        ctx = ToolContext(target=host, base_dir=BASE_DIR)
        output_file = ctx.get_output_path("cvinder", "content", "json")

        def _run():
            run_cvinder(ctx, host, str(output_file))

        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=310)
        except asyncio.TimeoutError:
            logger.warning("[cvinder_node] CVINDER timed out after 300s")
            status.append(make_status("cvinder", "CVE scan timed out"))
            return {"cvinder_done": True, "cve_history": [], "status_log": status}

        # Read results written by the wrapper
        cve_results = []
        if output_file.exists():
            with open(output_file, "r", encoding="utf-8", errors="replace") as fh:
                raw = fh.read().strip()
            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        cve_results = data
                    elif isinstance(data, dict) and "cves" in data:
                        cve_results = data["cves"]
                except json.JSONDecodeError:
                    cve_results = _parse_text_output(raw)

        logger.info(f"[cvinder_node] Found {len(cve_results)} CVEs for {host}")
        status.append(make_status("cvinder", f"CVE scan complete: {len(cve_results)} CVEs found"))

        return {
            "cvinder_done": True,
            "cve_history": cve_results,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[cvinder_node] Failed: {e}", exc_info=True)
        status.append(make_status("cvinder", f"CVE scan error: {e}"))
        return {"cvinder_done": True, "cve_history": [], "status_log": status}


def _parse_text_output(text: str) -> list[dict]:
    """Fallback: extract CVE-XXXX-XXXX patterns from plain text output."""
    import re
    seen: set[str] = set()
    results = []
    for line in text.splitlines():
        for cve_id in re.findall(r"CVE-\d{4}-\d{4,}", line, re.IGNORECASE):
            cve_id = cve_id.upper()
            if cve_id not in seen:
                seen.add(cve_id)
                results.append({"cve_id": cve_id, "description": line.strip(), "source": "cvinder"})
    return results
