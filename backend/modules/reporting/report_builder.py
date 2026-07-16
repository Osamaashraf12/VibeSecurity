"""Consolidate scan artifact files into report.json."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.core.paths import SCAN_RESULTS_DIR

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}


def build_report(target: str) -> dict[str, Any]:
    """Build the dashboard report for a target from runtime artifacts."""
    findings: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    exploitation_dir = SCAN_RESULTS_DIR / "exploitation"
    if exploitation_dir.exists():
        for file in sorted(exploitation_dir.iterdir()):
            if not file.is_file() or file.suffix != ".json":
                continue
            try:
                with open(file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                for finding in data.get("findings", []):
                    dedup_key = (finding.get("title", ""), finding.get("location", ""))
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    findings.append(_normalize_finding(finding))
            except Exception as exc:
                print(f"[ReportBuilder] Skipping {file.name}: {exc}")

    for file in sorted(SCAN_RESULTS_DIR.glob("**/*.jsonl")):
        try:
            with open(file, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        finding = _nuclei_to_finding(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if not finding:
                        continue
                    dedup_key = (finding["title"], finding["location"])
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    findings.append(finding)
        except Exception as exc:
            print(f"[ReportBuilder] Skipping JSONL {file.name}: {exc}")

    findings.sort(key=lambda item: SEVERITY_ORDER.get(item.get("severity", "unknown").lower(), 5))

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    cvss_values: list[float] = []
    for finding in findings:
        severity = finding.get("severity", "").lower()
        if severity in counts:
            counts[severity] += 1
        cvss = finding.get("cvss", 0.0)
        if cvss and cvss > 0:
            cvss_values.append(float(cvss))

    risk_score = round(sum(cvss_values) / len(cvss_values), 1) if cvss_values else 0.0
    report = {
        "meta": {
            "scan_id": f"report_{hashlib.md5(target.encode()).hexdigest()[:8]}",
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0,
        },
        "summary": {
            "risk_score": risk_score,
            "executive_text": _generate_executive_summary(target, counts, risk_score, len(findings)),
            "counts": counts,
        },
        "findings": findings,
    }

    SCAN_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = SCAN_RESULTS_DIR / "report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    print(f"[ReportBuilder] Generated report.json with {len(findings)} findings -> {report_path}")
    return report


def _normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    finding_id = finding.get("id") or f"find-{hashlib.md5(json.dumps(finding, sort_keys=True).encode()).hexdigest()[:8]}"
    return {
        "id": finding_id,
        "title": finding.get("title", "Untitled Finding"),
        "severity": finding.get("severity", "Unknown"),
        "cvss": finding.get("cvss", 0.0),
        "category": finding.get("category", "General"),
        "location": finding.get("location", ""),
        "description": finding.get("description", ""),
        "remediation": finding.get("remediation", ""),
    }


def _nuclei_to_finding(entry: dict[str, Any]) -> dict[str, Any] | None:
    info = entry.get("info", {})
    title = info.get("name")
    if not title:
        return None

    severity_map = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low", "info": "Info"}
    classification = info.get("classification", {})
    cvss = 0.0
    if classification.get("cvss-score"):
        try:
            cvss = float(classification["cvss-score"])
        except (TypeError, ValueError):
            pass

    matched_at = entry.get("matched-at", "")
    return {
        "id": f"nuclei-{hashlib.md5(f'{title}{matched_at}'.encode()).hexdigest()[:8]}",
        "title": title,
        "severity": severity_map.get(info.get("severity", "unknown").lower(), "Unknown"),
        "cvss": cvss,
        "category": info.get("tags", ["General"])[0] if info.get("tags") else "General",
        "location": matched_at,
        "description": info.get("description", ""),
        "remediation": info.get("remediation", ""),
    }


def _generate_executive_summary(target: str, counts: dict[str, int], risk_score: float, total: int) -> str:
    if total == 0:
        return (
            f"The scan of {target} completed successfully. "
            "No vulnerabilities were identified during this assessment."
        )

    if risk_score >= 8.0:
        posture = "critical"
    elif risk_score >= 6.0:
        posture = "concerning"
    elif risk_score >= 4.0:
        posture = "moderate"
    else:
        posture = "relatively secure"

    parts = [f"The security posture of {target} is {posture} (risk score: {risk_score}/10)."]
    if counts["critical"] > 0:
        parts.append(f"{counts['critical']} critical-severity issue(s) require immediate attention.")
    if counts["high"] > 0:
        parts.append(f"{counts['high']} high-severity issue(s) were identified.")
    if counts["medium"] > 0:
        parts.append(f"{counts['medium']} medium-severity issue(s) should be reviewed.")
    if counts["low"] > 0:
        parts.append(f"{counts['low']} low-severity informational finding(s) were noted.")
    parts.append(f"A total of {total} unique findings were consolidated from scan artifacts.")
    return " ".join(parts)
