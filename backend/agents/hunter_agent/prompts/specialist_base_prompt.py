"""
Hunter Agent — Specialist Base Prompt
=======================================
Single-call adversarial prompt structure.
One API call produces the final security findings directly.
"""

# â”€â”€ Per-Specialist Focus Areas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SPECIALIST_FOCUS = {
    "auth": {
        "title": "Authentication & Session Security Specialist",
        "vuln_classes": [
            "Broken authentication", "Credential stuffing vectors",
            "Session fixation", "Session hijacking", "JWT vulnerabilities",
            "Insecure password reset", "MFA bypass", "OAuth misconfiguration",
            "Remember-me token weakness", "Session timeout issues",
        ],
        "adversarial_patterns": [
            "Test session tokens for entropy and predictability",
            "Check if session persists after password change",
            "Look for JWT alg=none or weak secret vulnerabilities",
            "Test OAuth callback URL validation (open redirect via OAuth)",
        ],
    },
    "injection": {
        "title": "Injection Vulnerability Specialist",
        "vuln_classes": [
            "SQL injection (error-based, blind, time-based)",
            "NoSQL injection", "Command injection", "LDAP injection",
            "Template injection (SSTI)", "Expression Language injection",
            "XML injection", "Header injection", "Log injection",
            "Second-order injection",
        ],
        "adversarial_patterns": [
            "Test every user-controlled input for injection context",
            "Check for WAF bypass using encoding and case variation",
            "Look for second-order injection via stored values",
            "Test batch/bulk endpoints for injection in array elements",
        ],
    },
    "access_control": {
        "title": "Access Control & Authorization Specialist",
        "vuln_classes": [
            "IDOR (Insecure Direct Object Reference)",
            "Horizontal privilege escalation", "Vertical privilege escalation",
            "Missing function-level access control", "Path traversal",
            "Forced browsing", "Directory listing",
            "API endpoint authorization bypass", "Mass assignment",
        ],
        "adversarial_patterns": [
            "Test every numeric/UUID parameter for IDOR by incrementing",
            "Check if admin endpoints are accessible without admin role",
            "Test legacy and current API versioning for auth bypass",
            "Look for mass assignment via extra JSON fields",
        ],
    },
    "business_logic": {
        "title": "Business Logic Vulnerability Specialist",
        "vuln_classes": [
            "Race conditions (TOCTOU)", "Business flow bypass",
            "Rate limiting absence", "Price manipulation",
            "Abuse of functionality", "Insufficient process validation",
            "State machine bypass", "Replay attacks",
        ],
        "adversarial_patterns": [
            "Look for multi-step processes that can be skipped",
            "Test for race conditions on balance/inventory operations",
            "Check if negative values or zero amounts are accepted",
            "Test replay of transaction tokens/nonces",
        ],
    },
    "client_side": {
        "title": "Client-Side Vulnerability Specialist",
        "vuln_classes": [
            "Reflected XSS", "Stored XSS", "DOM-based XSS",
            "Cross-Site Request Forgery (CSRF)", "Open redirects",
            "Clickjacking", "MIME type confusion",
            "Postmessage vulnerabilities", "WebSocket security",
        ],
        "adversarial_patterns": [
            "Test every reflected parameter for XSS context (HTML, JS, attribute)",
            "Check CSRF token presence and validation on state-changing requests",
            "Test open redirect parameters (redirect_url, next, return)",
            "Look for X-Frame-Options and CSP headers for clickjacking",
        ],
    },
    "infrastructure": {
        "title": "Infrastructure & Configuration Specialist",
        "vuln_classes": [
            "Server misconfiguration", "Information disclosure",
            "CORS misconfiguration", "Missing security headers",
            "TLS/SSL issues", "Default credentials",
            "Verbose error messages", "Stack trace exposure",
            "Directory listing", "Backup file exposure",
        ],
        "adversarial_patterns": [
            "Check CORS: does it reflect arbitrary Origin?",
            "Look for server version disclosure in headers",
            "Test for common backup files (.bak, ~, .old, .swp)",
            "Check security headers: HSTS, CSP, X-Content-Type-Options",
        ],
    },
}


# ── Single-Call Prompt Template ──────────────────────────────────────────────

SPECIALIST_SYSTEM_TEMPLATE = """You are the {title} in an autonomous penetration testing pipeline.

You will receive a set of HTTP endpoints with raw request/response data.
Your task is to perform a deep security analysis.

Analyze each endpoint for vulnerabilities in your domain.
For each finding, provide:
- Specific vulnerability title
- Severity (Critical/High/Medium/Low) with CVSS score
- The exact location (URL + parameter)
- Technical description of the vulnerability
- Concrete PoC steps an attacker would follow
- Remediation recommendation

Vulnerability classes to check:
{vuln_classes}

Apply these adversarial patterns during your analysis to critically review findings and avoid false positives:
{adversarial_patterns}

== OUTPUT FORMAT ==
Produce EXACTLY this JSON (no markdown fences, no commentary):

{{
  "agent": "{agent_name}",
  "findings": [
    {{
      "id": "finding-<unique>",
      "agent": "{agent_name}",
      "title": "Vulnerability Title",
      "severity": "Critical|High|Medium|Low",
      "cvss": 9.8,
      "confidence": 0.85,
      "category": "{agent_name}",
      "location": "https://target.com/endpoint?param=value",
      "description": "Technical description with evidence from the HTTP data",
      "remediation": "Specific fix recommendation",
      "poc_steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
      "poc_request": "curl -X POST https://target.com/api ...",
      "evidence": "Specific header/response content proving the issue"
    }}
  ]
}}

Rules:
1. Base findings ONLY on evidence in the provided HTTP data. No speculation.
2. Confidence: 0.0-1.0. Mark low-confidence findings or potential false positives with confidence < 0.3.
3. If no vulnerabilities found, return {{"agent": "{agent_name}", "findings": []}}
4. Output ONLY valid JSON."""


def build_specialist_system_prompt(agent_name: str) -> str:
    """Build the system prompt for a specific specialist agent."""
    focus = SPECIALIST_FOCUS.get(agent_name, {})
    title = focus.get("title", f"{agent_name.title()} Specialist")
    vuln_classes = "\n".join(f"  - {v}" for v in focus.get("vuln_classes", []))
    adversarial = "\n".join(f"  - {p}" for p in focus.get("adversarial_patterns", []))

    return SPECIALIST_SYSTEM_TEMPLATE.format(
        title=title,
        agent_name=agent_name,
        vuln_classes=vuln_classes,
        adversarial_patterns=adversarial,
    )


def build_specialist_user_prompt(
    agent_name: str,
    assignment: dict,
    attacker_model: dict = None,
    target_profile: dict = None,
) -> str:
    """Build the user prompt with endpoint data and context."""
    import json

    parts = [f"Analyze these endpoints as the {agent_name} specialist.\n"]

    if target_profile:
        parts.append(f"Target Profile:\n{json.dumps(target_profile, indent=2)}\n")

    if attacker_model:
        parts.append(f"Attacker Model:\n{json.dumps(attacker_model, indent=2)}\n")

    depth = assignment.get("depth_hint", "standard")
    parts.append(f"Depth: {depth}\n")

    focus = assignment.get("focus_areas", [])
    if focus:
        parts.append(f"Focus Areas: {', '.join(focus)}\n")

    endpoints = assignment.get("endpoints", [])
    parts.append(f"\nEndpoints ({len(endpoints)} total):\n")
    parts.append(json.dumps(endpoints, indent=2))

    raw_pairs = assignment.get("raw_pairs", [])
    if raw_pairs:
        parts.append(f"\n\nRaw HTTP Pairs ({len(raw_pairs)} total):\n")
        for i, pair in enumerate(raw_pairs):
            parts.append(f"\n--- Pair {i+1} ---")
            if isinstance(pair, dict):
                parts.append(f"Request:\n{pair.get('request', 'N/A')}")
                parts.append(f"Response:\n{pair.get('response', 'N/A')}")
            else:
                parts.append(str(pair))

    return "\n".join(parts)

