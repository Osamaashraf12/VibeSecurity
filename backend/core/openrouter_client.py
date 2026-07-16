"""
OpenRouter Client
=========================================================
This module is the single LLM infrastructure layer for the VibeSecurity backend.
It uses the OpenAI-compatible SDK pointed at OpenRouter's endpoint.

Consumers:
  - ai_hacker.py HTTP pair analysis via analyze_req_res_pair()
  - routes_ai.py /analyze_traffic endpoint
  - Hunter Agent via analyze_full_crawl() (reserved hook)

Environment Variables Required:
  OPENROUTER_API_KEY        â€” mandatory, RuntimeError if missing
  OPENROUTER_BASE_URL       â€” defaults to https://openrouter.ai/api/v1
  OPENROUTER_SITE_URL       â€” for HTTP-Referer header (OpenRouter ToS)
  OPENROUTER_APP_NAME       â€” for X-Title header (OpenRouter ToS)
  OPENROUTER_HACKER_PRIMARY â€” primary model for HTTP pair analysis
  OPENROUTER_HACKER_FALLBACKâ€” fallback model on capacity errors
"""

import os
import re
import json
import typing
import logging
import time
import asyncio
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from openai import OpenAI, APIError, RateLimitError, APIConnectionError, APIStatusError
from tenacity import (
    retry, wait_exponential, stop_after_attempt,
    retry_if_exception_type, before_sleep_log
)

# Load environment at module level
load_dotenv(find_dotenv())

logger = logging.getLogger(__name__)

# â”€â”€ Validate API Key â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not _api_key:
    logger.warning("OPENROUTER_API_KEY is missing or empty. Set it in your .env file: OPENROUTER_API_KEY=sk-or-...")

# â”€â”€ Configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "http://localhost:8000")
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "VibeSecurity")
DEFAULT_MODEL = os.environ.get("OPENROUTER_DEFAULT_MODEL", "openai/gpt-oss-120b:free")
HACKER_PRIMARY = os.environ.get("OPENROUTER_HACKER_PRIMARY", "openai/gpt-oss-120b:free")
HACKER_FALLBACK = os.environ.get("OPENROUTER_HACKER_FALLBACK", "qwen/qwen3-coder:free")

# Path for quota persistence
from backend.core.paths import QUOTA_FILE


# â”€â”€ Data Schemas â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class VulnerabilityFinding(typing.TypedDict):
    """Schema for all vulnerability findings â€” compatible with existing pipeline."""
    title: str
    severity: str
    category: str
    location: str
    description: str
    remediation: str
    poc_steps: list[str]

# Headers that never contain security-relevant info â€” stripped to save tokens
NOISE_HEADERS = [
    'accept-encoding', 'accept-language', 'connection', 'cache-control',
    'pragma', 'upgrade-insecure-requests', 'dnt', 'te', 'if-none-match',
    'if-modified-since', 'accept-charset', 'keep-alive',
]


# â”€â”€ Thinking Level â†’ Temperature Mapping â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
THINKING_LEVEL_MAP = {
    "minimal": 0.0,   # Most deterministic â€” best for structured JSON conversion
    "low": 0.1,
    "medium": 0.3,
    "high": 0.5,      # More exploratory â€” best for creative security analysis
}


class OpenRouterClient:
    """
    LLM client for OpenRouter.
    Uses the OpenAI SDK with OpenRouter-specific headers and endpoint.
    """

    def __init__(self):
        self._client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=_api_key,
            default_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title": OPENROUTER_APP_NAME,
            }
        )
        self._primary_model = HACKER_PRIMARY
        self._fallback_model = HACKER_FALLBACK
        self._default_model = DEFAULT_MODEL
        logger.info(f"OpenRouterClient initialized | Primary: {self._primary_model} | Fallback: {self._fallback_model}")

    # â”€â”€ Core Generation (with retry) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    def _call_api(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 98304,   # 131072 total - ~32K reserved for input prompt
        response_format: dict = None,
    ) -> dict:
        """
        Low-level API call with retry logic.
        Returns the raw response dict from the OpenAI SDK.
        
        Retries on: 429 (RateLimitError), connection errors
        Does NOT retry on: 400, 401 (auth errors)
        """
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = self._client.chat.completions.create(**kwargs)
            
            # Token tracking
            usage = response.usage
            if usage:
                logger.info(
                    f"[Tokens] model={model} | prompt={usage.prompt_tokens} "
                    f"completion={usage.completion_tokens} total={usage.total_tokens}"
                )

            # Quota tracking from response headers (best effort)
            self._update_quota_from_response(response)

            return response
        except APIStatusError as e:
            # Don't retry on 400/401 â€” these are permanent auth errors
            if e.status_code in (400, 401):
                logger.error(f"Permanent API error ({e.status_code}): {e.message}")
                raise
            # Capacity / provider-blocked / model_not_found â†’ trigger fallback
            # 403 here means the *provider* (not OpenRouter auth) blocked the request
            if e.status_code in (403, 502, 503, 404):
                logger.warning(f"Model unavailable/provider error ({e.status_code}) for {model}")
                raise
            raise

    def _call_with_fallback(
        self,
        messages: list[dict],
        model: str = None,
        fallback: str = None,
        temperature: float = 0.0,
        max_tokens: int = 98304,   # 131072 total - ~32K reserved for input prompt
        response_format: dict = None,
    ) -> dict:
        """
        Calls _call_api with the primary model. If it fails with a capacity
        or model_not_found error, retries with the fallback model.
        """
        model = model or self._primary_model
        fallback = fallback or self._fallback_model

        try:
            return self._call_api(messages, model, temperature, max_tokens, response_format)
        except APIStatusError as e:
            if e.status_code in (403, 502, 503, 404) and fallback and fallback != model:
                logger.warning(f"âš ï¸ Primary model {model} blocked/unavailable ({e.status_code}). Falling back to {fallback}")
                return self._call_api(messages, fallback, temperature, max_tokens, response_format)
            raise

    # â”€â”€ Quota Management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _update_quota_from_response(self, response):
        """Parse rate limit headers from response and persist quota status."""
        try:
            # The OpenAI SDK wraps headers; try to access raw response
            raw = getattr(response, '_raw_response', None)
            if raw and hasattr(raw, 'headers'):
                headers = raw.headers
                remaining = headers.get('x-ratelimit-remaining')
                limit = headers.get('x-ratelimit-limit')
                reset = headers.get('x-ratelimit-reset')

                if remaining is not None:
                    quota_data = {
                        "used": int(limit or 200) - int(remaining),
                        "remaining": int(remaining),
                        "limit": int(limit or 200),
                        "reset_at": reset or "",
                        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
                    # Atomic write: write to temp file then replace to avoid partial reads
                    import tempfile
                    tmp_fd, tmp_path = tempfile.mkstemp(
                        dir=QUOTA_FILE.parent, prefix=".quota_tmp_", suffix=".json"
                    )
                    try:
                        with os.fdopen(tmp_fd, "w") as f:
                            json.dump(quota_data, f, indent=2)
                        import os as _os
                        _os.replace(tmp_path, QUOTA_FILE)
                    except Exception:
                        try:
                            import os as _os2
                            _os2.unlink(tmp_path)
                        except OSError:
                            pass
                        raise
        except Exception as e:
            logger.debug(f"Quota tracking update failed (non-critical): {e}")

    def get_quota_status(self) -> dict:
        """
        Returns current API quota status from persisted file.
        Returns: {"used": int, "remaining": int, "limit": int, "reset_at": str}
        """
        try:
            if QUOTA_FILE.exists():
                with open(QUOTA_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to read quota file: {e}")

        return {
            "used": 0,
            "remaining": 200,
            "limit": 200,
            "reset_at": "",
            "last_updated": ""
        }

    # â”€â”€ Public Methods â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def generate_text(
        self,
        prompt: str,
        system_prompt: str = None,
        model: str = None,
        thinking_level: str = None,
        include_thoughts: bool = False,
    ) -> str:
        """
        Standard text generation.

        Args:
            prompt: User prompt text.
            system_prompt: Optional system instruction override.
            model: Model to use (defaults to DEFAULT_MODEL).
            thinking_level: 'minimal', 'low', 'medium', 'high' â†’ maps to temperature.
            include_thoughts: If True, requests explicit reasoning in output.

        Returns:
            Generated text string.
        """
        temperature = THINKING_LEVEL_MAP.get(thinking_level, 0.2)
        model = model or self._default_model

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if include_thoughts:
            prompt = "Provide your internal reasoning in a <thought> block first.\n\n" + prompt

        messages.append({"role": "user", "content": prompt})

        response = self._call_with_fallback(
            messages=messages,
            model=model,
            temperature=temperature,
        )

        if getattr(response.choices[0], "finish_reason", None) == "length":
            logger.warning(f"OpenRouter response truncated due to length limits (model: {model})")
        return response.choices[0].message.content or ""

    def generate_json(
        self,
        prompt: str,
        system_prompt: str = None,
        model: str = None,
        schema_keys: list[str] = None,
        thinking_level: str = None,
    ) -> str:
        """
        Structured JSON generation with extraction, repair, and validation.

        Pipeline:
          1. Call model with json_object response_format
          2. Extract JSON from response (strips markdown fences, attempts repair)
          3. Validate required keys
          4. If invalid, retry with a CLEAN simplified prompt (no broken context)

        Returns:
            Validated JSON string.
        """
        temperature = THINKING_LEVEL_MAP.get(thinking_level, 0.1)
        model = model or self._primary_model
        schema_keys = schema_keys or FINDING_REQUIRED_KEYS

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # First attempt
        response = self._call_with_fallback(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        if getattr(response.choices[0], "finish_reason", None) == "length":
            logger.warning(f"OpenRouter JSON response truncated due to length limits (model: {model})")
        raw_text = response.choices[0].message.content or "{}"
        raw_text = self._extract_json(raw_text)

        # Post-parse validation
        validation_error = self._validate_findings_json(raw_text, schema_keys)
        if validation_error:
            logger.warning(f"JSON validation failed: {validation_error}. Retrying with clean prompt.")

            # IMPORTANT: Do NOT append the broken JSON into context.
            # That bloats token usage and causes a second truncation.
            # Instead, send a clean retry with the SAME system prompt
            # (to preserve the vulnerability checklist) but a shorter user prompt.
            retry_sys = system_prompt or (
                "You are a security analysis AI. "
                "Respond ONLY with valid JSON."
            )
            # Add conciseness constraint
            retry_sys += (
                "\nCRITICAL: Valid JSON only. Use abbreviated keys: "
                "t,s,c,l,d,r,p. Severity: C/H/M/L. PoC as single string."
            )

            retry_messages = [
                {"role": "system", "content": retry_sys},
                {"role": "user", "content": prompt}
            ]

            response = self._call_with_fallback(
                messages=retry_messages,
                model=model,
                temperature=0.1,  # Lower temperature for reliability
                response_format={"type": "json_object"},
            )
            raw_text = response.choices[0].message.content or "{}"
            raw_text = self._extract_json(raw_text)

        return raw_text

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Extracts and repairs JSON from model output.

        Handles common free-tier model issues:
        - JSON wrapped in markdown code fences (```json ... ```)
        - Leading/trailing whitespace or text
        - Truncated JSON (attempts to close brackets/braces)
        """
        if not text or not text.strip():
            return "{}"

        original = text

        # Strip markdown code fences
        fence_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)```', text)
        if fence_match:
            text = fence_match.group(1).strip()

        # Try parsing as-is first
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # Find the first { or [ to skip any preamble text
        first_brace = text.find('{')
        first_bracket = text.find('[')
        if first_brace == -1 and first_bracket == -1:
            return original  # Give up, return as-is for the validator to handle

        # Use whichever comes first
        if first_brace == -1:
            start = first_bracket
        elif first_bracket == -1:
            start = first_brace
        else:
            start = min(first_brace, first_bracket)

        text = text[start:]

        # Try parsing again after stripping preamble
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

        # â”€â”€ Improved repair: track actual nesting order â”€â”€
        repaired = text
        nesting_stack = []  # tracks '{' and '[' in their actual order
        in_string = False
        escape_next = False

        for ch in repaired:
            if escape_next:
                escape_next = False
                continue
            if ch == chr(92):  # backslash
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            # Outside strings, track nesting
            if ch == '{':
                nesting_stack.append('{')
            elif ch == '[':
                nesting_stack.append('[')
            elif ch == '}':
                if nesting_stack and nesting_stack[-1] == '{':
                    nesting_stack.pop()
            elif ch == ']':
                if nesting_stack and nesting_stack[-1] == '[':
                    nesting_stack.pop()

        # Close unclosed string
        if in_string:
            repaired += '"'

        # Handle truncation mid-structure
        stripped = repaired.rstrip()
        if stripped.endswith(':'):
            import re
            repaired = re.sub(r',?\s*"[^"]+"\s*:\s*$', '', repaired)
        elif stripped.endswith(','):
            repaired = repaired.rstrip().rstrip(',')

        # Close nesting in reverse order (innermost first)
        for opener in reversed(nesting_stack):
            repaired += '}' if opener == '{' else ']'

        try:
            json.loads(repaired)
            logger.info(f"Successfully repaired truncated JSON (closed {len(nesting_stack)} unclosed brackets/braces)")
            return repaired
        except json.JSONDecodeError:
            # Repair didn't work; return original for error reporting
            return original

    def _validate_findings_json(self, raw_text: str, required_keys: list[str]) -> str | None:
        """
        Validates that the JSON output contains findings with all required keys.
        Returns None if valid, or an error message string if invalid.
        """
        try:
            parsed = json.loads(raw_text)

            # Handle both {"findings": [...]} and bare [...]
            if isinstance(parsed, dict):
                findings = parsed.get("findings", [])
                if not findings and len(parsed) > 0:
                    # Might be a single finding as dict
                    findings = [parsed] if any(k in parsed for k in required_keys) else []
            elif isinstance(parsed, list):
                findings = parsed
            else:
                return "Response is not a JSON object or array"

            if not findings:
                return None  # Empty findings is valid (no vulns found)

            for i, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    return f"Finding #{i} is not a dict"
                missing = [k for k in required_keys if k not in finding]
                if missing:
                    return f"Finding #{i} is missing keys: {missing}"

            return None
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

    # â”€â”€ HTTP Input Optimisation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def _strip_noise_headers(text: str) -> str:
        """Strip security-irrelevant headers to save input tokens.
        Does NOT truncate content â€” full HTTP data is preserved."""
        if not text:
            return ""
        lines = text.split('\n')
        filtered = []
        for line in lines:
            line_lower = line.lower()
            if any(line_lower.startswith(nh + ':') for nh in NOISE_HEADERS):
                continue
            filtered.append(line)
        return '\n'.join(filtered)

    @staticmethod
    def _minimize_body(text: str) -> str:
        """Conservatively reduce HTTP body size while preserving ALL security-relevant content.
        
        Only strips:
        - <style>...</style> inner code (CSS has no security relevance)
        - Image data URIs (data:image/...) â€” just pixel data
        - Excessive whitespace and blank lines
        
        Keeps everything else: scripts, HTML comments, encoded strings, etc.
        """
        if not text:
            return text

        # Split headers from body (separated by double newline)
        parts = re.split(r'\n\s*\n', text, maxsplit=1)
        if len(parts) < 2:
            return text  # No body found, return as-is
        
        headers = parts[0]
        body = parts[1][:500_000]  # Cap body size to prevent ReDoS

        # 1. Strip <style>...</style> inner code (CSS is never security-relevant)
        body = re.sub(
            r'<style[^>]*>[\s\S]*?</style>',
            '<style>[stripped]</style>',
            body, flags=re.IGNORECASE
        )

        # 2. Strip image data URIs only (data:image/png;base64,... â€” just pixels)
        body = re.sub(
            r'data:image/[a-zA-Z0-9+]+;base64,[A-Za-z0-9+/=]{50,}',
            'data:image/[stripped]',
            body
        )

        # 3. Collapse excessive whitespace: multiple blank lines â†’ single blank line
        body = re.sub(r'\n\s*\n\s*\n', '\n\n', body)

        # 4. Strip trailing whitespace per line
        body = '\n'.join(line.rstrip() for line in body.split('\n'))

        return headers + '\n\n' + body

    @classmethod
    def _prepare_http(cls, text: str) -> str:
        """Full HTTP preparation pipeline: strip noise headers + minimize body."""
        text = cls._strip_noise_headers(text)
        text = cls._minimize_body(text)
        return text

    # â”€â”€ HTTP Pair Analysis Method â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def analyze_req_res_pair(
        self,
        http_request: str,
        http_response: str,
        context: dict = None,
        system_prompt: str = None,
    ) -> str:
        """
        Analyzes a single HTTP request/response pair for vulnerabilities
        using a single massive scan and expects Markdown output.

        Returns:
            String containing the AI's Markdown report.
        """
        # Prepare HTTP data: strip noise headers + minimize body (no char cap)
        req_clean = self._prepare_http(http_request)
        res_clean = self._prepare_http(http_response)

        user_prompt = f"Find ALL vulnerabilities in the payload below.\n\n<req>\n{req_clean}\n</req>\n\n<res>\n{res_clean}\n</res>\n"
        if context:
            user_prompt += f"\nContext: {json.dumps(context)}\n"

        logger.info(f"[*] Starting massive one-pass scan with OpenRouter (max tokens=131072)...")

        # Run sync LLM call in a thread to avoid blocking the event loop
        response_text = await asyncio.to_thread(
            self.generate_text,
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=self._primary_model,
            thinking_level="high",   # temperature=0.0 â€” most deterministic
        )
        return response_text

    # â”€â”€ Hunter Agent Reserved Hook â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def analyze_full_crawl(self, crawl_data: list[dict]) -> dict:
        """
        Reserved for Hunter Agent full-crawl analysis with a router/subagent pattern.
        
        Raises:
            NotImplementedError: Always. This is a Phase 2 stub.
        """
        raise NotImplementedError(
            "analyze_full_crawl() is reserved for the Hunter Agent. "
            "Use analyze_req_res_pair() for single-pair analysis."
        )


# â”€â”€ Module-Level Singleton â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# This allows `from backend.core.openrouter_client import client` as a convenience,
# but consumers can also instantiate OpenRouterClient() directly.
try:
    client = OpenRouterClient()
except Exception as e:
    logger.warning(f"OpenRouterClient auto-init failed: {e}")
    client = None

