"""
Null-safe utilities for handling LLM extraction outputs
"""
import json
from typing import Any, Dict, List, Optional


def normalize_nulls(obj: Any) -> Any:
    """
    Recursively replace None values with safe defaults.
    Prevents .lower(), .strip(), .split() crashes on None.
    """
    if isinstance(obj, dict):
        return {k: normalize_nulls(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [normalize_nulls(v) for v in obj]
    elif obj is None:
        return ""
    elif isinstance(obj, str):
        return obj
    elif isinstance(obj, (int, float, bool)):
        return obj
    return str(obj)


def safe_lower(value: Any) -> str:
    """Safely convert to lowercase, returns empty string for None"""
    if value is None:
        return ""
    return str(value).lower()


def safe_strip(value: Any) -> str:
    """Safely strip whitespace"""
    if value is None:
        return ""
    return str(value).strip()


def safe_get(data: dict, *keys, default: Any = "") -> Any:
    """
    Safely navigate nested dict with defaults
    Usage: safe_get(data, "company_info", "sector", default="technology")
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        if result is None:
            return default
    return result if result is not None else default


def ensure_list(value: Any) -> List:
    """Ensure value is a list, returns empty list for None"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def ensure_dict(value: Any) -> Dict:
    """Ensure value is a dict, returns empty dict for None"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {}


def clean_currency(value: Any) -> str:
    """Clean currency value, extract number"""
    if value is None:
        return ""
    value_str = str(value).strip()
    # Extract just the number part
    import re
    match = re.search(r'[\d.]+', value_str)
    return match.group(0) if match else value_str


def parse_optional_float(value: Any) -> Optional[float]:
    """Parse optional float, returns None for invalid"""
    if value is None:
        return None
    try:
        return float(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return None


def parse_optional_int(value: Any) -> Optional[int]:
    """Parse optional int, returns None for invalid"""
    if value is None:
        return None
    try:
        return int(str(value).replace(',', '').split('.')[0])
    except (ValueError, TypeError):
        return None


def truncate_text(text: Any, max_length: int = 200) -> str:
    """Safely truncate text"""
    if text is None:
        return ""
    text_str = str(text)[:max_length]
    return text_str