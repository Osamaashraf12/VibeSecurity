"""
Token Counter Utility for Hunter Agent
=======================================
Simple token estimation for quota planning.
Uses a rough 4-characters-per-token heuristic for fast estimation
without requiring a tokenizer dependency.
"""


def estimate_tokens(text: str) -> int:
    """
    Estimates the number of tokens in a text string.
    Uses a 4-chars-per-token heuristic (average for English text).
    
    Args:
        text: Input text string.
    
    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_crawl_tokens(crawl_data: list[dict]) -> dict:
    """
    Estimates total tokens for a full crawl dataset.
    
    Args:
        crawl_data: List of dicts, each containing 'request' and 'response' keys.
    
    Returns:
        Dict with 'total_tokens', 'pair_count', and 'avg_tokens_per_pair'.
    """
    import json
    
    total = 0
    for pair in crawl_data:
        serialized = json.dumps(pair)
        total += estimate_tokens(serialized)
    
    pair_count = len(crawl_data)
    return {
        "total_tokens": total,
        "pair_count": pair_count,
        "avg_tokens_per_pair": total // pair_count if pair_count > 0 else 0,
    }
