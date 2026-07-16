"""
Hunter Agent — State Definition
================================
Central state schema for the LangGraph pipeline. Contains:
- HackerState TypedDict with all fields and 3 reducers
- All dataclasses (Finding, PoCResult, TargetProfile, etc.)
- StatusEntry for structured logging
- Reducer functions for LangGraph parallel merging
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Annotated, Any, TypedDict


# ── Reducer Functions ─────────────────────────────────────────────────────
# These are called by LangGraph when merging state from parallel branches.

def merge_findings(left: list, right: list) -> list:
    """Merge specialist findings from parallel branches. Deduplicates by id."""
    left = left or []
    right = right or []
    seen_ids = set()
    merged = []
    for f in left:
        fid = f.get("id") if isinstance(f, dict) else getattr(f, "id", None)
        if fid and fid not in seen_ids:
            seen_ids.add(fid)
            merged.append(f)
        elif not fid:
            merged.append(f)
    for f in right:
        fid = f.get("id") if isinstance(f, dict) else getattr(f, "id", None)
        if fid and fid not in seen_ids:
            seen_ids.add(fid)
            merged.append(f)
        elif not fid:
            merged.append(f)
    return merged


def increment(left: int, right: int) -> int:
    """Additive reducer for join_attempts counter."""
    return (left or 0) + (right or 0)


def append_logs(left: list, right: list) -> list:
    """Append reducer for status_log — parallel nodes don't overwrite each other."""
    return (left or []) + (right or [])


# ── Status Entry ──────────────────────────────────────────────────────────

class StatusEntry(TypedDict):
    """Structured status log entry for the frontend chat feed."""
    phase: str          # katana|synthesizer|cvinder|threat_model|coordinator|specialist|...
    node: str | None    # specific node name or null for single-node phases
    message: str        # human-readable text rendered in chat
    timestamp: str      # ISO 8601


def make_status(phase: str, message: str, node: str = None) -> StatusEntry:
    """Helper to create a StatusEntry with auto-timestamp."""
    return StatusEntry(
        phase=phase,
        node=node,
        message=message,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


# ── Dataclasses ───────────────────────────────────────────────────────────

@dataclass
class TargetProfile:
    """High-level profile of the scan target."""
    domain: str = ""
    technologies: list[str] = field(default_factory=list)
    framework: str = ""
    auth_mechanisms: list[str] = field(default_factory=list)
    api_style: str = ""  # REST, GraphQL, SOAP, etc.
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TargetProfile:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Endpoint:
    """Single endpoint discovered by Katana."""
    id: str = ""
    url: str = ""
    method: str = "GET"
    parameters: list[str] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    auth_required: bool = False
    cluster: str = ""  # auth, api, file, admin, other
    raw_request: str = ""
    raw_response: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Endpoint:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AttackerModel:
    """Formal attacker model — defines scope and constraints."""
    role: str = "authenticated"  # unauthenticated, authenticated, admin
    attack_vector: str = "network"
    trust_boundaries: list[str] = field(default_factory=list)
    scope: str = ""
    goal: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AttackerModel:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ThreatModel:
    """Threat model with prioritized hypotheses."""
    hypotheses: list[dict] = field(default_factory=list)  # [{endpoint_id, vuln_class, priority, rationale}]
    cve_seeded: bool = False
    top_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ThreatModel:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Finding:
    """Single vulnerability finding from a specialist agent."""
    id: str = field(default_factory=lambda: f"finding-{uuid.uuid4().hex[:8]}")
    agent: str = ""
    title: str = ""
    severity: str = "Medium"
    cvss: float = 5.0
    confidence: float = 0.5
    category: str = ""
    location: str = ""
    description: str = ""
    remediation: str = ""
    poc_steps: list[str] = field(default_factory=list)
    poc_request: str = ""
    attacker_model_satisfied: bool = False
    evidence: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Finding:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PoCResult:
    """Proof-of-concept result from the PoC Generator."""
    finding_id: str = ""
    viable: bool = False
    http_request: str = ""
    expected_response: str = ""
    prerequisites_met: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PoCResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AttackChain:
    """Multi-step attack chain identified by the Chainer."""
    id: str = field(default_factory=lambda: f"chain-{uuid.uuid4().hex[:8]}")
    name: str = ""
    severity: str = "High"
    finding_ids: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)  # [{step, action, relies_on_finding, payload}]
    impact_narrative: str = ""
    prerequisites: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AttackChain:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TokenBudget:
    """Tracks token usage across pipeline phases."""
    total_limit: int = 500000
    scaffolding_spent: int = 0
    specialist_spent: int = 0
    verification_spent: int = 0

    @property
    def remaining(self) -> int:
        return self.total_limit - self.scaffolding_spent - self.specialist_spent - self.verification_spent

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TokenBudget:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── HackerState — LangGraph State Schema ─────────────────────────────────

class HackerState(TypedDict):
    """
    Central state for the Hunter Agent LangGraph pipeline.
    Fields with Annotated reducers support parallel branch merging.
    """

    # ── Input ──
    target: str
    katana_output: list[dict]
    cve_history: list[dict]

    # ── Join coordination ──
    synthesizer_done: bool
    cvinder_done: bool
    join_attempts: Annotated[int, increment]

    # ── Agent 0 (Synthesizer) outputs ──
    target_profile: dict | None
    endpoint_inventory: list[dict]
    endpoint_clusters: dict
    knowledge_graph: dict  # AspectGraphBundle.to_dict()

    # ── Threat model outputs ──
    threat_model: dict | None
    attacker_model: dict | None
    attack_surface_map: dict | None

    # ── Coordinator ──
    active_agents: list[str]
    agent_assignments: dict[str, dict]
    token_budget: dict | None
    coordinator_log: list[str]

    # ── Specialist fan-out (injected per-agent by Send()) ──
    my_assignment: dict | None
    my_agent_name: str | None

    # ── Specialist outputs (merged via reducer) ──
    specialist_findings: Annotated[list[dict], merge_findings]

    # ── Coordinator checkpoint builds this ──
    beliefs: Any  # BeliefStore instance — see belief_store.py

    # ── Post-processing ──
    chains: list[dict]
    poc_results: list[dict]
    validated_findings: list[dict]
    rejected_findings: list[dict]
    revisor_notes: str | None

    # ── Output ──
    report: dict | None
    iteration_count: int
    status_log: Annotated[list[dict], append_logs]


def build_initial_state(target_url: str) -> dict:
    """
    Creates a fully initialized state dict for graph.ainvoke().
    All reducer fields MUST be initialized here to avoid TypeError.
    """
    return {
        "target": target_url,
        "katana_output": [],
        "cve_history": [],
        "synthesizer_done": False,
        "cvinder_done": False,
        "join_attempts": 0,
        "target_profile": None,
        "endpoint_inventory": [],
        "endpoint_clusters": {},
        "knowledge_graph": {},
        "threat_model": None,
        "attacker_model": None,
        "attack_surface_map": None,
        "active_agents": [],
        "agent_assignments": {},
        "token_budget": None,
        "coordinator_log": [],
        "my_assignment": None,
        "my_agent_name": None,
        "specialist_findings": [],    # MUST be [] — reducer expects list
        "beliefs": None,
        "chains": [],
        "poc_results": [],
        "validated_findings": [],
        "rejected_findings": [],
        "revisor_notes": None,
        "report": None,
        "iteration_count": 0,
        "status_log": [],             # MUST be [] — reducer expects list
    }
