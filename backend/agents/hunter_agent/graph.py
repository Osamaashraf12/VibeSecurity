"""
Hunter Agent — LangGraph State Graph
======================================
Wires all nodes together with:
- Parallel fork (Synthesizer || CVINDER) after Katana
- Explicit join node with timeout guard
- Specialist fan-out via Send()
- Annotated reducers for parallel state merging
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from backend.agents.hunter_agent.state import HackerState
from backend.core.llm.model_config import SPECIALIST_NAMES

# ── Node imports ──
from backend.agents.hunter_agent.nodes.katana_node import katana_node
from backend.agents.hunter_agent.nodes.synthesizer import synthesizer_node
from backend.agents.hunter_agent.nodes.cvinder_node import cvinder_node
from backend.agents.hunter_agent.nodes.join_node import (
    join_node, should_proceed_to_threat_modeller,
)
from backend.agents.hunter_agent.nodes.threat_modeller import threat_modeller_node
from backend.agents.hunter_agent.nodes.coordinator import (
    coordinator_dispatch_node, coordinator_checkpoint_node,
)
from backend.agents.hunter_agent.nodes.chainer import chainer_node
from backend.agents.hunter_agent.nodes.poc_generator import poc_generator_node
from backend.agents.hunter_agent.nodes.revisor import revisor_node
from backend.agents.hunter_agent.nodes.report_agent import report_agent_node
from backend.agents.hunter_agent.nodes.specialists import SPECIALIST_NODES

logger = logging.getLogger(__name__)


def dispatch_specialists(state: HackerState) -> list[Send]:
    """
    Fan-out: sends each specialist ONLY what it needs — not the full state.
    Each Send() targets a specialist node with minimal context.
    """
    assignments = state.get("agent_assignments", {})
    active_agents = state.get("active_agents", [])
    sends = []

    for agent_name, assignment in assignments.items():
        if agent_name not in active_agents:
            continue
        if agent_name not in SPECIALIST_NAMES:
            continue

        # Minimal context per specialist
        sends.append(Send(agent_name, {
            "my_assignment": assignment,
            "my_agent_name": agent_name,
            "attacker_model": state.get("attacker_model"),
            "target_profile": state.get("target_profile"),
            "target": state.get("target", ""),
        }))

    if not sends:
        logger.warning("[graph] No specialists to dispatch — sending empty to coordinator_checkpoint")
        # Must send at least one thing or graph hangs
        # Send directly to checkpoint with empty findings
        return [Send("coordinator_checkpoint", {})]

    logger.info(f"[graph] Dispatching to {len(sends)} specialists: {[s.node for s in sends]}")
    return sends


def build_graph() -> Any:
    """Build and compile the Hunter Agent LangGraph."""
    logger.info("[graph] Building Hunter Agent state graph")

    graph = StateGraph(HackerState)

    # ── Node registration ──
    graph.add_node("katana", katana_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("cvinder", cvinder_node)
    graph.add_node("join", join_node)
    graph.add_node("threat_modeller", threat_modeller_node)
    graph.add_node("coordinator_dispatch", coordinator_dispatch_node)
    graph.add_node("coordinator_checkpoint", coordinator_checkpoint_node)
    graph.add_node("chainer", chainer_node)
    graph.add_node("poc_generator", poc_generator_node)
    graph.add_node("revisor", revisor_node)
    graph.add_node("report_agent", report_agent_node)

    # Specialists registered dynamically
    for name in SPECIALIST_NAMES:
        if name in SPECIALIST_NODES:
            graph.add_node(name, SPECIALIST_NODES[name])

    # ── Parallel fork after katana ──
    graph.add_edge(START, "katana")
    graph.add_edge("katana", "synthesizer")
    graph.add_edge("katana", "cvinder")

    # ── Explicit join with timeout guard ──
    graph.add_edge("synthesizer", "join")
    graph.add_edge("cvinder", "join")
    graph.add_conditional_edges("join", should_proceed_to_threat_modeller, {
        "threat_modeller": "threat_modeller",
        "join": "join",
    })

    # ── Sequential after join ──
    graph.add_edge("threat_modeller", "coordinator_dispatch")

    # ── Specialist fan-out via Send() ──
    graph.add_conditional_edges("coordinator_dispatch", dispatch_specialists)

    # ── Specialist join → checkpoint ──
    for name in SPECIALIST_NAMES:
        graph.add_edge(name, "coordinator_checkpoint")

    # ── Sequential post-processing ──
    graph.add_edge("coordinator_checkpoint", "chainer")
    graph.add_edge("chainer", "poc_generator")
    graph.add_edge("poc_generator", "revisor")
    graph.add_edge("revisor", "report_agent")
    graph.add_edge("report_agent", END)

    compiled = graph.compile()
    logger.info("[graph] Hunter Agent graph compiled successfully")
    return compiled
