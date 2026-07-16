"""
Hunter Agent — HTTP Utilities
===============================
Shared HTTP processing helpers used across pipeline nodes.
"""

from __future__ import annotations

import re
import json
import logging

logger = logging.getLogger(__name__)

# Headers that never contain security-relevant info — stripped to save tokens
NOISE_HEADERS = [
    'accept-encoding', 'accept-language', 'connection', 'cache-control',
    'pragma', 'upgrade-insecure-requests', 'dnt', 'te', 'if-none-match',
    'if-modified-since', 'accept-charset', 'keep-alive',
]


def strip_noise_headers(text: str) -> str:
    """Strip security-irrelevant headers to save input tokens."""
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


def minimize_body(text: str) -> str:
    """
    Reduce HTTP body size while preserving ALL security-relevant content.
    Only strips CSS, image data URIs, and excessive whitespace.
    """
    if not text:
        return text

    parts = re.split(r'\n\s*\n', text, maxsplit=1)
    if len(parts) < 2:
        return text

    headers = parts[0]
    body = parts[1]

    # Strip <style> inner code
    body = re.sub(r'<style[^>]*>[\s\S]*?</style>', '<style>[stripped]</style>', body, flags=re.IGNORECASE)
    # Strip image data URIs
    body = re.sub(r'data:image/[a-zA-Z0-9+]+;base64,[A-Za-z0-9+/=]{50,}', 'data:image/[stripped]', body)
    # Collapse excessive whitespace
    body = re.sub(r'\n\s*\n\s*\n', '\n\n', body)
    # Strip trailing whitespace per line
    body = '\n'.join(line.rstrip() for line in body.split('\n'))

    return headers + '\n\n' + body


def prepare_http(text: str) -> str:
    """Full HTTP preparation pipeline: strip noise headers + minimize body."""
    text = strip_noise_headers(text)
    text = minimize_body(text)
    return text


def extract_json_from_response(raw: str) -> str:
    """
    Extract JSON from LLM output. Handles:
    - Markdown code fences (```json ... ```)
    - Leading/trailing text
    - Truncated JSON (basic repair)
    """
    if not raw or not raw.strip():
        return "{}"

    # Strip markdown fences
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)```', raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()

    # Try as-is
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # Find first { or [
    first_brace = raw.find('{')
    first_bracket = raw.find('[')
    if first_brace == -1 and first_bracket == -1:
        return raw

    if first_brace == -1:
        start = first_bracket
    elif first_bracket == -1:
        start = first_brace
    else:
        start = min(first_brace, first_bracket)

    raw = raw[start:]

    # Try again after stripping preamble
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # Basic repair: close unclosed brackets/braces
    nesting_stack = []
    in_string = False
    escape_next = False

    for ch in raw:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
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

    repaired = raw
    if in_string:
        repaired += '"'

    stripped = repaired.rstrip()
    if stripped.endswith(':'):
        repaired += ' null'
    elif stripped.endswith(','):
        repaired = repaired.rstrip().rstrip(',')

    for opener in reversed(nesting_stack):
        repaired += '}' if opener == '{' else ']'

    try:
        json.loads(repaired)
        logger.info(f"Repaired truncated JSON (closed {len(nesting_stack)} brackets)")
        return repaired
    except json.JSONDecodeError:
        return raw


def parse_and_validate_report(raw: str) -> dict:
    """
    Parse and validate the final hunter_report.json from Report Agent output.
    Raises ValueError if structure is invalid.
    """
    clean = extract_json_from_response(raw)
    data = json.loads(clean)

    if "meta" not in data:
        raise ValueError("Missing 'meta' field in report")
    if "findings" not in data:
        raise ValueError("Missing 'findings' field in report")
    if not isinstance(data["findings"], list):
        raise ValueError("'findings' must be an array")

    return data
