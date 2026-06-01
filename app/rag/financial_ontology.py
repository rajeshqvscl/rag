"""
Financial Metric Ontology Classification Layer

Distinguishes between different types of financial metrics to prevent
revenue/PO/grant/funding confusion that causes extraction failures.

Metric Classes:
- revenue_actual: Earned/received revenue (invoiced, received)
- revenue_projected: Forecasted revenue (projections, targets)
- purchase_order: Confirmed orders (signed POs, bookings)
- grant_funding: Government/non-dilutive funding (grants, subsidies)
- equity_raise: Dilutive funding (seed, Series A, etc.)
- pipeline: Potential but not yet booked (pipeline, expected)
"""

from typing import Dict, List, Optional, Tuple
import re


METRIC_CLASSES = {
    "revenue_actual",
    "revenue_projected",
    "purchase_order",
    "grant_funding",
    "equity_raise",
    "pipeline",
    "valuation",
    "unit_count",
    "customer_count",
}


METRIC_PATTERNS = {
    "revenue_actual": [
        r"(?:invoiced|billed|received|earned|realized|actual)\s*(?:revenue|income|sales)?",
        r"(?:revenue|income|sales)\s*(?:invoiced|billed|received)?",
        r"(?:₹|Rs\.?|INR)\s*\d+(?:\.\d+)?\s*(?:cr|lakh|mn|bn)",
        r"(?:FY\d{2})\s*(?:revenue|income|sales).*(?:invoiced|achieved)",
        r"(?:audited|actual|real)\s*(?:revenue|figures?|numbers?)",
    ],
    "revenue_projected": [
        r"(?:projected|forecast|expected|target|estimated|anticipate).*(?:revenue|income|sales|growth)",
        r"(?:revenue|income).*(?:projected|forecast|target|expected|vision)",
        r"(?:next\s+(?:FY|year)|(?:FY|in FY)\s*\d{2}).*(?:target|projected|vision)",
        r"(?:₹|Rs\.?|INR)\s*\d+(?:\.\d+)?\s*(?:cr|lakh|mn|bn).*(?:target|projected|forecast)",
        r"(?:to\s+reach|aim\s+(?:for|to)|targeting).*(?:cr|lakh|mn|bn)",
    ],
    "purchase_order": [
        r"(?:purchase\s+order|PO|booked|order\s+book|confirmed\s+order)",
        r"(?:signed\s+(?:PO|order))",
        r"(?:order\s+(?:worth|value|value)?)",
        r"(?:received|secured)?\s*(?:PO|order).*(?:worth|value)?",
        r"(?:₹|Rs\.?|INR)\s*\d+(?:\.\d+)?\s*(?:cr|lakh).*(?:PO|order)",
        r"(?:order\s+book|booked).*(?:worth|value)?",
    ],
    "grant_funding": [
        r"(?:grant|subsidy|non-dilutive|government\s+(?:grant|funding|subsidy))",
        r"(?:diyat|DIAT|BEL|DRDO|defence\s+research).*grant",
        r"(?:seed\s+grant|tech\s+grant|defence\s+grant)",
        r"(?:sanctioned|approved|awarded).*(?:grant|subsidy)",
        r"(?:₹|Rs\.?|INR)\s*\d+(?:\.\d+)?\s*(?:cr|lakh).*grant",
    ],
    "equity_raise": [
        r"(?:seed\s+(?:round|funding)|Series\s+[A-Z]|Funding\s+Round)",
        r"(?:raising|raised|investment|equity\s+funding)",
        r"(?:pre-money|post-money|valuation).*(?:seed|round|Series)",
        r"(?:lead\s+investor|investor|capital)",
    ],
    "pipeline": [
        r"(?:pipeline|potential|expected|under\s+development)",
        r"(?:proposal|bid|opportunity|whitelist)",
        r"(?:discussions?|negotiation|evaluation)",
        r"(?:worth|value).*(?:pipeline|crore|cr)",
        r"(?:expected|estimated).*(?:PO|order|revenue|invoicing)",
    ],
}


CONTEXT_INDICATORS = {
    "positive": [
        "invoiced", "received", "booked", "signed", "secured", "won",
        "confirmed", "awarded", "sanctioned", "completed", "delivered",
        "under execution", "deployed", "operational"
    ],
    "future": [
        "projected", "forecast", "expected", "target", "vision",
        "aiming", "targeting", "to reach", "potential", "pipeline",
        "under development", "proposal", "bid", "discussion"
    ],
    "uncertain": [
        "may", "might", "could", "possibly", "tentative", "estimate",
        "approximate", "up to", "as of", "截至"
    ]
}


def classify_metric(text: str, value: str, context: str = "") -> Tuple[str, float]:
    """
    Classify a financial metric into its proper category.

    Returns:
        (metric_class, confidence)
    """
    text_lower = text.lower()
    value_str = str(value).lower()
    context_lower = (context or "").lower()

    combined = f"{text_lower} {value_str} {context_lower}"

    scores = {}

    for metric_class, patterns in METRIC_PATTERNS.items():
        score = 0
        for pattern in patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                score += 1

        context_modifier = 1.0

        if metric_class in ("revenue_actual", "purchase_order"):
            for indicator in CONTEXT_INDICATORS["positive"]:
                if indicator in context_lower:
                    context_modifier *= 1.5
            for indicator in CONTEXT_INDICATORS["future"] + CONTEXT_INDICATORS["uncertain"]:
                if indicator in context_lower:
                    context_modifier *= 0.5

        elif metric_class in ("revenue_projected", "pipeline"):
            for indicator in CONTEXT_INDICATORS["future"]:
                if indicator in context_lower:
                    context_modifier *= 1.5
            for indicator in CONTEXT_INDICATORS["positive"]:
                if indicator in context_lower:
                    context_modifier *= 0.7

        elif metric_class == "grant_funding":
            if "grant" in combined or "subsidy" in combined or "diyat" in combined:
                score += 2

        scores[metric_class] = score * context_modifier

    best_class = max(scores, key=scores.get)
    best_score = scores[best_class]

    confidence = min(best_score / 3.0, 1.0) if best_score > 0 else 0.3

    return best_class, confidence


def normalize_metric_value(value: str) -> Dict:
    """
    Normalize a metric value with proper unit detection and classification.

    Returns:
        {
            "raw": str,
            "normalized": float,
            "unit": str,
            "currency": str,
            "period": str
        }
    """
    from app.rag.number_utils import parse_indian_number, detect_unit

    normalized = parse_indian_number(value)
    unit = detect_unit(value) or "unknown"

    currency = "INR"
    if "₹" in value or "Rs" in value or "INR" in value:
        currency = "INR"
    elif "$" in value or "USD" in value:
        currency = "USD"

    period = ""
    fy_match = re.search(r"FY(\d{2,4})", value, re.IGNORECASE)
    if fy_match:
        period = f"FY{fy_match.group(1)}"

    return {
        "raw": value,
        "normalized": normalized,
        "unit": unit,
        "currency": currency,
        "period": period
    }


def extract_financial_entities(text: str) -> List[Dict]:
    """
    Extract and classify all financial entities from text.

    Returns:
        List of {
            "text": str,
            "value": str,
            "metric_class": str,
            "confidence": float,
            "context": str,
            "normalized": dict
        }
    """
    import re

    financial_pattern = r"(?:(?:₹|Rs\.?|INR|\$|USD)\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:cr|lakh|lakhs?|mn|million|bn|billion|k|thousand)?"
    matches = re.finditer(financial_pattern, text, re.IGNORECASE)

    entities = []
    for match in matches:
        value_str = match.group(0)
        numeric_val = match.group(1)

        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = text[start:end]

        metric_class, confidence = classify_metric(value_str, numeric_val, context)

        normalized = normalize_metric_value(value_str)

        entities.append({
            "text": value_str,
            "value": numeric_val,
            "metric_class": metric_class,
            "confidence": confidence,
            "context": context.strip(),
            "normalized": normalized
        })

    return entities


def build_canonical_metrics(entities: List[Dict]) -> Dict[str, Dict]:
    """
    Build canonical metric registry from extracted entities.

    Groups by metric_class and selects best evidence per type.
    """
    canonical = {}

    for entity in entities:
        mc = entity["metric_class"]
        conf = entity["confidence"]

        if mc not in canonical:
            canonical[mc] = {
                "value": entity["text"],
                "normalized_value": entity["normalized"]["normalized"],
                "confidence": conf,
                "source_context": entity["context"][:200],
                "evidence": [entity]
            }
        else:
            if conf > canonical[mc]["confidence"]:
                canonical[mc] = {
                    "value": entity["text"],
                    "normalized_value": entity["normalized"]["normalized"],
                    "confidence": conf,
                    "source_context": entity["context"][:200],
                    "evidence": [entity]
                }

    return canonical


def validate_financial_ontology(canonical: Dict, warnings: List[str]) -> Tuple[Dict, List[str]]:
    """
    Validate canonical metrics for ontological consistency.

    Returns:
        (validated_canonical, warnings)
    """
    revenue_actual = canonical.get("revenue_actual", {})
    revenue_proj = canonical.get("revenue_projected", {})
    po = canonical.get("purchase_order", {})
    pipeline = canonical.get("pipeline", {})

    if revenue_actual and revenue_proj:
        actual_val = revenue_actual.get("normalized_value", 0)
        proj_val = revenue_proj.get("normalized_value", 0)
        if proj_val > 0 and actual_val > 0 and proj_val < actual_val * 0.5:
            warnings.append("Projected revenue significantly lower than actual - check classification")

    if po and revenue_actual:
        po_val = po.get("normalized_value", 0)
        rev_val = revenue_actual.get("normalized_value", 0)
        if po_val > 0 and rev_val > 0 and po_val > rev_val * 10:
            warnings.append("PO value unusually high vs revenue - verify PO is not already counted")

    if pipeline and po:
        pipe_val = pipeline.get("normalized_value", 0)
        po_val = po.get("normalized_value", 0)
        if pipe_val > 0 and po_val > 0 and pipe_val < po_val:
            warnings.append("Pipeline less than PO - pipeline should be larger")

    return canonical, warnings