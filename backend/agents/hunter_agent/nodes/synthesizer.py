"""
Hunter Agent — Synthesizer Node (Agent 0)
===========================================
Two-step design:
  Step 1: A single OpenRouter call semantically clusters all endpoints.
           The LLM understands the app's domain and groups logically,
           regardless of URL naming conventions.
  Step 2: Each cluster is analyzed individually for deep synthesis.

Produces target_profile, knowledge_graph, and endpoint_clusters.
Sets synthesizer_done=True on completion (including failure).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from urllib.parse import urlparse

from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.knowledge_graph import AspectGraphBundle
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import extract_json_from_response
from backend.agents.hunter_agent.prompts.synthesizer_prompt import (
    SYNTHESIZER_SYSTEM, build_synthesizer_prompt,
)

logger = logging.getLogger(__name__)

_or_client = OpenRouterAgentClient()

# ── Static asset extensions — always filtered, never analyzed ─────────────
STATIC_EXTENSIONS = {
    ".css", ".ico", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".woff", ".woff2", ".ttf", ".eot", ".map",
}

# ── Clustering prompt (Step 1) ──────────────────────────────────────────

CLUSTERING_SYSTEM = """You are a security-focused endpoint classifier.
You receive a list of HTTP endpoints from a web application.
Your job is to group them into functional clusters based on what they DO,
not based on their URL naming convention.

Think about it from a pentester's perspective: which endpoints belong
together because they share a functional context?

Common cluster types (use these or create your own labels):
- authentication (login, signup, token refresh, password reset — regardless of URL naming)
- user_management (profiles, settings, preferences)
- api_data (CRUD operations on resources)
- admin_panel (administrative operations, config, management)
- file_operations (upload, download, media serving)
- payment_checkout (transactions, cart, billing)
- search_navigation (search, filters, pagination)
- static_content (documentation, FAQ, about pages)
- other (anything that doesn't fit)

Output EXACTLY this JSON (no markdown fences):

{
  "clusters": {
    "cluster_label": ["ep-id-1", "ep-id-2"],
    "another_cluster": ["ep-id-3"]
  },
  "reasoning": "Brief explanation of why you grouped them this way"
}

Rules:
1. Every endpoint ID must appear in exactly one cluster.
2. Don't create clusters with only 1 endpoint — merge them into the closest group.
3. Limit to 8 clusters maximum. Merge smaller groups.
4. Cluster labels should be lowercase_with_underscores.
5. Output ONLY valid JSON."""


def _build_clustering_prompt(endpoints: list[dict]) -> str:
    """Build a lightweight endpoint list for the clustering call."""
    simplified = []
    for ep in endpoints:
        simplified.append({
            "id": ep.get("id", ""),
            "url": ep.get("url", ""),
            "method": ep.get("method", "GET"),
            "params": ep.get("parameters", [])[:5],  # truncate for token efficiency
        })
    return f"Group these {len(simplified)} endpoints into functional clusters:\n\n{json.dumps(simplified, indent=1)}"


def _filter_static(endpoints: list[dict]) -> list[dict]:
    """Remove static assets before any processing."""
    filtered = []
    for ep in endpoints:
        url = ep.get("url", "")
        path = urlparse(url).path
        ext_match = re.search(r'\.\w{2,5}$', path)
        if ext_match and ext_match.group().lower() in STATIC_EXTENSIONS:
            continue
        filtered.append(ep)
    return filtered


def _fallback_cluster(endpoints: list[dict]) -> dict[str, list[dict]]:
    """
    Structural fallback: group by first 1-2 URL path segments.
    Used only if the LLM clustering call fails.
    """
    prefix_groups: dict[str, list[dict]] = {}

    for ep in endpoints:
        path = urlparse(ep.get("url", "")).path.strip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 2:
            key = f"{segments[0]}/{segments[1]}"
        elif len(segments) == 1:
            key = segments[0]
        else:
            key = "root"
        prefix_groups.setdefault(key, []).append(ep)

    # Merge tiny groups (< 3 endpoints) into "misc"
    final: dict[str, list[dict]] = {}
    misc: list[dict] = []
    for key, eps in prefix_groups.items():
        if len(eps) >= 3:
            final[key] = eps
        else:
            misc.extend(eps)
    if misc:
        final["misc"] = misc

    return {k: v for k, v in final.items() if v}


async def _llm_cluster(endpoints: list[dict]) -> dict[str, list[dict]]:
    """
    Step 1: Ask OpenRouter to semantically cluster endpoints.
    Returns {cluster_label: [endpoint_dicts]}.
    Falls back to structural grouping on failure.
    """
    # Build ID lookup
    ep_by_id: dict[str, dict] = {}
    for ep in endpoints:
        ep_by_id[ep.get("id", "")] = ep

    prompt = _build_clustering_prompt(endpoints)

    try:
        result_text = await _or_client.generate(
            prompt=prompt,
            system_prompt=CLUSTERING_SYSTEM,
            node_name="synthesizer",
        )

        result = json.loads(extract_json_from_response(result_text))
        raw_clusters = result.get("clusters", {})
        reasoning = result.get("reasoning", "")

        if reasoning:
            logger.info(f"[synthesizer] LLM clustering reasoning: {reasoning}")

        # Map IDs back to full endpoint dicts
        clusters: dict[str, list[dict]] = {}
        claimed_ids: set[str] = set()

        for label, ep_ids in raw_clusters.items():
            cluster_eps = []
            for eid in ep_ids:
                if eid in ep_by_id:
                    cluster_eps.append(ep_by_id[eid])
                    claimed_ids.add(eid)
            if cluster_eps:
                clusters[label] = cluster_eps

        # Catch any endpoints the LLM missed
        unclaimed = [ep for ep in endpoints if ep.get("id", "") not in claimed_ids]
        if unclaimed:
            logger.warning(f"[synthesizer] LLM missed {len(unclaimed)} endpoints, adding to 'other'")
            clusters.setdefault("other", []).extend(unclaimed)

        if clusters:
            logger.info(
                f"[synthesizer] LLM produced {len(clusters)} clusters: "
                f"{', '.join(f'{k}({len(v)})' for k, v in clusters.items())}"
            )
            return clusters

    except Exception as e:
        logger.warning(f"[synthesizer] LLM clustering failed: {e}. Falling back to structural grouping.")

    # Fallback
    return _fallback_cluster(endpoints)


async def synthesizer_node(state: HackerState) -> dict:
    """
    Analyze endpoints in clusters via Gemini. RPM-paced.
    Always sets synthesizer_done=True, even on failure.
    """
    endpoints = state.get("endpoint_inventory", [])
    status = [make_status("synthesizer", f"Analyzing {len(endpoints)} endpoints...")]

    try:
        if not endpoints:
            logger.warning("[synthesizer] No endpoints to analyze")
            status.append(make_status("synthesizer", "No endpoints found -- skipping synthesis"))
            return {
                "synthesizer_done": True,
                "target_profile": {},
                "endpoint_clusters": {},
                "knowledge_graph": {},
                "status_log": status,
            }

        # Filter static assets
        endpoints = _filter_static(endpoints)
        logger.info(f"[synthesizer] {len(endpoints)} endpoints after filtering static assets")

        # Step 1: LLM-based semantic clustering
        status.append(make_status("synthesizer", "Classifying endpoints into functional clusters..."))
        clusters = await _llm_cluster(endpoints)
        logger.info(f"[synthesizer] {len(clusters)} clusters: {list(clusters.keys())}")
        status.append(make_status(
            "synthesizer",
            f"{len(clusters)} clusters identified: {', '.join(clusters.keys())}",
        ))

        # Step 2: Analyze each cluster individually (RPM-paced)
        merged_profile = {}
        all_analyzed_endpoints = []
        graph_bundle = AspectGraphBundle()

        for cluster_name, cluster_eps in clusters.items():
            logger.info(f"[synthesizer] Analyzing cluster '{cluster_name}' ({len(cluster_eps)} endpoints)")
            status.append(make_status(
                "synthesizer",
                f"Analyzing {cluster_name} cluster ({len(cluster_eps)} endpoints)...",
                node="synthesizer",
            ))

            # Build prompt for this cluster
            eps_json = json.dumps([{
                "id": ep.get("id", ""),
                "url": ep.get("url", ""),
                "method": ep.get("method", "GET"),
                "parameters": ep.get("parameters", []),
            } for ep in cluster_eps], indent=2)

            prompt = build_synthesizer_prompt(cluster_name, eps_json)

            try:
                result_text = await _or_client.generate(
                    prompt=prompt,
                    system_prompt=SYNTHESIZER_SYSTEM,
                    node_name="synthesizer",
                )

                try:
                    result = json.loads(extract_json_from_response(result_text))
                except json.JSONDecodeError:
                    logger.warning(f"[synthesizer] Failed to parse JSON for cluster '{cluster_name}'")
                    result = {}

                # Merge target profile
                if "target_profile" in result:
                    for key, val in result["target_profile"].items():
                        if isinstance(val, list):
                            existing = merged_profile.get(key, [])
                            merged_profile[key] = list(set(existing + val))
                        elif val and not merged_profile.get(key):
                            merged_profile[key] = val

                # Collect analyzed endpoints
                if "endpoints" in result:
                    all_analyzed_endpoints.extend(result["endpoints"])

            except Exception as e:
                logger.error(f"[synthesizer] Cluster '{cluster_name}' failed: {e}")
                status.append(make_status("synthesizer", f"Cluster {cluster_name} analysis failed: {e}"))

        # Build knowledge graph from all analyzed endpoints
        graph_bundle.build_auth_flow(all_analyzed_endpoints or endpoints)
        graph_bundle.build_data_flow(all_analyzed_endpoints or endpoints)
        graph_bundle.build_endpoint_map(all_analyzed_endpoints or endpoints)

        status.append(make_status(
            "synthesizer",
            f"Synthesis complete: {len(all_analyzed_endpoints)} endpoints analyzed, "
            f"profile: {merged_profile.get('framework', 'unknown')} / {merged_profile.get('api_style', 'unknown')}",
        ))

        return {
            "synthesizer_done": True,
            "target_profile": merged_profile,
            "endpoint_clusters": {k: [ep.get("id", "") for ep in v] for k, v in clusters.items()},
            "knowledge_graph": graph_bundle.to_dict(),
            "status_log": status,
        }

    except Exception as e:
        logger.error(f"[synthesizer] Fatal error: {e}", exc_info=True)
        status.append(make_status("synthesizer", f"Synthesizer failed: {e}"))
        # done=True even on failure so join doesn't hang
        return {
            "synthesizer_done": True,
            "target_profile": {},
            "endpoint_clusters": {},
            "knowledge_graph": {},
            "status_log": status,
        }
