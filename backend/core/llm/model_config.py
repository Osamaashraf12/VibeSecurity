"""Shared model configuration for Hunter Agent and payload generation."""

from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

MAX_ENDPOINTS_SINGLE_CALL = 15
RETRY_ATTEMPTS = 2
BACKOFF_SCHEDULE = [1.0, 4.0]
RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

DEFAULT_OPENROUTER_MODEL = "openai/gpt-oss-120b:free"

OPENROUTER_MODELS = {
    "threat_modeller": os.getenv("HUNTER_MODEL_THREAT_MODELLER", DEFAULT_OPENROUTER_MODEL),
    "coordinator": os.getenv("HUNTER_MODEL_COORDINATOR", DEFAULT_OPENROUTER_MODEL),
    "auth": os.getenv("HUNTER_MODEL_AUTH", DEFAULT_OPENROUTER_MODEL),
    "injection": os.getenv("HUNTER_MODEL_INJECTION", DEFAULT_OPENROUTER_MODEL),
    "access_control": os.getenv("HUNTER_MODEL_ACCESS_CONTROL", DEFAULT_OPENROUTER_MODEL),
    "business_logic": os.getenv("HUNTER_MODEL_BUSINESS_LOGIC", DEFAULT_OPENROUTER_MODEL),
    "client_side": os.getenv("HUNTER_MODEL_CLIENT_SIDE", DEFAULT_OPENROUTER_MODEL),
    "infrastructure": os.getenv("HUNTER_MODEL_INFRASTRUCTURE", DEFAULT_OPENROUTER_MODEL),
    "poc_generator": os.getenv("HUNTER_MODEL_POC_GENERATOR", DEFAULT_OPENROUTER_MODEL),
    "revisor": os.getenv("HUNTER_MODEL_REVISOR", DEFAULT_OPENROUTER_MODEL),
    "report_agent": os.getenv("HUNTER_MODEL_REPORT_AGENT", DEFAULT_OPENROUTER_MODEL),
    # Previously Gemini-only nodes — now unified under OpenRouter
    "synthesizer": os.getenv("HUNTER_MODEL_SYNTHESIZER", DEFAULT_OPENROUTER_MODEL),
    "chainer": os.getenv("HUNTER_MODEL_CHAINER", DEFAULT_OPENROUTER_MODEL),
    "payload_generator": os.getenv("HUNTER_MODEL_PAYLOAD_GENERATOR", DEFAULT_OPENROUTER_MODEL),
}

FALLBACKS = {
    "synthesizer": os.getenv("HUNTER_FALLBACK_SYNTHESIZER", DEFAULT_OPENROUTER_MODEL),
    "chainer": os.getenv("HUNTER_FALLBACK_CHAINER", DEFAULT_OPENROUTER_MODEL),
    "threat_modeller": os.getenv("HUNTER_FALLBACK_THREAT_MODELLER", DEFAULT_OPENROUTER_MODEL),
    "coordinator": os.getenv("HUNTER_FALLBACK_COORDINATOR", DEFAULT_OPENROUTER_MODEL),
    "auth": os.getenv("HUNTER_FALLBACK_AUTH", DEFAULT_OPENROUTER_MODEL),
    "injection": os.getenv("HUNTER_FALLBACK_INJECTION", DEFAULT_OPENROUTER_MODEL),
    "access_control": os.getenv("HUNTER_FALLBACK_ACCESS_CONTROL", DEFAULT_OPENROUTER_MODEL),
    "business_logic": os.getenv("HUNTER_FALLBACK_BUSINESS_LOGIC", DEFAULT_OPENROUTER_MODEL),
    "client_side": os.getenv("HUNTER_FALLBACK_CLIENT_SIDE", DEFAULT_OPENROUTER_MODEL),
    "infrastructure": os.getenv("HUNTER_FALLBACK_INFRASTRUCTURE", DEFAULT_OPENROUTER_MODEL),
    "poc_generator": os.getenv("HUNTER_FALLBACK_POC_GENERATOR", DEFAULT_OPENROUTER_MODEL),
    "revisor": os.getenv("HUNTER_FALLBACK_REVISOR", DEFAULT_OPENROUTER_MODEL),
    "report_agent": os.getenv("HUNTER_FALLBACK_REPORT_AGENT", DEFAULT_OPENROUTER_MODEL),
    "payload_generator": os.getenv("HUNTER_FALLBACK_PAYLOAD_GENERATOR", DEFAULT_OPENROUTER_MODEL),
}

REASONING_MODELS = {"z-ai/glm-4.5-air:free"}

SPECIALIST_NAMES = [
    "auth",
    "injection",
    "access_control",
    "business_logic",
    "client_side",
    "infrastructure",
]


def get_model(node_name: str) -> str:
    """Get the primary OpenRouter model for a named node."""
    return OPENROUTER_MODELS.get(node_name, DEFAULT_OPENROUTER_MODEL)


def get_fallback(node_name: str) -> str:
    """Get the fallback OpenRouter model for a named node."""
    return FALLBACKS.get(node_name, DEFAULT_OPENROUTER_MODEL)


def needs_reasoning(model: str) -> bool:
    """Return true when OpenRouter needs a reasoning flag for this model."""
    return model in REASONING_MODELS
