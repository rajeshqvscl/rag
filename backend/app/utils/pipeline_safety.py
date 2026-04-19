"""
Pipeline safety utilities.
A single `safe_str()` helper + guarded wrappers used everywhere in the
extract → analyse → prompt → reply pipeline.

Import with:
    from app.utils.pipeline_safety import safe_str, safe_join, safe_get, guard_prompt
"""
from typing import Any, Optional


def safe_str(x: Any, default: str = "") -> str:
    """
    Return x as a string, or `default` if x is None / not a string.

    Usage:
        prompt = "Context: " + safe_str(context)
        full_text += safe_str(page_text)
    """
    if x is None:
        return default
    if isinstance(x, (bytes, bytearray)):
        return x.decode("utf-8", errors="replace")
    return str(x)


def safe_join(parts, sep: str = "\n\n") -> str:
    """
    Join a list of items that may contain None values.

    Usage:
        context = safe_join([chunk.get("text") for chunk in chunks])
    """
    return sep.join(safe_str(p) for p in (parts or []) if safe_str(p).strip())


def safe_get(d: Any, key: str, default: str = "") -> str:
    """
    dict.get() that always returns a string — never None.

    Usage:
        email = safe_get(request_body, "email")
        summary = safe_get(analysis, "summary")
    """
    if not isinstance(d, dict):
        return default
    val = d.get(key, default)
    return safe_str(val, default)


def guard_prompt(**kwargs) -> dict:
    """
    Sanitize all values in a prompt-context dict so no value is None.
    Returns a new dict where every value is a non-empty string or the
    original non-string type (list, int, etc.) unchanged.

    Usage:
        context = guard_prompt(
            company=company_name,
            summary=analysis.get("summary"),
            email=email_body,
        )
        prompt = f"Company: {context['company']}\\nSummary: {context['summary']}"
    """
    result = {}
    for k, v in kwargs.items():
        if v is None:
            result[k] = ""
        elif isinstance(v, str):
            result[k] = v
        elif isinstance(v, (list, dict, int, float, bool)):
            result[k] = v  # Leave structured types intact
        else:
            result[k] = str(v)
    return result
