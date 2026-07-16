"""
Hunter Agent — Belief Store
============================
Thread-safe-by-design store for vulnerability findings.
No locking — writes only occur at node boundaries where
LangGraph serializes state updates.

Constructed from the merged specialist_findings list at the
Coordinator checkpoint. Downstream nodes (Chainer, PoC Generator,
Revisor) read from this store.

# TODO: If a LangGraph checkpointer is ever added for crash recovery,
# BeliefStore needs a __reduce__ method or JSON serialization path.
# Currently lives only in memory — no persistence needed.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.agents.hunter_agent.state import Finding


class BeliefStore:
    """
    Pure dict-based vulnerability findings store.
    No locking — LangGraph handles state serialization at node boundaries.
    """

    def __init__(self):
        self._findings: dict[str, dict] = {}

    def add(self, finding: dict | object) -> None:
        """Add a finding. Accepts dict or Finding dataclass."""
        if hasattr(finding, "to_dict"):
            data = finding.to_dict()
        elif isinstance(finding, dict):
            data = finding
        else:
            raise TypeError(f"Expected dict or Finding, got {type(finding)}")

        fid = data.get("id", "")
        if not fid:
            import uuid
            fid = f"finding-{uuid.uuid4().hex[:8]}"
            data["id"] = fid

        self._findings[fid] = data

    def update(self, finding_id: str, **kwargs) -> None:
        """Update fields on an existing finding."""
        if finding_id in self._findings:
            self._findings[finding_id].update(kwargs)

    def get(self, finding_id: str) -> dict | None:
        """Get a finding by ID."""
        return self._findings.get(finding_id)

    def get_by_agent(self, agent: str) -> list[dict]:
        """Get all findings from a specific agent."""
        return [f for f in self._findings.values() if f.get("agent") == agent]

    def get_above_confidence(self, threshold: float) -> list[dict]:
        """Get findings above a confidence threshold."""
        return [
            f for f in self._findings.values()
            if f.get("confidence", 0) >= threshold
        ]

    def get_by_severity(self, severity: str) -> list[dict]:
        """Get findings of a specific severity level."""
        return [
            f for f in self._findings.values()
            if f.get("severity", "").lower() == severity.lower()
        ]

    def get_viable_for_poc(self) -> list[dict]:
        """Get findings with confidence >= 0.5, suitable for PoC generation."""
        return self.get_above_confidence(0.5)

    def get_for_rejection(self) -> list[dict]:
        """Get findings with non-viable PoC AND confidence < 0.7 — candidates for rejection."""
        results = []
        for f in self._findings.values():
            confidence = f.get("confidence", 0)
            poc_viable = f.get("poc_viable", None)
            if poc_viable is False and confidence < 0.7:
                results.append(f)
        return results

    @property
    def count(self) -> int:
        return len(self._findings)

    def export(self) -> list[dict]:
        """Export all findings as a list of dicts."""
        return list(self._findings.values())

    def to_dict(self) -> dict:
        """Serialize for state storage."""
        return {"findings": self.export()}

    @classmethod
    def from_dict(cls, data: dict) -> BeliefStore:
        """Reconstruct from serialized dict."""
        store = cls()
        if data and "findings" in data:
            for f in data["findings"]:
                store.add(f)
        return store

    @classmethod
    def from_findings_list(cls, findings: list[dict]) -> BeliefStore:
        """Construct from merged specialist_findings list."""
        store = cls()
        for f in (findings or []):
            store.add(f)
        return store

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        return f"BeliefStore({self.count} findings)"
