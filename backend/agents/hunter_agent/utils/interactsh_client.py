"""
Hunter Agent — Interactsh Client (Stub)
=========================================
Out-of-band (OOB) interaction verifier for blind vulnerabilities.
Currently stub — will be implemented when active verification is added.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class InteractshClient:
    """
    Stub for Interactsh OOB callback verification.
    Used by PoC Generator to verify blind SSRF, blind XXE, etc.
    """

    def __init__(self):
        self._active = False
        self._callback_url = ""
        logger.info("[InteractshClient] Initialized (stub mode)")

    async def register(self) -> str:
        """Register an interaction URL. Returns callback URL."""
        logger.warning("[InteractshClient] register() called on stub — returning placeholder")
        self._callback_url = "https://interactsh-placeholder.example.com"
        return self._callback_url

    async def poll(self) -> list[dict]:
        """Poll for OOB interactions. Returns list of interaction events."""
        logger.warning("[InteractshClient] poll() called on stub — returning empty")
        return []

    async def close(self) -> None:
        """Deregister the interaction URL."""
        self._active = False

    @property
    def callback_url(self) -> str:
        return self._callback_url
