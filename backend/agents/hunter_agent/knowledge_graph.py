"""
Hunter Agent — Knowledge Graph (AspectGraphBundle)
====================================================
Single class with 3 dict fields:
  - auth_flow:    auth mechanisms, session lifecycle, token handling
  - data_flow:    taint sources -> processing -> sinks
  - endpoint_map: all endpoints + relationships + specialist annotations (living)

The endpoint_map is a living document — specialists annotate it during analysis.
The Coordinator uses get_slice() to extract focused subgraphs for each specialist.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AspectGraphBundle:
    """
    Unified knowledge graph for the target application.
    Built by the Synthesizer (Agent 0), annotated by specialists.
    """

    def __init__(self):
        self.auth_flow: dict[str, Any] = {}
        self.data_flow: dict[str, Any] = {}
        self.endpoint_map: dict[str, Any] = {}

    def build_auth_flow(self, endpoint_inventory: list[dict]) -> dict:
        """
        Build AuthFlow graph from endpoint inventory.
        Groups auth-related endpoints: login, logout, reset, OAuth, tokens, sessions.
        """
        auth_endpoints = []
        for ep in endpoint_inventory:
            url = ep.get("url", "").lower()
            params = [p.lower() for p in ep.get("parameters", [])]
            is_auth = any(
                kw in url for kw in
                ["login", "logout", "auth", "oauth", "token", "session",
                 "register", "signup", "password", "reset", "mfa", "2fa",
                 "verify", "refresh", "revoke"]
            ) or any(
                kw in p for p in params for kw in
                ["password", "token", "session", "auth", "credential"]
            )
            if is_auth:
                auth_endpoints.append(ep)

        self.auth_flow = {
            "endpoints": auth_endpoints,
            "mechanisms": [],    # populated by Synthesizer LLM call
            "session_lifecycle": {},
            "token_handling": {},
        }
        return self.auth_flow

    def build_data_flow(self, endpoint_inventory: list[dict]) -> dict:
        """
        Build DataFlow graph from endpoint inventory.
        Maps taint sources (user input) -> processing -> sinks (output).
        """
        sources = []
        sinks = []
        for ep in endpoint_inventory:
            if ep.get("parameters") or ep.get("method", "GET").upper() in ("POST", "PUT", "PATCH"):
                sources.append({
                    "endpoint_id": ep.get("id", ""),
                    "url": ep.get("url", ""),
                    "input_params": ep.get("parameters", []),
                })
            url = ep.get("url", "").lower()
            if any(kw in url for kw in ["search", "export", "download", "render", "display", "view"]):
                sinks.append({
                    "endpoint_id": ep.get("id", ""),
                    "url": ep.get("url", ""),
                    "reflection_risk": True,
                })

        self.data_flow = {
            "sources": sources,
            "sinks": sinks,
            "processing": [],    # populated by Synthesizer
        }
        return self.data_flow

    def build_endpoint_map(self, endpoint_inventory: list[dict]) -> dict:
        """
        Build EndpointMap from full inventory.
        This is the living document annotated by specialists.
        """
        ep_map = {}
        for ep in endpoint_inventory:
            ep_id = ep.get("id", ep.get("url", ""))
            ep_map[ep_id] = {
                **ep,
                "annotations": [],       # specialists write here
                "findings_count": 0,
                "risk_score": 0.0,
            }
        self.endpoint_map = ep_map
        return self.endpoint_map

    def annotate(self, endpoint_id: str, annotation: dict) -> None:
        """
        Specialist annotation API. Adds analysis notes to an endpoint.
        Called by specialists after completing their analysis.
        """
        if endpoint_id in self.endpoint_map:
            self.endpoint_map[endpoint_id]["annotations"].append(annotation)
            self.endpoint_map[endpoint_id]["findings_count"] += annotation.get("findings_count", 0)
            if annotation.get("risk_score", 0) > self.endpoint_map[endpoint_id]["risk_score"]:
                self.endpoint_map[endpoint_id]["risk_score"] = annotation["risk_score"]
        else:
            logger.warning(f"[KnowledgeGraph] annotate() called for unknown endpoint: {endpoint_id}")

    def get_slice(self, graph_name: str, endpoint_ids: list[str]) -> dict:
        """
        Extract a focused slice of a specific aspect graph for a specialist.
        Only returns data relevant to the given endpoint IDs.
        """
        if graph_name == "auth_flow":
            sliced_endpoints = [
                ep for ep in self.auth_flow.get("endpoints", [])
                if ep.get("id", ep.get("url", "")) in endpoint_ids
            ]
            return {
                "endpoints": sliced_endpoints,
                "mechanisms": self.auth_flow.get("mechanisms", []),
                "session_lifecycle": self.auth_flow.get("session_lifecycle", {}),
                "token_handling": self.auth_flow.get("token_handling", {}),
            }
        elif graph_name == "data_flow":
            sliced_sources = [
                s for s in self.data_flow.get("sources", [])
                if s.get("endpoint_id", "") in endpoint_ids
            ]
            sliced_sinks = [
                s for s in self.data_flow.get("sinks", [])
                if s.get("endpoint_id", "") in endpoint_ids
            ]
            return {
                "sources": sliced_sources,
                "sinks": sliced_sinks,
                "processing": self.data_flow.get("processing", []),
            }
        elif graph_name == "endpoint_map":
            return {
                eid: self.endpoint_map[eid]
                for eid in endpoint_ids
                if eid in self.endpoint_map
            }
        else:
            logger.warning(f"[KnowledgeGraph] Unknown graph name: {graph_name}")
            return {}

    def to_dict(self) -> dict:
        """Serialize for state storage."""
        return {
            "auth_flow": self.auth_flow,
            "data_flow": self.data_flow,
            "endpoint_map": self.endpoint_map,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AspectGraphBundle:
        """Reconstruct from serialized dict."""
        bundle = cls()
        if data:
            bundle.auth_flow = data.get("auth_flow", {})
            bundle.data_flow = data.get("data_flow", {})
            bundle.endpoint_map = data.get("endpoint_map", {})
        return bundle

    def __repr__(self) -> str:
        return (
            f"AspectGraphBundle("
            f"auth_flow={len(self.auth_flow.get('endpoints', []))} eps, "
            f"data_flow={len(self.data_flow.get('sources', []))} sources, "
            f"endpoint_map={len(self.endpoint_map)} eps)"
        )
