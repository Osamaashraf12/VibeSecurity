"""
Hunter Agent — Specialist Agents Package
==========================================
Generic specialist runner used by all 6 specialist agents.
Each agent uses a different model but the same execution pattern.
"""

from __future__ import annotations

import json
import logging

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.core.llm.model_config import needs_reasoning
from backend.agents.hunter_agent.prompts.specialist_base_prompt import (
    build_specialist_system_prompt, build_specialist_user_prompt,
)

logger = logging.getLogger(__name__)

_openrouter = OpenRouterAgentClient()


async def run_specialist(state: HackerState) -> dict:
    """
    Generic specialist execution. Called by all 6 specialist nodes.
    Uses my_agent_name and my_assignment from Send()-injected state.
    Returns specialist_findings (merged via reducer at join).
    """
    agent_name = state.get("my_agent_name", "unknown")
    assignment = state.get("my_assignment", {})

    logger.info(f"[{agent_name}] Starting specialist analysis")
    status = [make_status(
        "specialist",
        f"{agent_name} specialist analyzing {len(assignment.get('endpoints', []))} endpoints...",
        node=agent_name,
    )]

    try:
        # Build prompts
        system_prompt = build_specialist_system_prompt(agent_name)
        user_prompt = build_specialist_user_prompt(
            agent_name=agent_name,
            assignment=assignment,
            attacker_model=state.get("attacker_model"),
            target_profile=state.get("target_profile"),
        )

        # Check if this model needs reasoning mode
        from backend.core.llm.model_config import OPENROUTER_MODELS
        model = OPENROUTER_MODELS.get(agent_name, "")
        use_thinking = needs_reasoning(model)

        # Single LLM call
        result_text = await _openrouter.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            node_name=agent_name,
            thinking=use_thinking,
        )

        # Parse findings
        try:
            result = json.loads(extract_json_from_response(result_text))
            findings = result.get("findings", [])

            # Ensure each finding has the agent name
            for f in findings:
                if not f.get("agent"):
                    f["agent"] = agent_name
                if not f.get("category"):
                    f["category"] = agent_name

        except json.JSONDecodeError:
            logger.warning(f"[{agent_name}] Failed to parse JSON response")
            findings = []

        logger.info(f"[{agent_name}] Found {len(findings)} findings")
        status.append(make_status(
            "specialist",
            f"{agent_name}: {len(findings)} findings",
            node=agent_name,
        ))

        return {
            "specialist_findings": findings,
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[{agent_name}] Failed: {e}", exc_info=True)
        status.append(make_status("specialist", f"{agent_name} failed: {e}", node=agent_name))
        return {
            "specialist_findings": [],
            "status_log": status,
        }


# Individual specialist node functions (all use run_specialist)
async def auth_agent(state: HackerState) -> dict:
    return await run_specialist(state)

async def injection_agent(state: HackerState) -> dict:
    return await run_specialist(state)

async def access_control_agent(state: HackerState) -> dict:
    return await run_specialist(state)

async def business_logic_agent(state: HackerState) -> dict:
    return await run_specialist(state)

async def client_side_agent(state: HackerState) -> dict:
    return await run_specialist(state)

async def infrastructure_agent(state: HackerState) -> dict:
    return await run_specialist(state)


# Registry for dynamic graph registration
SPECIALIST_NODES = {
    "auth": auth_agent,
    "injection": injection_agent,
    "access_control": access_control_agent,
    "business_logic": business_logic_agent,
    "client_side": client_side_agent,
    "infrastructure": infrastructure_agent,
}
