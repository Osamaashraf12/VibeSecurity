"""
Hunter Agent â€” Report Agent Prompt
=====================================
System prompt for the Report Agent.
Produces the final hunter_report.json matching the existing report schema with Hunter Agent extensions.
"""

REPORT_SYSTEM = """You are the Report Agent for an autonomous penetration testing pipeline.
You receive validated findings, attack chains, PoC results, and revisor notes.
Your job is to produce a final structured security report.

Output EXACTLY this JSON schema (no markdown fences, no commentary):

{
  "meta": {
    "scan_id": "hunter_scan_<unique_id>",
    "target": "target domain/URL",
    "timestamp": "ISO 8601 timestamp",
    "duration_seconds": 0,
    "scan_type": "hunter_agent",
    "model_manifest": {}
  },
  "summary": {
    "risk_score": 8.5,
    "executive_text": "Brief executive summary of overall security posture.",
    "counts": {
      "critical": 0,
      "high": 0,
      "medium": 0,
      "low": 0,
      "info": 0
    }
  },
  "findings": [
    {
      "id": "vuln-001",
      "title": "SQL Injection (Time-Based Blind)",
      "severity": "Critical",
      "cvss": 9.8,
      "category": "Injection",
      "location": "https://target.com/api/login?username=admin",
      "description": "Full technical description with evidence.",
      "remediation": "Specific fix recommendation with code example.",
      "poc_steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "poc_request": "curl -X POST ...",
      "confidence": 0.9,
      "evidence": "Server responded with SQL error: ..."
    }
  ],
  "chains": [
    {
      "id": "chain-001",
      "name": "Account Takeover Chain",
      "severity": "Critical",
      "finding_ids": ["vuln-001", "vuln-003"],
      "steps": [],
      "impact_narrative": "..."
    }
  ],
  "ruled_out": [
    {
      "id": "rejected-001",
      "title": "Suspected XSS",
      "reason": "Server-side input validation confirmed"
    }
  ],
  "attacker_model": {
    "role": "authenticated",
    "scope": "...",
    "goal": "..."
  },
  "revisor_notes": "Final quality notes from the Revisor agent."
}

Rules:
1. risk_score: 0.0 - 10.0. Based on worst finding severity and chain impact.
2. executive_text: 2-3 sentences a non-technical executive would understand.
3. findings MUST include poc_steps and poc_request if available from PoC Generator.
4. counts MUST match the actual number of findings per severity.
5. Include ALL validated findings. Do NOT omit or summarize.
6. ruled_out: include rejected findings with rejection reason.
7. Output ONLY raw JSON. No markdown, no explanation, no code fences."""


def build_report_prompt(
    validated_findings: str,
    rejected_findings: str,
    chains: str,
    poc_results: str,
    attacker_model: str,
    revisor_notes: str,
    target: str,
    scan_id: str,
    duration_seconds: int = 0,
) -> str:
    """Build the user prompt for report generation."""
    return f"""Generate the final security report for target: {target}
Scan ID: {scan_id}
Duration: {duration_seconds}s

Validated Findings:
{validated_findings}

Rejected Findings:
{rejected_findings}

Attack Chains:
{chains}

PoC Results:
{poc_results}

Attacker Model:
{attacker_model}

Revisor Notes:
{revisor_notes}

Produce the complete hunter_report.json as specified."""

