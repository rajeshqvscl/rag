"""
Typed metric value system.
Every extracted financial/numeric value carries type, unit, temporal, and confidence metadata.
"""
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class MetricType(Enum):
    CURRENT_REVENUE = "current_revenue"
    ARR = "arr"
    PROJECTED_REVENUE = "projected_revenue"
    PIPELINE = "pipeline"
    EXPECTED_PO = "expected_po"
    INVOICED_REVENUE = "invoiced_revenue"
    GRANT = "grant"
    FUNDRAISE = "fundraise"
    PRE_MONEY_VALUATION = "pre_money_valuation"
    POST_MONEY_VALUATION = "post_money_valuation"
    CUSTOMER_COUNT = "customer_count"
    ORDER_COUNT = "order_count"
    MARKET_VOLUME = "market_volume"
    MARKET_REVENUE = "market_revenue"
    GROSS_MARGIN = "gross_margin"
    GROWTH_RATE = "growth_rate"
    UNIT_COUNT = "unit_count"
    CONTRACT_VALUE = "contract_value"
    PROJECTION = "projection"
    PROJECT_VALUE = "project_value"
    UNKNOWN = "unknown"


class TemporalType(Enum):
    HISTORICAL = "historical"
    CURRENT = "current"
    PROJECTION = "projection"
    TARGET = "target"
    PIPELINE = "pipeline"
    FUNDRAISING = "fundraising"
    UNKNOWN = "unknown"


TEMPORAL_KEYWORD_MAP = [
    (r'\bFY\d{2,4}\b|\b20\d{2}\b', TemporalType.HISTORICAL),
    (r'\bcurrent\b|\bpresent\b|\bongoing\b|\bthis\s+(year|fy|quarter|q)\b', TemporalType.CURRENT),
    (r'\bproject(?:ion|ed|ing)?\b|\bforecast\b|\btarget\b|\bplan\b|\baim\b|\bexpect(?:ed|ing)?\b', TemporalType.PROJECTION),
    (r'\bfuture\b|\bnext\b|\bupcoming\b|\bby\s+20\d{2}\b', TemporalType.PROJECTION),
    (r'\bpipeline\b|\bpotential\b|\bprospect\b|\bletter of intent\b|\bloi\b|\bpo\b|\bpurchase order\b', TemporalType.PIPELINE),
    (r'\brais(?:e|ing|ed)\b|\bfund(?:raise|ing)?\b|\bround\b|\bseries\s+[a-z]\b', TemporalType.FUNDRAISING),
]


def infer_temporal_type(value_str: str, context: str = "") -> TemporalType:
    ctx = (str(value_str) + " " + str(context)).lower()
    for pattern, ttype in TEMPORAL_KEYWORD_MAP:
        if re.search(pattern, ctx):
            return ttype
    return TemporalType.UNKNOWN


class UnitType(Enum):
    CURRENCY = "currency"
    JOBS = "jobs"
    PERCENTAGE = "percentage"
    COUNT = "count"
    RATIO = "ratio"
    UNKNOWN = "unknown"


@dataclass
class MetricValue:
    raw: str
    normalized: float = 0.0
    metric_type: MetricType = MetricType.UNKNOWN
    temporal_type: TemporalType = TemporalType.UNKNOWN
    unit_type: UnitType = UnitType.UNKNOWN
    unit: str = ""
    currency: str = ""
    confidence: float = 0.0
    source_page: int = 0
    source_text: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "metric_type": self.metric_type.value,
            "temporal_type": self.temporal_type.value,
            "unit_type": self.unit_type.value,
            "unit": self.unit,
            "currency": self.currency,
            "confidence": self.confidence,
            "source_page": self.source_page,
            "source_text": self.source_text[:200] if self.source_text else "",
        }


def metric_value_from_raw(raw: str, metric_type: MetricType = MetricType.UNKNOWN,
                          context: str = "", page: int = 0) -> MetricValue:
    from app.rag.number_utils import parse_any_number, detect_unit, classify_unit_type as classify_ut

    num = parse_any_number(raw)
    unit = detect_unit(raw) or ""
    unit_type = classify_ut(raw, context)
    temporal = infer_temporal_type(raw, context)

    currency = ""
    lower = raw.lower()
    if "₹" in lower or "inr" in lower:
        currency = "INR"
    elif "$" in lower or "usd" in lower:
        currency = "USD"
    elif "€" in lower or "eur" in lower:
        currency = "EUR"

    return MetricValue(
        raw=raw,
        normalized=num,
        metric_type=metric_type,
        temporal_type=temporal,
        unit_type=unit_type,
        unit=unit,
        currency=currency,
        source_page=page,
        source_text=context,
        confidence=_compute_base_confidence(raw, unit_type),
    )


def _compute_base_confidence(raw: str, unit_type: UnitType) -> float:
    s = str(raw)
    score = 0.5
    if re.search(r'[₹$€£]', s):
        score = 0.95
    elif re.search(r'(?:Cr|Lakh|L|Mn|Bn|Million|Billion|Thousand|K)\b', s, re.IGNORECASE):
        score = 0.85
    elif re.search(r'\d+', s):
        score = 0.7
    if re.search(r'FY\d{2}-\d{2}', s):
        score = min(score + 0.1, 1.0)
    elif re.search(r'FY\d{2,4}', s, re.IGNORECASE):
        score = min(score + 0.05, 1.0)
    return round(score, 2)
