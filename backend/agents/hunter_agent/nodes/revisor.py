"""
Hunter Agent — Revisor Node
==============================
Final quality gate: validates, rejects, and annotates findings.
"""

from __future__ import annotations

import json
import logging

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.agents.hunter_agent.prompts.revisor_prompt import (
    REVISOR_SYSTEM, build_revisor_prompt,
)

logger = logging.getLogger(__name__)

_openrouter = OpenRouterAgentClient()


async def revisor_node(state: HackerState) -> dict:
    """Validate, reject, and annotate findings."""
    beliefs = state.get("beliefs")
    if beliefs and hasattr(beliefs, "export"):
        findings = beliefs.export()
    else:
        findings = state.get("specialist_findings", [])

    chains = state.get("chains", [])
    poc_results = state.get("poc_results", [])

    logger.info(f"[revisor] Reviewing {len(findings)} findings")
    status = [make_status("revisor", f"Quality review of {len(findings)} findings...")]

    if not findings:
        status.append(make_status("revisor", "No findings to review"))
        return {
            "validated_findings": [],
            "rejected_findings": [],
            "revisor_notes": "No findings submitted for review.",
            "status_log": status,
        }

    try:
        findings_json = json.dumps(findings, indent=2)
        poc_json = json.dumps(poc_results, indent=2)
        chains_json = json.dumps(chains, indent=2) if chains else ""

        prompt = build_revisor_prompt(findings_json, poc_json, chains_json)

        result_text = await _openrouter.generate(
            prompt=prompt,
            system_prompt=REVISOR_SYSTEM,
            node_name="revisor",
        )

        result = json.loads(extract_json_from_response(result_text))

        validated = result.get("validated_findings", [])
        rejected = result.get("rejected_findings", [])
        notes = result.get("revisor_notes", "")

        # Build validated/rejected lists
        approved_ids = {v.get("id") for v in validated if v.get("approved", True)}
        rejected_ids = {r.get("id") for r in rejected}

        validated_findings = [f for f in findings if f.get("id") in approved_ids]
        rejected_findings_data = [f for f in findings if f.get("id") in rejected_ids]

        # Apply severity adjustments
        for v in validated:
            adj = v.get("severity_adjustment")
            if adj:
                for f in validated_findings:
                    if f.get("id") == v.get("id"):
                        f["severity"] = adj
                        break

        n_approved = len(validated_findings)
        n_rejected = len(rejected_findings_data)
        logger.info(f"[revisor] Approved {n_approved}, rejected {n_rejected}")
        status.append(make_status(
            "revisor",
            f"Review complete: {n_approved} approved, {n_rejected} rejected",
        ))

        return {
            "validated_findings": validated_findings,
            "rejected_findings": rejected_findings_data,
            "revisor_notes": notes,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[revisor] Failed: {e}", exc_info=True)
        status.append(make_status("revisor", f"Review failed: {e}. Passing all findings through."))
        # On failure, pass all findings through unfiltered
        return {
            "validated_findings": findings,
            "rejected_findings": [],
            "revisor_notes": f"Revisor failed: {e}. All findings passed through unfiltered.",
            "status_log": status,
        }
