"""
Hunter Agent - Katana Node
=============================
Delegates to the existing katana_wrapper.run_katana() via ToolContext.
ToolContext.run_command() handles Docker execution automatically.
"""

from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import httpx
from urllib.parse import urlparse

from backend.core.paths import PROJECT_ROOT
from backend.core.schemas import ToolContext
from backend.modules.recon.content.katana_wrapper import run_katana
from backend.agents.hunter_agent.state import HackerState, make_status

logger = logging.getLogger(__name__)

BASE_DIR = PROJECT_ROOT


async def _warm_up_target(url: str, max_wait: int = 60) -> bool:
    """
    Poll the target URL until it returns a non-503 status or max_wait seconds elapse.
    Returns True if the target came up, False if it stayed down.
    """
    deadline = asyncio.get_event_loop().time() + max_wait
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(url)
                if r.status_code != 503:
                    return True
            except Exception:
                pass
            await asyncio.sleep(5)
    return False


async def katana_node(state: HackerState) -> dict:
    """
    Crawl the target URL using Katana via the standard katana_wrapper.
    Parses JSONL output into endpoint dicts for downstream nodes.

    Cache behaviour: if a non-empty katana output file already exists for
    this target, the crawl is skipped and the cached results are used instead.
    Delete the file manually to force a fresh crawl.
    """
    target = state["target"]
    logger.info(f"[katana_node] Crawling target: {target}")

    parsed = urlparse(target)
    domain = parsed.netloc or parsed.path
    full_url = target if target.startswith(("http://", "https://")) else f"https://{domain}"

    status = [make_status("katana", f"Crawling {target}...")]

    try:
        ctx = ToolContext(target=domain, base_dir=BASE_DIR)
        output_file = ctx.get_output_path("katana", "content", "json")

        # ── Cache hit: skip crawl if output already exists and is non-empty ──
        if output_file.exists() and output_file.stat().st_size > 0:
            logger.info(f"[katana_node] Cache hit — reusing existing output: {output_file.name}")
            status.append(make_status("katana", f"Using cached katana output ({output_file.name})"))
        else:
            # Pre-warm: wait for sleeping dynos to wake up
            status.append(make_status("katana", "Checking target availability..."))
            is_up = await _warm_up_target(full_url)
            if not is_up:
                logger.warning(f"[katana_node] Target {full_url} returned 503 for 60s — crawling anyway")
                status.append(make_status("katana", "Target returned 503 (may be sleeping). Crawling anyway..."))
            else:
                status.append(make_status("katana", "Target is up. Starting crawl..."))

            def _run():
                run_katana(ctx, full_url, "DIRECT", str(output_file))

            status.append(make_status("katana", "Running katana crawl (this may take a minute)..."))
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _run)

        # Parse katana output — handles both JSONL (one obj/line) and
        # pretty-printed multi-line objects written by some katana versions.
        katana_output = []
        if output_file.exists():
            raw_text = output_file.read_text(encoding="utf-8", errors="replace")
            decoder = json.JSONDecoder()
            idx = 0
            while idx < len(raw_text):
                # Skip whitespace/newlines between objects
                while idx < len(raw_text) and raw_text[idx] in " \t\r\n":
                    idx += 1
                if idx >= len(raw_text):
                    break
                try:
                    obj, end_idx = decoder.raw_decode(raw_text, idx)
                    katana_output.append(obj)
                    idx = end_idx
                except json.JSONDecodeError:
                    idx += 1  # skip bad char and keep scanning


        # Parse into endpoint inventory
        endpoints = []
        for entry in katana_output:
            url = entry.get("request", {}).get("endpoint", entry.get("endpoint", ""))
            if not url:
                url = entry.get("url", "")

            ep_id = f"ep-{hashlib.md5(url.encode()).hexdigest()[:8]}"
            method = entry.get("request", {}).get("method", "GET")
            raw_request = entry.get("request", {}).get("raw", "")
            raw_response = entry.get("response", {}).get("raw", "")

            endpoints.append({
                "id": ep_id,
                "url": url,
                "method": method,
                "parameters": _extract_params(url, entry),
                "raw_request": raw_request,
                "raw_response": raw_response,
            })

        logger.info(f"[katana_node] Parsed {len(endpoints)} endpoints from katana output")
        status.append(make_status("katana", f"Crawl complete: {len(endpoints)} endpoints found"))

        return {
            "katana_output": katana_output,
            "endpoint_inventory": endpoints,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[katana_node] Failed: {e}", exc_info=True)
        status.append(make_status("katana", f"Katana crawl error: {e}"))
        return {
            "katana_output": [],
            "endpoint_inventory": [],
            "status_log": status,
        }


def _extract_params(url: str, entry: dict) -> list[str]:
    """Extract parameter names from URL and request body."""
    params = []
    parsed = urlparse(url)
    if parsed.query:
        for part in parsed.query.split("&"):
            if "=" in part:
                params.append(part.split("=")[0])

    body = entry.get("request", {}).get("body", "")
    if body:
        try:
            body_json = json.loads(body)
            if isinstance(body_json, dict):
                params.extend(body_json.keys())
        except (json.JSONDecodeError, TypeError):
            for part in body.split("&"):
                if "=" in part:
                    params.append(part.split("=")[0])

    return list(set(params))
