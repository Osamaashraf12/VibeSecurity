"""
Hunter Agent — Join Node
===========================
Explicit LangGraph join checkpoint with timeout guard.
Conditional routing: proceeds to threat_modeller when both branches complete,
or times out after ~60 iterations to prevent infinite loops.
"""

from __future__ import annotations

import logging

from backend.agents.hunter_agent.state import HackerState, make_status

logger = logging.getLogger(__name__)

# Maximum join attempts before proceeding with partial data
MAX_JOIN_ATTEMPTS = 60


async def join_node(state: HackerState) -> dict:
    """
    Increment join counter. Exists as a routing checkpoint.
    Logs branch completion status for debugging.
    """
    attempts = (state.get("join_attempts", 0) or 0) + 1
    synth_done = state.get("synthesizer_done", False)
    cvinder_done = state.get("cvinder_done", False)

    logger.debug(
        f"[join_node] call #{attempts}, "
        f"synthesizer={synth_done}, cvinder={cvinder_done}"
    )

    return {"join_attempts": 1}  # additive reducer will sum this


def should_proceed_to_threat_modeller(state: HackerState) -> str:
    """
    Conditional routing from join node.
    Proceeds when both branches are done OR after timeout.
    """
    synth_done = state.get("synthesizer_done", False)
    cvinder_done = state.get("cvinder_done", False)
    attempts = state.get("join_attempts", 0) or 0

    if synth_done and cvinder_done:
        logger.info("[join_node] Both branches complete. Proceeding to threat_modeller.")
        return "threat_modeller"

    if attempts > MAX_JOIN_ATTEMPTS:
        logger.warning(
            f"[join_node] Timeout after {attempts} attempts. "
            f"synthesizer={synth_done}, cvinder={cvinder_done}. "
            f"Proceeding with partial data."
        )
        return "threat_modeller"

    return "join"
