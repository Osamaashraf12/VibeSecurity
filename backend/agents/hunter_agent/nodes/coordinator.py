"""
Hunter Agent — Coordinator Node
==================================
Two steps:
1. Dispatch: Assigns endpoints to specialists (≤15 per agent per batch).
   Slices raw HTTP pairs into each agent's assignment.
2. Checkpoint: Builds BeliefStore from merged specialist_findings.
"""

from __future__ import annotations

import json
import logging

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.belief_store import BeliefStore
from backend.agents.hunter_agent.knowledge_graph import AspectGraphBundle
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.core.llm.model_config import (
    MAX_ENDPOINTS_SINGLE_CALL, SPECIALIST_NAMES,
)
from backend.agents.hunter_agent.prompts.coordinator_prompt import (
    COORDINATOR_DISPATCH_SYSTEM, build_coordinator_dispatch_prompt,
)

logger = logging.getLogger(__name__)

_openrouter = OpenRouterAgentClient()


async def coordinator_dispatch_node(state: HackerState) -> dict:
    """
    Assign endpoints to specialist agents.
    Enforces MAX_ENDPOINTS_SINGLE_CALL per agent.
    Slices raw HTTP pairs from katana_output into assignments.
    """
    logger.info("[coordinator] Dispatching specialist assignments")
    status = [make_status("coordinator", "Assigning endpoints to specialist agents...")]

    try:
        threat_model = json.dumps(state.get("threat_model", {}), indent=2)

        # Strip raw HTTP bodies — coordinator only needs URL/method/params to assign.
        # Raw pairs are injected into assignments AFTER the LLM call via katana_lookup.
        slim_inventory = [
            {"id": ep.get("id"), "url": ep.get("url"), "method": ep.get("method"), "parameters": ep.get("parameters", [])}
            for ep in state.get("endpoint_inventory", [])
        ]
        endpoint_inventory = json.dumps(slim_inventory, indent=2)

        prompt = build_coordinator_dispatch_prompt(
            threat_model, endpoint_inventory,
        )

        result_text = await _openrouter.generate(
            prompt=prompt,
            system_prompt=COORDINATOR_DISPATCH_SYSTEM,
            node_name="coordinator",
        )

        result = json.loads(extract_json_from_response(result_text))

        active_agents = result.get("active_agents", [])
        raw_assignments = result.get("assignments", {})

        # Validate agent names
        active_agents = [a for a in active_agents if a in SPECIALIST_NAMES]

        # Build katana lookup for raw pairs
        katana_lookup = {}
        for entry in state.get("katana_output", []):
            url = entry.get("request", {}).get("endpoint", entry.get("url", ""))
            if url:
                katana_lookup[url] = {
                    "request": entry.get("request", {}).get("raw", ""),
                    "response": entry.get("response", {}).get("raw", ""),
                }

        # Process assignments: enforce endpoint cap + inject raw pairs
        processed = {}
        for agent_name in active_agents:
            assignment = raw_assignments.get(agent_name, {})
            endpoints = assignment.get("endpoints", [])

            # Enforce endpoint cap
            if len(endpoints) > MAX_ENDPOINTS_SINGLE_CALL:
                logger.info(
                    f"[coordinator] {agent_name} has {len(endpoints)} endpoints, "
                    f"capping at {MAX_ENDPOINTS_SINGLE_CALL}"
                )
                endpoints = endpoints[:MAX_ENDPOINTS_SINGLE_CALL]

            # Slice raw HTTP pairs into assignment
            raw_pairs = []
            for ep in endpoints:
                url = ep.get("url", "")
                if url in katana_lookup:
                    raw_pairs.append(katana_lookup[url])

            # Build graph slice
            graph_data = state.get("knowledge_graph", {})
            graph_bundle = AspectGraphBundle.from_dict(graph_data)
            ep_ids = [ep.get("id", "") for ep in endpoints]
            graph_slice = graph_bundle.get_slice("endpoint_map", ep_ids)

            processed[agent_name] = {
                "endpoints": endpoints,
                "raw_pairs": raw_pairs,
                "graph_slice": graph_slice,
                "hypotheses": assignment.get("hypotheses", []),
                "depth_hint": assignment.get("depth_hint", "standard"),
                "focus_areas": assignment.get("focus_areas", []),
            }

        logger.info(
            f"[coordinator] Dispatching to {len(active_agents)} agents: {active_agents}"
        )
        status.append(make_status(
            "coordinator",
            f"Dispatched to {len(active_agents)} specialists: {', '.join(active_agents)}",
        ))

        return {
            "active_agents": active_agents,
            "agent_assignments": processed,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[coordinator] Dispatch failed: {e}", exc_info=True)
        status.append(make_status("coordinator", f"Coordinator dispatch failed: {e}"))
        return {
            "active_agents": [],
            "agent_assignments": {},
            "status_log": status,
        }


async def coordinator_checkpoint_node(state: HackerState) -> dict:
    """
    Explicit state transition: specialist_findings → beliefs.
    Builds BeliefStore from merged specialist_findings list.
    From this point, downstream nodes read state["beliefs"].
    """
    findings = state.get("specialist_findings", [])
    logger.info(f"[coordinator_checkpoint] Building BeliefStore from {len(findings)} findings")

    store = BeliefStore.from_findings_list(findings)

    status = [make_status(
        "coordinator",
        f"Collected {store.count} findings from specialists",
        node="checkpoint",
    )]

    return {
        "beliefs": store,
        "status_log": status,
    }
