import json
import logging
import asyncio
import time
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

# Path for saving http_report.json
from backend.core.paths import SCAN_RESULTS_DIR

_SCAN_RESULTS_DIR = SCAN_RESULTS_DIR

# ── Markdown → JSON Conversion Prompt ─────────────────────────────────────
_CONVERSION_SYSTEM_PROMPT = """You are a JSON conversion assistant. You receive a Markdown security vulnerability report and MUST convert it into a strictly valid JSON object.

Output ONLY valid JSON with NO markdown fences, NO commentary, NO extra text. Just the raw JSON object.

Required JSON schema:
{
  "meta": {
    "scan_id": "<generate a unique scan ID like http_scan_XXXX>",
    "target": "<extract the target domain/URL from the report or use 'manual-analysis'>",
    "timestamp": "<current ISO 8601 timestamp>",
    "duration_seconds": 0
  },
  "summary": {
    "risk_score": <float 0.0-10.0 based on highest CVSS/severity>,
    "executive_text": "<1-2 sentence summary of overall findings>",
    "counts": {
      "critical": <int>,
      "high": <int>,
      "medium": <int>,
      "low": <int>
    }
  },
  "findings": [
    {
      "id": "<vuln-001, vuln-002, etc.>",
      "title": "<vulnerability title>",
      "severity": "<Critical|High|Medium|Low>",
      "cvss": <float 0.0-10.0>,
      "category": "<category name>",
      "location": "<affected endpoint/parameter/header>",
      "description": "<description of the vulnerability>",
      "remediation": "<how to fix it>"
    }
  ]
}

Rules:
- Extract EVERY finding from the Markdown report into the findings array
- Map severity emojis: 🔴=Critical, 🟠=High, 🟡=Medium, 🔵=Low
- Assign reasonable CVSS scores: Critical=9.0-10.0, High=7.0-8.9, Medium=4.0-6.9, Low=0.1-3.9
- If the report says "No vulnerabilities detected", return an empty findings array with risk_score 0.0
- Output ONLY the JSON object, nothing else"""


class ChatRequest(BaseModel):
    message: str

class TrafficAnalysisRequest(BaseModel):
    http_request: str = Field(..., max_length=500_000)
    http_response: str = Field(..., max_length=500_000)
    analysis_type: str = "manual"

@router.post("/chat")
async def chat_endpoint(request: Request, req: ChatRequest):
    client = getattr(request.app.state, "llm_client", None)
    if not client:
        return {"response": "Backend Notification: LLM Client is not initialized."}
    
    response = await asyncio.to_thread(client.chat, req.message, persona="chat", history=True)
    if "error" in response: 
        raise HTTPException(status_code=500, detail=response["error"])
    return {"response": response.get("message", {}).get("content", "Error: No response.")}

# --- SYSTEM PARSER DISABLED FOR NOW ---
# @router.post("/parser_sys")
# async def parser_sys_endpoint(request: Request, req: ChatRequest):
#     client = getattr(request.app.state, "llm_client", None)
#     if not client: return {"response": "Error: LLM unavailable."}
#     response = client.chat(req.message, persona="parser_sys", history=True)
#     return {"response": response.get("message", {}).get("content", "Error")}

@router.post("/parser_user")
async def parser_user_endpoint(request: Request, req: ChatRequest):
    client = getattr(request.app.state, "llm_client", None)
    
    # Fallback if LLM is down to keep the UI functional
    if not client:
        print(f"⚠️ LLM Unavailable. Returning 503 for: {req.message}")
        raise HTTPException(status_code=503, detail="LLM unavailable")

    print(f"AI Parser Request: {req.message}")
    response = await asyncio.to_thread(client.chat, req.message, persona="parser_user", history=True)
    return {"response": response.get("message", {}).get("content", "Error")}


async def _convert_markdown_to_report_json(openrouter, markdown_text: str) -> dict | None:
    """
    Sends a second LLM call to convert the AI Hacker's Markdown report
    into structured JSON matching the report.json schema.
    Returns the parsed dict, or None on failure.
    """
    try:
        logger.info("[*] Starting Markdown → JSON conversion (second LLM call)...")
        print("[*] Starting Markdown → JSON conversion...")

        user_prompt = f"Convert the following security vulnerability report into the required JSON format:\n\n{markdown_text}"

        # Use generate_text with a low temperature for deterministic conversion
        raw_json = await asyncio.to_thread(
            openrouter.generate_text,
            prompt=user_prompt,
            system_prompt=_CONVERSION_SYSTEM_PROMPT,
            model=openrouter._fallback_model,  # Use fallback (lighter model) to save quota
            thinking_level="minimal",           # temperature=0.1 — deterministic
        )

        if not raw_json or len(raw_json.strip()) < 5:
            logger.warning("[-] Conversion returned empty response")
            return None

        # Clean and parse JSON
        cleaned = raw_json.strip()
        # Strip markdown fences if present
        if cleaned.startswith("```"):
            import re
            fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', cleaned, re.DOTALL)
            if fence_match:
                cleaned = fence_match.group(1).strip()

        parsed = json.loads(cleaned)

        # Inject current timestamp if missing
        if "meta" in parsed:
            if not parsed["meta"].get("timestamp"):
                parsed["meta"]["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if not parsed["meta"].get("scan_id"):
                parsed["meta"]["scan_id"] = f"http_scan_{uuid.uuid4().hex[:8]}"

        # Save to disk
        _SCAN_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        import uuid
        filename = f"http_report_{uuid.uuid4().hex[:8]}.json"
        output_path = _SCAN_RESULTS_DIR / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)

        logger.info(f"[+] {filename} saved to {output_path}")
        print(f"[+] {filename} saved to {output_path}")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"[-] JSON conversion parse error: {e}")
        print(f"[-] JSON conversion parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"[-] Markdown→JSON conversion failed: {e}")
        print(f"[-] Markdown→JSON conversion failed: {e}")
        return None


@router.post("/analyze_traffic")
async def analyze_traffic_endpoint(request: Request, req: TrafficAnalysisRequest):
    """
    Deep HTTP traffic analysis using OpenRouter.
    Returns structured vulnerability findings instead of raw text.
    After the primary Markdown analysis, a second LLM call converts
    the report into structured JSON (http_report.json) for the dashboard.
    """
    # Use the OpenRouter client for structured analysis
    openrouter = getattr(request.app.state, "openrouter_client", None)
    
    if not openrouter:
        # Fallback: try Ollama hacker persona if OpenRouter is unavailable
        ollama_client = getattr(request.app.state, "llm_client", None)
        if not ollama_client:
            raise HTTPException(status_code=503, detail="No AI backend available. Configure OPENROUTER_API_KEY in .env or start the Ollama server.")
        
        # Legacy Ollama path (kept as safety net)
        analysis_instructions = {
            "manual": "Focus: Find ALL vulnerabilities in this single HTTP request/response pair, including standard injections (SQLi, XSS) and logic flaws.\nOutput Format: Return ONLY a detailed list of the vulnerabilities found.",
            "pipeline": "Focus: Find ONLY complex business logic flaws (IDOR, parameter tampering, authorization bypasses) in this traffic.\nOutput Format: Provide a high-level overview followed by a detailed list of complex vulnerabilities.",
            "auth_only": "Focus strictly on authentication and authorization mechanisms.\nOutput Format: Return ONLY the authentication/authorization vulnerabilities found."
        }
        instruction = analysis_instructions.get(req.analysis_type, "Analyze the provided HTTP Request and Response for any security vulnerabilities.")
        prompt = f"""{instruction}

=== HTTP REQUEST ===
{req.http_request}

=== HTTP RESPONSE ===
{req.http_response}
"""
        response = ollama_client.chat(prompt, persona="hacker", history=False)
        if "error" in response:
            raise HTTPException(status_code=500, detail=response["error"])
        return {"response": response.get("message", {}).get("content", "Error: No findings generated.")}

    # Primary path: OpenRouter massive single-pass analysis
    try:
        logger.info("[*] Traffic analysis request received — starting massive OpenRouter scan...")
        
        # Load system prompt
        from backend.modules.exploitation.ai_hacker import _load_system_prompt
        system_prompt = _load_system_prompt()
        
        response_text = await openrouter.analyze_req_res_pair(
            http_request=req.http_request,
            http_response=req.http_response,
            system_prompt=system_prompt,
        )
        
        if not response_text or len(response_text.strip()) < 10:
            final_response_text = f"## ⚠️ Analysis Failed (Empty Response)\n\nThe OpenRouter model (`{openrouter._primary_model}`) returned an empty output. \n\n**Why did this happen?**\nYou are using a free-tier model with a massive 1-pass prompt. When processing large HTTP payloads (or if the payload trips provider safety filters), free OpenRouter models often silently fail and return an empty string rather than an error block.\n\n**Solutions:**\n1. Use the Gemini endpoint instead (which supports massive payloads).\n2. Switch back to the 5-pass split-scan architecture.\n3. Provide a smaller HTTP request/response pair."
            http_report_generated = False
        else:
            final_response_text = response_text.strip()

            # ── STEP 2: Convert Markdown → JSON (second LLM call) ──
            # This does NOT affect the primary model's output.
            # Uses the fallback (lighter) model to minimize quota impact.
            http_report_data = await _convert_markdown_to_report_json(openrouter, final_response_text)
            http_report_generated = http_report_data is not None
        
        return {
            "response": final_response_text,
            "findings": [],
            "model": str(getattr(openrouter, "_primary_model", "unknown-model")),
            "http_report_generated": http_report_generated,
        }
        
    except Exception as e:
        logger.error(f"OpenRouter analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
