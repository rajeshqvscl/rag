"""
Central Metric Serializer — ensures every metric reaching frontend is a clean
display string, never a raw dict, list, or object.

Phase A of the accuracy improvement plan.
"""

import re
from typing import Any, Dict, List, Optional


def serialize_metric(value: Any, metric_type: str = "") -> str:
    """
    Convert any metric value to a clean display string.
    Never returns dicts, lists, or None — always a string.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        v = value.get("display_value") or value.get("value") or value.get("label") or ""
        if not isinstance(v, str):
            v = str(v) if v else ""
        return v
    if isinstance(value, list):
        parts = []
        for item in value[:3]:
            if isinstance(item, dict):
                parts.append(str(item.get("display_value", item.get("value", item.get("label", "")))))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def serialize_for_frontend(data: Dict) -> Dict:
    """
    Recursively serialize all values in a dict to ensure no [object Object] appears.
    Returns a clean dict with only strings, numbers, booleans, and lists of primitives.
    """
    if not isinstance(data, dict):
        return {}

    result = {}
    for key, value in data.items():
        if value is None:
            result[key] = ""
            continue
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, (int, float, bool)):
            result[key] = value
        elif isinstance(value, dict):
            result[key] = serialize_for_frontend(value)
        elif isinstance(value, list):
            result[key] = [_serialize_list_item(v) for v in value]
        else:
            result[key] = str(value)
    return result


def _serialize_list_item(item: Any) -> Any:
    """Serialize a single list item to a frontend-safe value."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item
    if isinstance(item, (int, float, bool)):
        return item
    if isinstance(item, dict):
        serialized = {}
        for k, v in item.items():
            if isinstance(v, str):
                serialized[k] = v
            elif isinstance(v, (int, float, bool)):
                serialized[k] = v
            elif v is None:
                serialized[k] = ""
            else:
                serialized[k] = str(v)
        return serialized
    return str(item)


def serialize_traction_for_frontend(traction: Dict) -> Dict:
    """Serialize traction section specifically for frontend display."""
    if not isinstance(traction, dict):
        return {}

    result = {}
    for key, value in traction.items():
        if key in ("key_milestones",):
            if isinstance(value, list):
                result[key] = [str(v) for v in value[:5]]
            else:
                result[key] = []
        elif isinstance(value, dict):
            result[key] = serialize_metric(value.get("value", ""), key)
        else:
            result[key] = serialize_metric(value, key)
    return result


def serialize_funding_for_frontend(funding: Dict) -> Dict:
    """Serialize funding section specifically for frontend display."""
    if not isinstance(funding, dict):
        return {}

    result = {}
    for key, value in funding.items():
        if key in ("previous_rounds", "investors", "use_of_funds"):
            if isinstance(value, list):
                result[key] = [str(v) for v in value[:5]]
            elif isinstance(value, str):
                result[key] = value[:200]
            else:
                result[key] = []
        elif isinstance(value, dict):
            result[key] = serialize_metric(value.get("value", ""), key)
        else:
            result[key] = serialize_metric(value, key)
    return result


def sanitize_financial_highlights(highlights: Dict) -> Dict:
    """Ensure all financial_highlights values are strings, never dicts."""
    clean = {}
    for key, value in highlights.items():
        clean[key] = serialize_metric(value, key)
    return clean


def sanitize_chart_data(chart_data: Dict) -> Dict:
    """Ensure chart_data has valid structure with no empty/null values."""
    if not isinstance(chart_data, dict):
        return {}
    clean = {}
    for chart_key, chart_value in chart_data.items():
        if not isinstance(chart_value, dict):
            continue
        data = chart_value.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            valid_points = []
            for point in data:
                if isinstance(point, dict):
                    val = point.get("value")
                    label = point.get("label", point.get("period", ""))
                    if val is not None and label:
                        valid_points.append({
                            "label": str(label),
                            "value": float(val) if isinstance(val, (int, float)) else val,
                            "display": serialize_metric(point.get("display", "")),
                            "confidence": float(point.get("confidence", 0)),
                        })
            if valid_points:
                clean[chart_key] = {
                    "type": chart_value.get("type", ""),
                    "title": chart_value.get("title", ""),
                    "data": valid_points,
                    "display_unit": chart_value.get("display_unit", ""),
                    "calculated": {k: v for k, v in chart_value.get("calculated", {}).items() if v},
                    "chart_options": {
                        "x_axis": chart_value.get("chart_options", {}).get("x_axis", ""),
                        "y_axis": chart_value.get("chart_options", {}).get("y_axis", ""),
                        "unit": chart_value.get("chart_options", {}).get("unit", ""),
                        "color_scheme": chart_value.get("chart_options", {}).get("color_scheme", ""),
                    },
                }
    return clean


def sanitize_canonical_metrics(canonical: Dict) -> Dict:
    """Sanitize canonical metrics dict — ensure every value has proper structure."""
    if not isinstance(canonical, dict):
        return {}
    clean = {}
    for canon_name, entry in canonical.items():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value", "")
        if not value:
            continue
        clean[canon_name] = {
            "value": serialize_metric(value),
            "display_value": serialize_metric(entry.get("display_value", value)),
            "normalized_value": entry.get("normalized_value", 0),
            "currency": entry.get("currency", "INR"),
            "confidence": entry.get("confidence", 0),
            "source_type": entry.get("source_type", ""),
            "temporal_type": entry.get("temporal_type", ""),
            "ontological_type": entry.get("ontological_type", ""),
            "display_name": entry.get("display_name", canon_name.replace("_", " ").title()),
            "source_section": entry.get("source_section", ""),
        }
    return clean


def sanitize_data_warnings(warnings: List) -> List[str]:
    """Ensure data_warnings is always a list of strings."""
    clean = []
    for w in (warnings or []):
        if isinstance(w, str):
            clean.append(w)
        elif isinstance(w, dict):
            msg = w.get("message", w.get("text", str(w)))
            clean.append(str(msg)[:200])
        else:
            clean.append(str(w)[:200])
    return clean


def sanitize_strategy(strategy: Dict) -> Dict:
    """Ensure strategy output has expected string fields."""
    if not isinstance(strategy, dict):
        return {"next_step": "", "reasoning": "", "priority": "Low"}
    return {
        "next_step": serialize_metric(strategy.get("next_step", "")),
        "reasoning": serialize_metric(strategy.get("reasoning", "")),
        "priority": strategy.get("priority", "Low"),
    }


def sanitize_intent(intent: Any) -> Dict:
    """Ensure intent is a dict with expected fields."""
    if isinstance(intent, str):
        return {"intent": intent, "confidence": 50, "signals": []}
    if isinstance(intent, dict):
        return {
            "intent": intent.get("intent", "neutral"),
            "confidence": int(intent.get("confidence", 50)),
            "signals": intent.get("signals", []) if isinstance(intent.get("signals"), list) else [],
        }
    return {"intent": "neutral", "confidence": 50, "signals": []}
