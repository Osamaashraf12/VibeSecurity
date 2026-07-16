"""
Hunter Agent — Threat Modeller Node
=====================================
Produces attacker model, attack surface map, and prioritized hypotheses.
"""

from __future__ import annotations

import json
import logging

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.agents.hunter_agent.prompts.threat_modeller_prompt import (
    THREAT_MODELLER_SYSTEM, build_threat_modeller_prompt,
)

logger = logging.getLogger(__name__)

_openrouter = OpenRouterAgentClient()


async def threat_modeller_node(state: HackerState) -> dict:
    """Produce threat model from synthesized intel + CVINDER results."""
    logger.info("[threat_modeller] Building threat model")
    status = [make_status("threat_model", "Building threat model...")]

    try:
        target_profile = json.dumps(state.get("target_profile", {}), indent=2)
        knowledge_graph = json.dumps(state.get("knowledge_graph", {}), indent=2)
        cve_history = json.dumps(state.get("cve_history", []), indent=2)

        prompt = build_threat_modeller_prompt(target_profile, knowledge_graph, cve_history)

        result_text = await _openrouter.generate(
            prompt=prompt,
            system_prompt=THREAT_MODELLER_SYSTEM,
            node_name="threat_modeller",
        )

        result = json.loads(extract_json_from_response(result_text))

        threat_model = {
            "hypotheses": result.get("hypotheses", []),
            "cve_correlations": result.get("cve_correlations", []),
        }
        attacker_model = result.get("attacker_model", {})
        attack_surface = result.get("attack_surface_map", {})

        n_hyp = len(threat_model["hypotheses"])
        logger.info(f"[threat_modeller] Generated {n_hyp} hypotheses")
        status.append(make_status(
            "threat_model",
            f"Threat model complete: {n_hyp} attack hypotheses generated",
        ))

        return {
            "threat_model": threat_model,
            "attacker_model": attacker_model,
            "attack_surface_map": attack_surface,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[threat_modeller] Failed: {e}", exc_info=True)
        status.append(make_status("threat_model", f"Threat modelling failed: {e}"))
        return {
            "threat_model": {"hypotheses": []},
            "attacker_model": {},
            "attack_surface_map": {},
            "status_log": status,
        }
