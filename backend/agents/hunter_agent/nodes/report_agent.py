"""
Hunter Agent — Report Agent Node
===================================
Final node: produces hunter_report.json.
Validates JSON, retries on failure, writes minimal error report as last resort.
"""

from __future__ import annotations

import json
import uuid
import time
import logging

from backend.core.paths import SCAN_RESULTS_DIR
from backend.agents.hunter_agent.state import HackerState, make_status
from backend.agents.hunter_agent.utils.openrouter_wrapper import OpenRouterAgentClient
from backend.agents.hunter_agent.utils.http_utils import (
    extract_json_from_response, parse_and_validate_report,
)
from backend.agents.hunter_agent.prompts.report_prompt import (
    REPORT_SYSTEM, build_report_prompt,
)

logger = logging.getLogger(__name__)

_openrouter = OpenRouterAgentClient()

SCAN_RESULTS = SCAN_RESULTS_DIR


async def report_agent_node(state: HackerState) -> dict:
    """Generate hunter_report.json. Validates, retries, and provides fallback."""
    target = state.get("target", "unknown")
    scan_id = f"hunter_scan_{uuid.uuid4().hex[:12]}"
    start_time = state.get("_start_time", time.time())
    duration = int(time.time() - start_time) if start_time else 0

    logger.info(f"[report_agent] Generating report for {target}")
    status = [make_status("report", "Generating final security report...")]

    validated = state.get("validated_findings", [])
    rejected = state.get("rejected_findings", [])
    chains = state.get("chains", [])
    poc_results = state.get("poc_results", [])
    attacker_model = state.get("attacker_model", {})
    revisor_notes = state.get("revisor_notes", "")

    prompt = build_report_prompt(
        validated_findings=json.dumps(validated, indent=2),
        rejected_findings=json.dumps(rejected, indent=2),
        chains=json.dumps(chains, indent=2),
        poc_results=json.dumps(poc_results, indent=2),
        attacker_model=json.dumps(attacker_model, indent=2),
        revisor_notes=revisor_notes,
        target=target,
        scan_id=scan_id,
        duration_seconds=duration,
    )

    report = None

    # Attempt 1
    try:
        result_text = await _openrouter.generate(
            prompt=prompt,
            system_prompt=REPORT_SYSTEM,
            node_name="report_agent",
        )
        report = parse_and_validate_report(result_text)
        logger.info("[report_agent] Report generated successfully on first attempt")

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[report_agent] First attempt failed validation: {e}")
        status.append(make_status("report", "Report validation failed, retrying with correction prompt..."))

        # Attempt 2: correction prompt
        try:
            correction_prompt = (
                "Your previous response was not valid JSON. "
                "Return ONLY raw JSON with no markdown fences, no commentary. "
                f"Schema: {{meta: {{scan_id, target, timestamp}}, "
                f"summary: {{risk_score, executive_text, counts}}, "
                f"findings: [...], chains: [...], ruled_out: [...]}}\n\n"
                f"Original request:\n{prompt}"
            )

            result_text = await _openrouter.generate(
                prompt=correction_prompt,
                system_prompt=REPORT_SYSTEM,
                node_name="report_agent",
            )
            report = parse_and_validate_report(result_text)
            logger.info("[report_agent] Report generated on retry")

        except Exception as e2:
            logger.error(f"[report_agent] Retry also failed: {e2}")

    except Exception as e:
        logger.error(f"[report_agent] Report generation failed: {e}", exc_info=True)

    # Fallback: minimal error report
    if report is None:
        logger.warning("[report_agent] Using minimal fallback report")
        report = _build_fallback_report(target, scan_id, duration, validated, rejected, chains)
        status.append(make_status("report", "Report generation failed. Using fallback report."))

    # Write report files
    _write_report(report, target)

    status.append(make_status(
        "report",
        f"Report complete: {len(report.get('findings', []))} findings, "
        f"risk score {report.get('summary', {}).get('risk_score', 'N/A')}",
    ))

    return {
        "report": report,
        "status_log": status,
    }


def _build_fallback_report(
    target: str, scan_id: str, duration: int,
    validated: list, rejected: list, chains: list,
) -> dict:
    """Build minimal report when LLM fails to produce valid JSON."""
    # Count severities from validated findings
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in validated:
        sev = f.get("severity", "medium").lower()
        if sev in counts:
            counts[sev] += 1

    return {
        "meta": {
            "scan_id": scan_id,
            "target": target,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_seconds": duration,
            "scan_type": "hunter_agent",
        },
        "summary": {
            "risk_score": 0,
            "executive_text": (
                "Report generation failed. Raw findings are available in the "
                "exploitation output directory."
            ),
            "counts": counts,
        },
        "findings": validated,
        "chains": chains,
        "ruled_out": [{"id": f.get("id", ""), "title": f.get("title", ""), "reason": ""}
                      for f in rejected],
        "attacker_model": {},
        "revisor_notes": "",
        "error": "Report Agent failed to produce valid JSON after 2 attempts.",
    }


def _write_report(report: dict, target: str) -> None:
    """Write report to hunter_report.json and exploitation artifact file."""
    SCAN_RESULTS.mkdir(parents=True, exist_ok=True)

    # Main report
    report_path = SCAN_RESULTS / "hunter_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"[report_agent] Saved: {report_path}")

    # Exploitation artifact
    exploit_dir = SCAN_RESULTS / "exploitation"
    exploit_dir.mkdir(parents=True, exist_ok=True)

    # Clean target for filename
    clean_target = target.replace("https://", "").replace("http://", "")
    clean_target = clean_target.replace("/", "_").replace(":", "_")[:50]

    artifact_path = exploit_dir / f"{clean_target}_hunter_agent.json"
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"[report_agent] Saved artifact: {artifact_path}")
