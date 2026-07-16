"""
VibeSecurity Domain / Target Validation
=========================================
Shared validation functions for use by all CLI wrappers before passing
a target to subprocess.run(). Prevents command injection via malformed
domain strings.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Strict allowlist: hostnames, subdomains, bare IP-like domains (not full IP validation)
# Disallows: spaces, shell metacharacters, path traversal, unicode homoglyphs
_DOMAIN_RE = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
)

# Allow bare hostnames (single label) and plain IPs only for specific tools
_HOSTNAME_RE = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9\-\.]{0,253}[a-zA-Z0-9]$'
)


def validate_target_domain(target: str, strict: bool = True) -> str:
    """
    Validate that a target is a safe domain string before passing to subprocess.
    Raises ValueError if the target fails validation.

    Args:
        target: The domain/hostname string to validate.
        strict: If True, requires FQDN format (label.label.tld).
                If False, allows single-label hostnames (e.g., 'localhost').

    Returns:
        The cleaned target string (stripped).

    Raises:
        ValueError: If the target contains shell-unsafe or invalid characters.
    """
    if not target or not isinstance(target, str):
        raise ValueError("Target must be a non-empty string")

    target = target.strip().lower()

    # Hard block on obvious injection patterns
    BLOCKED_CHARS = set(';<>|&`$(){}[]\\\'\"!*?\n\r\t ')
    if any(c in BLOCKED_CHARS for c in target):
        raise ValueError(
            f"Target '{target}' contains shell-unsafe characters and was rejected"
        )

    if len(target) > 253:
        raise ValueError(f"Target domain too long ({len(target)} chars, max 253)")

    if strict:
        if not _DOMAIN_RE.match(target):
            raise ValueError(
                f"Target '{target}' does not match expected FQDN format "
                f"(e.g., 'example.com'). Rejecting to prevent injection."
            )
    else:
        if not _HOSTNAME_RE.match(target):
            raise ValueError(
                f"Target '{target}' contains invalid hostname characters"
            )

    logger.debug(f"[validate] Target '{target}' passed validation")
    return target
