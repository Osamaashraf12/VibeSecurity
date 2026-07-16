"""Hunter Agent — Utils Package"""

from backend.core.llm.model_config import (
    get_model, get_fallback,
    SPECIALIST_NAMES, MAX_ENDPOINTS_SINGLE_CALL,
)

__all__ = [
    "get_model", "get_fallback",
    "SPECIALIST_NAMES", "MAX_ENDPOINTS_SINGLE_CALL",
]
