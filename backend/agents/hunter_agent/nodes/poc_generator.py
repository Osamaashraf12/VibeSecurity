"""
Hunter Agent — PoC Generator Node
====================================
Generates concrete proof-of-concept requests for findings.
"""

from __future__ import annotations

import json
import logging

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.agents.hunter_agent.prompts.poc_generator_prompt import (
    POC_GENERATOR_SYSTEM, build_poc_generator_prompt,
)

logger = logging.getLogger(__name__)

_openrouter = OpenRouterAgentClient()


async def poc_generator_node(state: HackerState) -> dict:
    """Generate PoC requests for validated findings."""
    beliefs = state.get("beliefs")
    if beliefs and hasattr(beliefs, "get_viable_for_poc"):
        findings = beliefs.get_viable_for_poc()
    elif beliefs and hasattr(beliefs, "export"):
        findings = beliefs.export()
    else:
        findings = state.get("specialist_findings", [])

    chains = state.get("chains", [])
    target = state.get("target", "")

    logger.info(f"[poc_generator] Generating PoCs for {len(findings)} findings")
    status = [make_status("poc_generator", f"Generating PoCs for {len(findings)} findings...")]

    if not findings:
        status.append(make_status("poc_generator", "No findings for PoC generation"))
        return {"poc_results": [], "status_log": status}

    try:
        findings_json = json.dumps(findings, indent=2)
        chains_json = json.dumps(chains, indent=2) if chains else ""

        prompt = build_poc_generator_prompt(findings_json, chains_json, target)

        result_text = await _openrouter.generate(
            prompt=prompt,
            system_prompt=POC_GENERATOR_SYSTEM,
            node_name="poc_generator",
        )

        result = json.loads(extract_json_from_response(result_text))
        poc_results = result.get("poc_results", [])

        # Update findings in beliefs with PoC viability
        if beliefs and hasattr(beliefs, "update"):
            for poc in poc_results:
                fid = poc.get("finding_id", "")
                if fid:
                    beliefs.update(fid,
                        poc_viable=poc.get("viable", False),
                        poc_request=poc.get("http_request", ""),
                    )

        viable = sum(1 for p in poc_results if p.get("viable"))
        logger.info(f"[poc_generator] Generated {len(poc_results)} PoCs ({viable} viable)")
        status.append(make_status("poc_generator", f"Generated {len(poc_results)} PoCs ({viable} viable)"))

        return {
            "poc_results": poc_results,
            "beliefs": beliefs,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[poc_generator] Failed: {e}", exc_info=True)
        status.append(make_status("poc_generator", f"PoC generation failed: {e}"))
        return {"poc_results": [], "status_log": status}
