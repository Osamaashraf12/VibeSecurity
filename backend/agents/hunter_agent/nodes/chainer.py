"""
Hunter Agent — Chainer Node
==============================
Identifies multi-step attack chains from individual findings.
Uses OpenRouter via OpenRouterAgentClient.
"""

from __future__ import annotations

import json
import logging

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.agents.hunter_agent.prompts.chainer_prompt import (
    CHAINER_SYSTEM, build_chainer_prompt,
)

logger = logging.getLogger(__name__)

_or_client = OpenRouterAgentClient()


async def chainer_node(state: HackerState) -> dict:
    """Identify attack chains from merged findings."""
    beliefs = state.get("beliefs")
    if beliefs and hasattr(beliefs, "export"):
        findings = beliefs.export()
    else:
        findings = state.get("specialist_findings", [])

    logger.info(f"[chainer] Analyzing {len(findings)} findings for chains")
    status = [make_status("chainer", f"Searching for attack chains in {len(findings)} findings...")]

    if not findings:
        status.append(make_status("chainer", "No findings to chain"))
        return {"chains": [], "status_log": status}

    try:
        findings_json = json.dumps(findings, indent=2)
        attacker_model = json.dumps(state.get("attacker_model", {}), indent=2)

        prompt = build_chainer_prompt(findings_json, attacker_model)

        result_text = await _or_client.generate(
            prompt=prompt,
            system_prompt=CHAINER_SYSTEM,
            node_name="chainer",
        )

        result = json.loads(extract_json_from_response(result_text))
        chains = result.get("chains", [])

        logger.info(f"[chainer] Identified {len(chains)} attack chains")
        status.append(make_status("chainer", f"Found {len(chains)} attack chains"))

        return {
            "chains": chains,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[chainer] Failed: {e}", exc_info=True)
        status.append(make_status("chainer", f"Chain analysis failed: {e}"))
        return {"chains": [], "status_log": status}
