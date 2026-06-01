"""
Canonical Fact Registry — single source of truth for all extracted metrics
with temporal separation, entity-type preservation, ontological classification,
and conflict resolution.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import re


class TemporalType(str, Enum):
    HISTORICAL = "historical"
    CURRENT = "current"
    PROJECTION = "projection"
    TARGET = "target"
    PIPELINE = "pipeline"
    FUNDRAISING = "fundraising"
    GRANT = "grant"
    UNKNOWN = "unknown"


class UnitType(str, Enum):
    CURRENCY = "currency"
    JOBS = "jobs"
    PERCENTAGE = "percentage"
    COUNT = "count"
    RATIO = "ratio"
    UNKNOWN = "unknown"


@dataclass
class CanonicalMetric:
    canonical_name: str
    display_name: str
    value_str: str
    raw_value: float = 0.0
    normalized_value: float = 0.0  # Always numeric INR (e.g. 8900000 for ₹89L)
    display_value: str = ""  # Human-readable formatted value (e.g. "₹89 Lakhs")
    currency: str = "INR"  # INR, USD, or empty for non-currency
    unit_type: UnitType = UnitType.UNKNOWN
    temporal_type: TemporalType = TemporalType.UNKNOWN
    ontological_type: str = "unknown"
    confidence: float = 0.5
    source_section: str = ""
    source_field: str = ""
    entity_type: Optional[str] = None
    source_page: Optional[int] = None
    source_type: str = "inferred"  # explicit, inferred, visual_parsed, chart_inferred, narrative_inferred
    fiscal_year: Optional[str] = None
    fy_label: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# Time-type values the LLM can emit that signal ontological type (not temporal)
_ONTOLOGICAL_TIME_TYPES = {
    "contract": "purchase_order_value",
    "grant": "government_grants",
}

# Value-string patterns that reveal ontological type
_ONTOLOGY_VALUE_PATTERNS = [
    (re.compile(r'invoiced', re.IGNORECASE), 'invoiced_amount'),
    (re.compile(r'purchase\s*order|po\b', re.IGNORECASE), 'purchase_order_value'),
    (re.compile(r'grant|subsidy|disburs', re.IGNORECASE), 'government_grants'),
    (re.compile(r'realized|booked', re.IGNORECASE), 'realized_revenue'),
    (re.compile(r'expected.*(?:po|order|procurement|unit)', re.IGNORECASE), 'expected_booking'),
    (re.compile(r'booking', re.IGNORECASE), 'expected_booking'),
    # Defence-tech specific patterns
    (re.compile(r'amc|annual\s*maintenance', re.IGNORECASE), 'amc_revenue'),
    (re.compile(r'oem|original\s*equipment', re.IGNORECASE), 'oem_revenue'),
    (re.compile(r'tender|bid\s*value', re.IGNORECASE), 'tender_value'),
    (re.compile(r'export\s*potential', re.IGNORECASE), 'export_revenue'),
    (re.compile(r'procurement\s*value', re.IGNORECASE), 'procurement_value'),
    (re.compile(r'contract\s*value', re.IGNORECASE), 'contract_value'),
    (re.compile(r'defence\s*market|defense\s*market', re.IGNORECASE), 'defence_market'),
]

METRIC_DEFS: Dict[str, dict] = {
    "traction.revenue": {
        "display": "Total Revenue Since Launch",
        "canonical_name": "total_revenue",
        "temporal_overrides": {
            "historical": "historical_revenue",
            "current": "total_revenue",
            "projection": "projected_revenue",
        },
        "ontological_overrides": {
            "purchase_order_value": {"name": "purchase_order_value", "display": "Purchase Order Value"},
            "government_grants": {"name": "government_grants", "display": "Government Grants"},
            "invoiced_amount": {"name": "invoiced_amount", "display": "Invoiced Amount"},
            "expected_booking": {"name": "expected_booking", "display": "Expected Booking"},
            "amc_revenue": {"name": "amc_revenue", "display": "AMC Revenue"},
            "oem_revenue": {"name": "oem_revenue", "display": "OEM Revenue"},
        },
        "default_temp": TemporalType.CURRENT,
        "unit_type": UnitType.CURRENCY,
    },
    "revenue_details.current_revenue": {
        "display": "Current Period Revenue",
        "canonical_name": "current_period_revenue",
        "temporal_overrides": {
            "historical": "historical_period_revenue",
            "current": "current_period_revenue",
            "projection": "projected_period_revenue",
        },
        "ontological_overrides": {
            "purchase_order_value": {"name": "period_purchase_order_value", "display": "Period PO Value"},
            "invoiced_amount": {"name": "period_invoiced_amount", "display": "Period Invoiced Amount"},
            "amc_revenue": {"name": "period_amc_revenue", "display": "Period AMC Revenue"},
            "grant_revenue": {"name": "grant_revenue", "display": "Grant Revenue"},
        },
        "default_temp": TemporalType.CURRENT,
        "unit_type": UnitType.CURRENCY,
    },
    "traction.orders": {
        "display": "Orders",
        "canonical_name": "orders",
        "temporal_overrides": {
            "projection": "expected_units",
            "pipeline": "expected_units",
        },
        "ontological_overrides": {
            "expected_units": {"name": "expected_units", "display": "Expected Units"},
        },
        "unit_type": UnitType.COUNT,
    },
    "traction.customers": {
        "display": "Customers",
        "canonical_name": "customers",
        "unit_type": UnitType.COUNT,
    },
    "pipeline.pipeline_value": {
        "display": "Pipeline Value",
        "canonical_name": "pipeline_value",
        "default_temp": TemporalType.PIPELINE,
        "unit_type": UnitType.CURRENCY,
    },
    "pipeline.expected_po": {
        "display": "Expected Purchase Order",
        "canonical_name": "expected_po",
        "default_temp": TemporalType.PIPELINE,
        "unit_type": UnitType.CURRENCY,
        "ontological_overrides": {
            "purchase_order_value": {"name": "purchase_order_value", "display": "Purchase Order Value"},
        },
    },
    "funding.current_raise": {
        "display": "Current Raise",
        "canonical_name": "funding_raise",
        "default_temp": TemporalType.FUNDRAISING,
        "unit_type": UnitType.CURRENCY,
    },
    "funding.valuation": {
        "display": "Valuation",
        "canonical_name": "valuation",
        "default_temp": TemporalType.CURRENT,
        "unit_type": UnitType.CURRENCY,
    },
    "funding.government_grants": {
        "display": "Government Grants",
        "canonical_name": "government_grants",
        "default_temp": TemporalType.GRANT,
        "unit_type": UnitType.CURRENCY,
    },
    "industry_overview.tam": {
        "display": "TAM",
        "canonical_name": "tam",
        "unit_type": UnitType.CURRENCY,
    },
    "industry_overview.sam": {
        "display": "SAM",
        "canonical_name": "sam",
        "unit_type": UnitType.CURRENCY,
    },
    "industry_overview.som": {
        "display": "SOM",
        "canonical_name": "som",
        "unit_type": UnitType.CURRENCY,
    },
}

_CUMULATIVE_PATTERNS = re.compile(
    r'(till|since|as of|cumulative|ytd|run.?rate|annualized)', re.IGNORECASE
)
_PERIOD_PATTERNS = re.compile(
    r'\b(Q[1-4]|H[12]|monthly|quarterly|annual)\b', re.IGNORECASE
)


def _detect_unit_type(value_str: str) -> UnitType:
    if not value_str:
        return UnitType.UNKNOWN
    v = value_str.lower()
    if any(x in v for x in ["\u20b9", "$", "rs", "inr", "usd", "cr", "crore", "lakh", "mn", "million", "bn", "billion"]):
        return UnitType.CURRENCY
    if "%" in v or "percent" in v:
        return UnitType.PERCENTAGE
    if any(x in v for x in ["job", "employee", "headcount", "fte"]):
        return UnitType.JOBS
    return UnitType.UNKNOWN


def _infer_entity_type(field: str, value_str: str) -> Optional[str]:
    if not value_str or field != "customers":
        return None
    match = re.search(r'\d+[\+,]?\s*(.+)', value_str)
    if match:
        entity = match.group(1).strip().rstrip(".)")
        if entity and len(entity) < 60 and not re.match(r'^[\(\d]', entity):
            return entity
    return None


def _parse_raw_value(value_str: str) -> float:
    """Safely parse raw value to float with crash protection."""
    if not value_str:
        return 0.0
    try:
        from app.rag.number_utils import parse_indian_number, safe_float
        return parse_indian_number(value_str)
    except Exception:
        try:
            from app.rag.number_utils import safe_float
            nums = re.findall(r'[\d,]+\.?\d*', value_str.replace(",", ""))
            if nums:
                return safe_float(nums[0].replace(",", ""), 0.0)
        except Exception:
            pass
    return 0.0


def _detect_currency(value_str: str) -> str:
    """Detect currency from value string."""
    if not value_str:
        return "INR"
    v = value_str
    if '$' in v or 'usd' in v.lower():
        return "USD"
    if '€' in v or 'eur' in v.lower():
        return "EUR"
    if '£' in v or 'gbp' in v.lower():
        return "GBP"
    return "INR"


def _normalize_to_inr(value_str: str) -> tuple:
    """Convert value string to normalized INR numeric value + detected currency.
    Returns (normalized_value, currency).
    parse_indian_number already returns fully normalized INR.
    E.g., '₹89 Lakhs' → (8900000, 'INR'), '$150B' → (12450000000000.0, 'USD').
    """
    raw = _parse_raw_value(value_str)
    currency = _detect_currency(value_str)
    if raw == 0.0:
        return (0.0, currency)
    vlow = value_str.lower()
    # USD→INR conversion (approximate)
    if '$' in value_str or 'usd' in vlow:
        return (raw * 83.0, currency)
    if '€' in value_str or 'eur' in vlow:
        return (raw * 90.0, currency)
    # Already in INR — parse_indian_number handles the normalization
    return (raw, currency)


def _format_display_value(value_str: str, currency: str) -> str:
    """Format a human-readable display value from the raw string."""
    if not value_str:
        return ""
    v = value_str.strip()
    if currency == "INR" and '₹' not in v and not v.startswith('INR'):
        v = f"₹{v}" if v[0].isdigit() else v
    return v


def _infer_source_type(section: str, field: str) -> str:
    """Infer source_type from section/field context."""
    explicit_fields = {"tam", "sam", "som", "revenue", "current_revenue",
                       "orders", "customers", "current_raise", "valuation"}
    if field in explicit_fields:
        return "explicit"
    if section in ("additional_metrics",):
        return "inferred"
    if field.startswith("projection") or field == "projections":
        return "inferred"
    return "inferred"


def _classify_ontological_type(value_str: str, time_type_str: str, field: str) -> str:
    """Classify a metric's ontological type using time_type, value context, and field."""
    # 1. Time-type from LLM (most authoritative)
    if time_type_str:
        tt = time_type_str.lower().strip()
        mapped = _ONTOLOGICAL_TIME_TYPES.get(tt)
        if mapped:
            return mapped

    # 2. Value-string patterns
    if value_str:
        v = value_str.lower()
        for pattern, otype in _ONTOLOGY_VALUE_PATTERNS:
            if pattern.search(v):
                return otype

    # 3. Field-specific defaults
    if field in ("pipeline_value",):
        return "pipeline_value"
    if field in ("pipeline", "lois"):
        return "pipeline_value"
    if field in ("current_raise",):
        return "funding_ask"

    return "unknown"


def _get_temporal_type(field: str, time_type_value: str, value_str: str) -> TemporalType:
    if time_type_value:
        t = time_type_value.lower().strip()
        for tt in TemporalType:
            if tt.value == t:
                return tt

    if not value_str:
        return TemporalType.UNKNOWN

    v = value_str.lower()
    if _CUMULATIVE_PATTERNS.search(v):
        return TemporalType.CURRENT
    if "projected" in v or "expected" in v or "forecast" in v:
        return TemporalType.PROJECTION
    if "target" in v or "goal" in v:
        return TemporalType.TARGET
    if "pipeline" in v or "letter of intent" in v:
        return TemporalType.PIPELINE
    return TemporalType.UNKNOWN


def _resolve_canonical_name(metric_def: dict, temporal_type: TemporalType,
                            ontological_type: str) -> Tuple[str, str]:
    """Resolve canonical name and display name using temporal + ontological overrides."""
    name = metric_def.get("canonical_name", "")
    display = metric_def.get("display", name.replace("_", " ").title())

    # Ontological overrides take precedence
    onto_overrides = metric_def.get("ontological_overrides", {})
    if ontological_type in onto_overrides:
        override = onto_overrides[ontological_type]
        return override.get("name", name), override.get("display", display)

    # Temporal overrides
    temp_overrides = metric_def.get("temporal_overrides", {})
    tkey = temporal_type.value if temporal_type else ""
    if tkey in temp_overrides:
        override_name = temp_overrides[tkey]
        return override_name, override_name.replace("_", " ").title()

    return name, display


def _extract_fy_label(value_str: str) -> Optional[str]:
    if not value_str:
        return None
    match = re.search(r'FY\d{2}-\d{2}', value_str)
    return match.group(0) if match else None


class CanonicalFactRegistry:

    def __init__(self):
        self._metrics: Dict[str, List[CanonicalMetric]] = {}
        self._resolved: Dict[str, CanonicalMetric] = {}

    def add(self, metric: CanonicalMetric) -> None:
        if metric.canonical_name not in self._metrics:
            self._metrics[metric.canonical_name] = []
        self._metrics[metric.canonical_name].append(metric)

    def resolve(self) -> Dict[str, CanonicalMetric]:
        self._resolved = {}
        for name, candidates in self._metrics.items():
            if not candidates:
                continue
            _TEMPORAL_ORDER = {
                TemporalType.CURRENT: 4,
                TemporalType.PROJECTION: 3,
                TemporalType.TARGET: 3,
                TemporalType.FUNDRAISING: 3,
                TemporalType.HISTORICAL: 2,
                TemporalType.PIPELINE: 2,
                TemporalType.UNKNOWN: 0,
            }
            def _sort_key(m: CanonicalMetric) -> Tuple:
                return (
                    m.confidence,
                    _TEMPORAL_ORDER.get(m.temporal_type, 0),
                    len(m.value_str) if m.value_str else 0,
                )
            candidates.sort(key=_sort_key, reverse=True)
            self._resolved[name] = candidates[0]
        return self._resolved

    def get(self, canonical_name: str) -> Optional[CanonicalMetric]:
        return self._resolved.get(canonical_name)

    def all(self) -> Dict[str, CanonicalMetric]:
        return dict(self._resolved)

    def to_dict(self) -> dict:
        def _val(m):
            if m and m.value_str:
                v = m.value_str
                if m.entity_type:
                    nums = re.match(r'([\d,+]+)', v)
                    if nums:
                        v = f"{nums.group(1)} {m.entity_type}"
                return v
            return ""
        return {
            m.canonical_name: {
                "value": _val(m),
                "raw_value": m.raw_value,
                "normalized_value": m.normalized_value,
                "display_value": m.display_value or _val(m),
                "currency": m.currency,
                "temporal_type": m.temporal_type.value if m.temporal_type else "unknown",
                "unit_type": m.unit_type.value if m.unit_type else "unknown",
                "ontological_type": m.ontological_type,
                "confidence": m.confidence,
                "source_type": m.source_type,
                "fiscal_year": m.fiscal_year,
                "entity_type": m.entity_type,
                "display_name": m.display_name,
                "source_section": m.source_section,
            }
            for m in self._resolved.values()
        }

    def get_by_ontology(self, ontological_type: str) -> List[CanonicalMetric]:
        """Get all metrics matching an ontological type."""
        return [m for m in self._resolved.values() if m.ontological_type == ontological_type]


def build_canonical_registry(structured_data: dict) -> CanonicalFactRegistry:
    registry = CanonicalFactRegistry()

    tr = structured_data.get("traction", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}

    time_types = {
        "traction.revenue": tr.get("revenue_time_type", ""),
        "traction.orders": tr.get("orders_time_type", ""),
        "traction.customers": tr.get("customers_time_type", ""),
        "revenue_details.current_revenue": rd.get("current_revenue_time_type", ""),
    }

    for section_key, section in structured_data.items():
        if not isinstance(section, dict) or section_key.startswith("_"):
            continue
        for field_key, field_value in section.items():
            if not field_value or field_value in ("", [], {}):
                continue
            if isinstance(field_value, list):
                continue

            full_key = f"{section_key}.{field_key}"
            metric_def = METRIC_DEFS.get(full_key)
            if not metric_def:
                continue

            vstr = str(field_value)
            tt_str = time_types.get(full_key, "")

            ontological_type = _classify_ontological_type(vstr, tt_str, field_key)
            temporal_type = _get_temporal_type(full_key, tt_str, vstr)
            if temporal_type == TemporalType.UNKNOWN:
                temporal_type = metric_def.get("default_temp", TemporalType.UNKNOWN)

            canonical_name, display_name = _resolve_canonical_name(
                metric_def, temporal_type, ontological_type
            )
            raw_value = _parse_raw_value(vstr)
            unit_type = metric_def.get("unit_type", UnitType.UNKNOWN)
            if unit_type == UnitType.UNKNOWN:
                unit_type = _detect_unit_type(vstr)
            entity_type = _infer_entity_type(field_key, vstr)
            norm_val, currency = _normalize_to_inr(vstr)

            registry.add(CanonicalMetric(
                canonical_name=canonical_name,
                display_name=display_name,
                value_str=vstr,
                raw_value=raw_value,
                normalized_value=norm_val,
                display_value=_format_display_value(vstr, currency),
                currency=currency,
                unit_type=unit_type,
                temporal_type=temporal_type,
                ontological_type=ontological_type,
                confidence=0.7,
                source_section=section_key,
                source_field=field_key,
                entity_type=entity_type,
                source_type=_infer_source_type(section_key, field_key),
                fy_label=_extract_fy_label(vstr),
            ))

    # --- Revenue projections (with ontological classification) ---
    if rd and isinstance(rd.get("projections"), list):
        for i, proj in enumerate(rd["projections"]):
            if isinstance(proj, dict):
                period = proj.get("period", f"period_{i+1}")
                value = proj.get("value", "")
                if value:
                    vstr = str(value)
                    ot = _classify_ontological_type(vstr, "", "projections")
                    pname = f"projected_revenue_{i+1}"
                    disp = f"Projected Revenue ({period})"
                    if ot == "expected_booking":
                        pname = f"projected_booking_{i+1}"
                        disp = f"Projected Booking ({period})"
                    elif ot == "purchase_order_value":
                        pname = f"projected_po_{i+1}"
                        disp = f"Projected PO ({period})"
                    proj_norm_val, proj_currency = _normalize_to_inr(vstr)
                    registry.add(CanonicalMetric(
                        canonical_name=pname,
                        display_name=disp,
                        value_str=vstr,
                        raw_value=_parse_raw_value(vstr),
                        normalized_value=proj_norm_val,
                        display_value=_format_display_value(vstr, proj_currency),
                        currency=proj_currency,
                        unit_type=UnitType.CURRENCY,
                        temporal_type=TemporalType.PROJECTION,
                        ontological_type=ot,
                        confidence=0.6,
                        source_section="revenue_details",
                        source_field=f"projections[{i}]",
                        source_type="inferred",
                        fy_label=_extract_fy_label(vstr),
                        metadata={"period": period},
                    ))

    # --- Additional metrics ---
    additional = structured_data.get("additional_metrics", [])
    if isinstance(additional, list):
        for am in additional:
            if isinstance(am, dict):
                key = am.get("key", "")
                val = am.get("value", "")
                ctx = am.get("context", "")
                if key and val:
                    key_lower = key.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
                    cname = key_lower
                    tt = TemporalType.UNKNOWN
                    ot = "unknown"
                    disp = key.title()
                    if any(x in key_lower for x in ["arr", "run_rate", "annualized", "annual_run"]):
                        cname = "arr_run_rate"
                        tt = TemporalType.CURRENT
                        ot = "arr_run_rate"
                        disp = "ARR Run Rate"
                    elif any(x in key_lower for x in ["q1_revenue", "q2_revenue", "quarter_revenue"]):
                        tt = TemporalType.HISTORICAL
                    vstr = str(val)
                    addl_norm_val, addl_currency = _normalize_to_inr(vstr)
                    registry.add(CanonicalMetric(
                        canonical_name=cname,
                        display_name=disp,
                        value_str=vstr,
                        raw_value=_parse_raw_value(vstr),
                        normalized_value=addl_norm_val,
                        display_value=_format_display_value(vstr, addl_currency),
                        currency=addl_currency,
                        unit_type=_detect_unit_type(vstr),
                        temporal_type=tt,
                        ontological_type=ot,
                        confidence=0.5,
                        source_section="additional_metrics",
                        source_field=key,
                        source_type="inferred",
                        fy_label=_extract_fy_label(vstr),
                        metadata={"context": ctx} if ctx else None,
                    ))

    registry.resolve()
    return registry
