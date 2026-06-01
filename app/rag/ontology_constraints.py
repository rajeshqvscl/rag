"""
Ontology Hard Constraints — type validators, unit normalization, and reject layer
for preventing invalid metric assignments before they enter the canonical registry.

Phase 4 / Phase B of the accuracy improvement plan.

Full ontology classification:
  earned_revenue       - realized/invoiced revenue from operations
  projected_revenue    - forecast/projected revenue
  arr_run_rate         - annualized recurring revenue
  pipeline             - future deals, expected contracts
  expected_po          - purchase order value (expected, not invoiced)
  contract_value       - signed contract value
  grant                - government/non-dilutive funding
  valuation            - company valuation
  raise_amount         - funding raise
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ConstraintViolation:
    field: str
    message: str
    severity: str  # "error", "warning"
    value: str = ""


# ── Ontology Classifier ──────────────────────────────────────────────────

_ONTOLOGY_SIGNATURES: List[tuple] = [
    # (regex pattern, ontological_type, priority)
    (re.compile(r'invoiced|billed|received|realized|earned|collected', re.IGNORECASE), "earned_revenue", 90),
    (re.compile(r'arr\b|annual.?recurring.?revenue|run.?rate', re.IGNORECASE), "arr_run_rate", 85),
    (re.compile(r'grant|subsidy|disburs|government.*fund', re.IGNORECASE), "grant", 80),
    (re.compile(r'purchase.?order|po\s*(value|expected|worth)', re.IGNORECASE), "expected_po", 75),
    (re.compile(r'contract.*(?:value|worth|signed)', re.IGNORECASE), "contract_value", 70),
    (re.compile(r'pipeline|expected.*(?:booking|order|unit)', re.IGNORECASE), "pipeline", 65),
    (re.compile(r'projected|forecast|projection|estimated', re.IGNORECASE), "projected_revenue", 60),
    (re.compile(r'valuation|pre.?money|post.?money', re.IGNORECASE), "valuation", 55),
    (re.compile(r'raising|fundraise|current.*raise|series.*[a-z]', re.IGNORECASE), "raise_amount", 50),
]


_CONTEXT_SIGNATURES = [
    # (context_window_pattern, field_signal, weight)
    (r'(?i)(?:actual|audited|historical|past\s+\w+)\s+\w{0,20}(?:revenue|income|sales)', "earned_revenue", 95),
    (r'(?i)(?:fy|fiscal|year|quarter|q[1-4])\s*\d{2}', "earned_revenue", 60),
    (r'(?i)(?:mrr|arr|monthly|annual)\s*(?:recurring|run.?rate)', "arr_run_rate", 90),
    (r'(?i)(?:expected|upcoming|pipeline|future)\s+(?:revenue|order|po|contract)', "pipeline", 80),
    (r'(?i)(?:subsidy|grant|non.?dilutive|government.*fund)', "grant", 85),
    (r'(?i)(?:valuation|pre.?money|post.?money|exit)', "valuation", 80),
    (r'(?i)(?:series\s*[a-z]|seed|fundraise|closing.*round)', "raise_amount", 75),
    (r'(?i)(?:purchase\s*order|po\s*value|expected\s*po)', "expected_po", 80),
    (r'(?i)(?:contract\s*(?:value|signed|worth))', "contract_value", 75),
    (r'(?i)(?:projected|forecast|target|projection)\s*\w{0,20}(?:revenue|income)', "projected_revenue", 80),
    (r'(?i)(?:booking|order|po\b|purchase).{0,30}(?:unit|qty|quantity|number)', "pipeline", 60),
    (r'(?i)(?:revenue|income|sales).{0,30}(?:cr|lakh|mn|million|billion|\$|₹|€|£)', "earned_revenue", 70),
]


def classify_ontology(value_str: str, time_type_str: str = "", field: str = "",
                      context_window: str = "") -> str:
    """
    Classify a metric into its ontological type.
    Priority-based matching using time_type, field, regex signatures, and context window.
    Returns one of the ontology class strings or 'unknown'.
    """
    if not value_str and not time_type_str and not context_window:
        return "unknown"

    v = (value_str or "").lower()
    t = (time_type_str or "").lower()
    f = field.lower()
    ctx = (context_window or "").lower()

    # ── Strongest: time_type from LLM ──
    if "booked" in t or "contracted" in t:
        return "expected_po"
    if "grant" in t:
        return "grant"
    if "pipeline" in t:
        return "pipeline"
    if "arr" in t or "run-rate" in t:
        return "arr_run_rate"
    if "projected" in t or "projection" in t:
        return "projected_revenue"
    if "target" in t:
        return "projected_revenue"
    if "historical" in t:
        return "earned_revenue"

    # ── Field-based inference ──
    if f == "valuation":
        return "valuation"
    if f in ("current_raise",):
        return "raise_amount"
    if f in ("pipeline_value", "lois"):
        return "pipeline"
    if f in ("orders",):
        # Need more context to classify orders ontology
        pass

    # ── Context window signatures (most reliable) ──
    combined_ctx = f"{ctx} {v}"
    best_type = "unknown"
    best_priority = 0
    for pattern, otype, priority in _CONTEXT_SIGNATURES:
        if re.search(pattern, combined_ctx):
            if priority > best_priority:
                best_priority = priority
                best_type = otype

    # ── Full-text signature matching (fallback) ──
    if best_type == "unknown":
        for pattern, otype, priority in _ONTOLOGY_SIGNATURES:
            if pattern.search(v):
                if priority > best_priority:
                    best_priority = priority
                    best_type = otype

    # ── Default by keywords in value string ──
    if best_type == "unknown":
        has_financial_unit = bool(re.search(r'(?:cr|lakh|mn|million|billion|\$|₹|€|£|inr|usd)', v))
        has_count_unit = bool(re.search(r'(?:unit|customer|seat|user|employee|head)', v))

        if has_financial_unit and any(x in v for x in ["revenue", "income", "sales", "turnover"]):
            if any(x in v for x in ["expected", "projected", "forecast", "target"]):
                return "projected_revenue"
            return "earned_revenue"
        if has_financial_unit and any(x in v for x in ["raising", "fund", "investment", "series"]):
            return "raise_amount"
        if has_count_unit:
            return "pipeline"

    return best_type


# ── Constraint definitions per canonical metric field ──────────────────────

_REVENUE_CONSTRAINTS = {
    "must_have_currency": r'[\$₹€£]|inr|usd|eur|gbp|rs\.?',
    "must_have_number": r'\d+',
    "must_not_have": r'climate|mitigation|trend|employee|headcount|job|farmer|loss|shortage|vacancy|gdp|deficit|national|unemployment|productivity',
    "min_length": 3,
}

_MARKET_CONSTRAINTS = {
    "must_have_number": r'\d+',
    "must_not_have": r'climate|mitigation|trend|employee|headcount|job|farmer|user|customer|loss|shortage|vacancy|deficit|national|unemployment|productivity',
    "min_length": 3,
}

_ORDERS_CONSTRAINTS = {
    "must_have": r'order|booking|unit|po\b|purchase|contract|expected|deliver',
    "must_have_number": r'\d+',
    "must_not_have": r'climate|mitigation|trend|revenue|funding',
    "min_length": 3,
}

_FUNDING_CONSTRAINTS = {
    "must_have_currency": r'[\$₹€£]|inr|usd|eur|gbp|rs\.?',
    "must_have_number": r'\d+',
    "must_not_have": r'employee|headcount|job|farmer|market|tam|sam|som',
    "min_length": 3,
}


def _check_value(value_str: str, constraints: dict) -> List[str]:
    """Check a value string against a set of constraints. Returns violation messages."""
    violations = []
    vlow = value_str.lower()

    must_have = constraints.get("must_have")
    if must_have and not re.search(must_have, vlow, re.IGNORECASE):
        violations.append(f"must contain pattern '{must_have}'")

    must_have_currency = constraints.get("must_have_currency")
    if must_have_currency and not re.search(must_have_currency, vlow):
        violations.append(f"must contain currency indicator ({must_have_currency})")

    must_have_number = constraints.get("must_have_number")
    if must_have_number and not re.search(must_have_number, vlow):
        violations.append(f"must contain a number")

    must_not_have = constraints.get("must_not_have")
    if must_not_have and re.search(must_not_have, vlow, re.IGNORECASE):
        violations.append(f"contains prohibited terms ({must_not_have})")

    min_length = constraints.get("min_length", 0)
    if len(value_str.strip()) < min_length:
        violations.append(f"value too short (min {min_length} chars)")

    return violations


def validate_revenue(value_str: str, evidence_text: str = "") -> List[ConstraintViolation]:
    """Revenue must have currency + number, must not be a non-revenue concept."""
    violations = []
    for msg in _check_value(value_str, _REVENUE_CONSTRAINTS):
        violations.append(ConstraintViolation(
            field="revenue", message=msg, severity="error", value=value_str[:60]
        ))
    return violations


def validate_market_value(value_str: str, field_name: str, evidence_text: str = "") -> List[ConstraintViolation]:
    """TAM/SAM/SOM must be numeric and market-sized."""
    violations = []
    for msg in _check_value(value_str, _MARKET_CONSTRAINTS):
        violations.append(ConstraintViolation(
            field=field_name, message=msg, severity="error", value=value_str[:60]
        ))
    # Additional: must be a reasonably large number for a market
    from app.rag.number_utils import parse_indian_number
    num = parse_indian_number(value_str)
    if num > 0 and num < 1000000 and "$" not in value_str and "mn" not in value_str.lower():
        violations.append(ConstraintViolation(
            field=field_name,
            message=f"value ({value_str}) seems too small for a market size (≥₹10L expected)",
            severity="warning",
            value=value_str[:60],
        ))
    return violations


def validate_orders(value_str: str, evidence_text: str = "") -> List[ConstraintViolation]:
    """Orders must mention units, orders, bookings, or contracts."""
    violations = []
    check_text = f"{value_str} {evidence_text}".lower()
    has_order_signal = any(x in check_text for x in ["order", "booking", "unit", "po", "purchase", "contract", "deliver", "completed", "shipped", "processed"])
    if not has_order_signal and evidence_text:
        for msg in _check_value(value_str, _ORDERS_CONSTRAINTS):
            violations.append(ConstraintViolation(
                field="orders", message=msg, severity="error", value=value_str[:60]
            ))
    for msg in _check_value(value_str, _ORDERS_CONSTRAINTS):
        violations.append(ConstraintViolation(
            field="orders", message=msg, severity="warning", value=value_str[:60]
        ))
    num_match = re.search(r'(\d+\.?\d*)', value_str.replace(',', ''))
    if num_match:
        num_str = num_match.group(1)
        if '.' in num_str:
            violations.append(ConstraintViolation(
                field="orders", message="orders must be whole numbers (no decimals)",
                severity="error", value=value_str[:60]
            ))
    return violations


def validate_customers(value_str: str, evidence_text: str = "") -> List[ConstraintViolation]:
    """Customers must be count-based (whole numbers), not currency values."""
    violations = []
    # Must not have currency symbols
    if re.search(r'[\$₹€£]|inr|usd|eur|gbp|cr|lakh|lac|mn|million|billion', value_str.lower()):
        violations.append(ConstraintViolation(
            field="customers", message="customers must not contain currency/unit indicators",
            severity="error", value=value_str[:60]
        ))
    # Must have a number
    if not re.search(r'\d+', value_str):
        violations.append(ConstraintViolation(
            field="customers", message="must contain a number",
            severity="error", value=value_str[:60]
        ))
    # Reject decimals for count-based metrics
    num_match = re.search(r'(\d+\.?\d*)', value_str.replace(',', ''))
    if num_match:
        num_str = num_match.group(1)
        if '.' in num_str:
            violations.append(ConstraintViolation(
                field="customers", message="customers must be whole numbers (no decimals)",
                severity="error", value=value_str[:60]
            ))
    return violations


def validate_funding(value_str: str, field_name: str, evidence_text: str = "") -> List[ConstraintViolation]:
    """Funding must have currency + number, must not be a market metric."""
    violations = []
    for msg in _check_value(value_str, _FUNDING_CONSTRAINTS):
        violations.append(ConstraintViolation(
            field=field_name, message=msg, severity="error", value=value_str[:60]
        ))
    return violations


# ── Ontology Reject Layer ─────────────────────────────────────────────────

class OntologyRejectLayer:
    """Rejects invalid metric assignments before they enter canonical registry.

    Scans structured_data before build_canonical_registry() is called
    and moves/nulls invalid assignments.
    """

    FIELD_CONSTRAINT_MAP = {
        "traction.revenue": validate_revenue,
        "revenue_details.current_revenue": validate_revenue,
        "industry_overview.tam": lambda v, e=None: validate_market_value(v, "tam"),
        "industry_overview.sam": lambda v, e=None: validate_market_value(v, "sam"),
        "industry_overview.som": lambda v, e=None: validate_market_value(v, "som"),
        "traction.orders": validate_orders,
        "traction.customers": validate_customers,
        "funding.current_raise": lambda v, e=None: validate_funding(v, "funding"),
        "funding.valuation": lambda v, e=None: validate_funding(v, "valuation"),
        "pipeline.pipeline_value": lambda v, e=None: validate_funding(v, "pipeline"),
    }

    @classmethod
    def reject_invalid(cls, structured_data: dict) -> Tuple[dict, List[ConstraintViolation]]:
        """Scan structured_data and clear any values that violate ontology constraints.
        Returns (structured_data, violations)."""
        violations = []

        for field_path, validator in cls.FIELD_CONSTRAINT_MAP.items():
            section, field = field_path.split(".")
            section_data = structured_data.get(section, {})
            if not isinstance(section_data, dict):
                continue
            value_obj = section_data.get(field, "")
            if not value_obj:
                continue

            if isinstance(value_obj, dict):
                value_str = value_obj.get("value", "")
                evidence_text = value_obj.get("evidence_text", "")
            else:
                value_str = str(value_obj)
                evidence_text = ""

            if not value_str or value_str.strip() in ("", "null", "none"):
                continue

            field_violations = validator(value_str, evidence_text)
            for v in field_violations:
                if v.severity == "error":
                    print(f"[ONTOLOGY REJECT] {field_path}: {v.message} — clearing '{value_str}'")
                    if isinstance(value_obj, dict):
                        value_obj["value"] = ""
                    else:
                        section_data[field] = ""
                    violations.append(v)

        return structured_data, violations

    @classmethod
    def check_and_report(cls, structured_data: dict) -> List[str]:
        """Non-destructive check — returns violation messages without modifying data."""
        messages = []
        for field_path, validator in cls.FIELD_CONSTRAINT_MAP.items():
            section, field = field_path.split(".")
            section_data = structured_data.get(section, {})
            if not isinstance(section_data, dict):
                continue
            value_obj = section_data.get(field, "")
            if not value_obj:
                continue

            if isinstance(value_obj, dict):
                value_str = value_obj.get("value", "")
                evidence_text = value_obj.get("evidence_text", "")
            else:
                value_str = str(value_obj)
                evidence_text = ""

            if not value_str or value_str.strip() in ("", "null", "none"):
                continue

            field_violations = validator(value_str, evidence_text)
            for v in field_violations:
                if v.severity == "error":
                    messages.append(f"Ontology reject: {field_path} — {v.message} ('{v.value}')")
        return messages
