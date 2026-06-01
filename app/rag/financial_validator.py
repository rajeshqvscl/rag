import re
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

_PROXIMITY_WINDOW = 100


class MetricCategory(Enum):
    EARNED_REVENUE = "earned_revenue"
    PROJECT_VALUE = "project_value"
    PO_VALUE = "po_value"
    GRANT = "grant"
    PIPELINE = "pipeline"
    PROJECTION = "projection"
    VALUATION = "valuation"
    RAISE_AMOUNT = "raise_amount"
    UNIT_COUNT = "unit_count"
    CUSTOMER_COUNT = "customer_count"
    ORDER_COUNT = "order_count"
    EXPECTED_ORDER = "expected_order"
    UNCLASSIFIED = "unclassified"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_num(val) -> float:
    if not val:
        return 0.0
    if isinstance(val, dict):
        val = val.get("value", "")
    m = re.search(r'[\d.]+', str(val).replace(',', ''))
    return float(m.group()) if m else 0.0


def _normalize_indian(val: str) -> float:
    if isinstance(val, dict):
        val = val.get("value", "")
    from app.rag.number_utils import parse_indian_number
    return parse_indian_number(str(val))


def _detect_unit(val: str) -> str:
    if isinstance(val, dict):
        val = val.get("value", "")
    from app.rag.number_utils import detect_unit as du
    return du(str(val)) or ''


def _nearby_text(context: str, needle: str, window: int = _PROXIMITY_WINDOW) -> str:
    """Find nearby text around a value, with fallback to numeric portion matching."""
    if not context or not needle:
        return ""
    if isinstance(needle, dict):
        needle = needle.get("value", "")
    needle_lower = str(needle).lower()[:12]
    idx = context.lower().find(needle_lower)
    if idx == -1:
        # Try finding just the numeric portion (handles format mismatches like "60 Cr" vs "60+ cr")
        nums = re.findall(r'[\d,]+\.?\d*', str(needle))
        for num in nums:
            idx = context.lower().find(num)
            if idx != -1:
                start = max(0, idx - window)
                end = min(len(context), idx + window)
                return context[start:end]
        return ""
    start = max(0, idx - window)
    end = min(len(context), idx + window)
    return context[start:end]


def _keyword_hit(text: str, keywords: List[str]) -> bool:
    """Check for keyword presence with word boundaries to prevent substring false positives.
    'po' matches 'purchase order' but not 'potential'. 'arr' matches 'ARR' but not 'array'."""
    t = text.lower()
    for kw in keywords:
        try:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', t):
                return True
        except re.error:
            if kw.lower() in t:
                return True
    return False


def _classify_metric(value: str, context: str, slide_headers: Optional[List[str]] = None, strict: bool = False) -> MetricCategory:
    """Classify a financial value into MetricCategory using nearby context keywords.
    
    Uses multi-level context:
    1. Slide headers / section titles (most authoritative)
    2. Nearby text within proximity window
    3. Value-string patterns
    
    Args:
        strict: If True, requires specific nearby-text match (no full-context fallback).
    """
    if not value:
        return MetricCategory.UNCLASSIFIED

    # Level 1: Slide headers / section titles (highest authority)
    if slide_headers:
        headers_text = " ".join(slide_headers).lower()
        hdr_grants = _keyword_hit(headers_text, ["grant", "funding received", "non-dilutive"])
        hdr_po = _keyword_hit(headers_text, ["purchase order", "po", "booking", "contract", "order book"])
        hdr_pipeline = _keyword_hit(headers_text, ["pipeline", "expected", "prospect", "loi"])
        hdr_projection = _keyword_hit(headers_text, ["projection", "forecast", "target", "financial model"])
        hdr_revenue = _keyword_hit(headers_text, ["revenue", "income", "financials", "p&l", "profit & loss"])
        hdr_funding = _keyword_hit(headers_text, ["funding", "fundraise", "investment", "capital"])

        # Slide title "Funding & Purchase Orders" → PO takes priority over funding
        if hdr_po and hdr_funding:
            return MetricCategory.PO_VALUE
        if hdr_grants:
            return MetricCategory.GRANT
        if hdr_po:
            return MetricCategory.PO_VALUE
        if hdr_pipeline:
            return MetricCategory.PIPELINE
        if hdr_projection:
            return MetricCategory.PROJECTION
        if hdr_funding:
            return MetricCategory.RAISE_AMOUNT

    nearby = _nearby_text(context, value)
    if not nearby:
        if strict:
            return MetricCategory.UNCLASSIFIED
        # Fallback: scan first 500 chars of context as a broader window
        nearby = context[:500] if len(context) > 50 else context
    lower = nearby.lower()

    # Contract / committed deal (most specific)
    if _keyword_hit(nearby, ["contract", "deal", "committed"]):
        return MetricCategory.PO_VALUE
    # PO keywords
    if _keyword_hit(nearby, ["po", "purchase order", "expected order", "idel", "drdo"]):
        return MetricCategory.PO_VALUE
    # Bookings / booked orders
    if _keyword_hit(nearby, ["booking", "booked"]):
        return MetricCategory.ORDER_COUNT
    # Grant/subsidy
    if _keyword_hit(nearby, ["grant", "subsidy", "non-dilutive", "gst", "government"]):
        return MetricCategory.GRANT
    # Pipeline
    if _keyword_hit(nearby, ["pipeline", "potential", "expected", "letter of intent", "loi", "prospect", "upcoming"]):
        return MetricCategory.PIPELINE
    # Projection (note: 'arr' is NOT a projection — see EARNED_REVENUE below)
    if _keyword_hit(nearby, ["projection", "forecast", "target", "plan"]):
        return MetricCategory.PROJECTION
    # Unit counts
    if _keyword_hit(nearby, ["unit", "set", "system", "module", "kit", "equipment"]):
        return MetricCategory.UNIT_COUNT
    # Project / engagement value
    if _keyword_hit(nearby, ["project", "engagement"]):
        return MetricCategory.PROJECT_VALUE
    # Valuation
    if _keyword_hit(nearby, ["valuation", "pre-money", "post-money"]):
        return MetricCategory.VALUATION
    # Raise
    if _keyword_hit(nearby, ["raising", "fundraise", "round", "series", "capital"]):
        return MetricCategory.RAISE_AMOUNT
    # Revenue keywords — least confident signal
    if _keyword_hit(nearby, ["revenue", "invoiced", "arr", "sales", "income"]):
        return MetricCategory.EARNED_REVENUE
    return MetricCategory.UNCLASSIFIED


# ---------------------------------------------------------------------------
# 1D-i: Semantic Financial Classifier
# ---------------------------------------------------------------------------

def _semantic_classifier(structured_data: dict, context: str, warnings: List[str], flagged: dict) -> None:
    tr = structured_data.get("traction", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}

    rev = str(tr.get("revenue", "") or "")
    if rev and _keyword_hit(_nearby_text(context, rev), ["unit", "set", "system", "po", "contract"]):
        category = _classify_metric(rev, context)
        if category in (MetricCategory.PO_VALUE, MetricCategory.UNIT_COUNT, MetricCategory.EXPECTED_ORDER):
            warnings.append(
                f"Revenue ({rev}) classified as {category.value} — likely not earned revenue"
            )
            flagged["revenue_classification"] = category.value

    orders = str(tr.get("orders", "") or "")
    if orders:
        cat = _classify_metric(orders, context)
        if cat == MetricCategory.EXPECTED_ORDER:
            warnings.append(f"Orders ({orders}) appears to be expected/pipeline orders, not actual bookings")
            flagged["orders_classification"] = cat.value
        elif cat == MetricCategory.UNIT_COUNT:
            warnings.append(f"Orders ({orders}) appears to be product units, not order count")

    customers = str(tr.get("customers", "") or "")
    if customers:
        cat = _classify_metric(customers, context)
        if cat == MetricCategory.UNIT_COUNT:
            warnings.append(f"Customers ({customers}) appears to be product units, not customer count")
            flagged["customers_classification"] = cat.value

    curr_rev = str(rd.get("current_revenue", "") or "")
    if curr_rev:
        cat = _classify_metric(curr_rev, context)
        if cat in (MetricCategory.PO_VALUE, MetricCategory.UNIT_COUNT):
            warnings.append(f"Current revenue ({curr_rev}) classified as {cat.value} — verify source")

    projections = rd.get("projections", [])
    if isinstance(projections, list):
        flagged_projs = []
        for p in projections:
            p_val = ""
            if isinstance(p, dict):
                p_val = str(p.get("value", "") or "")
            elif isinstance(p, str):
                p_val = p
            if p_val:
                cat = _classify_metric(p_val, context)
                if cat in (MetricCategory.PO_VALUE, MetricCategory.UNIT_COUNT, MetricCategory.EXPECTED_ORDER):
                    flagged_projs.append({"value": p_val, "classification": cat.value})
        if flagged_projs:
            warnings.append(f"{len(flagged_projs)} projection(s) classified as PO/contract values")
            flagged["flagged_projections"] = flagged_projs


# ---------------------------------------------------------------------------
# 1D-ii: Cross-Field Deterministic Rules
# ---------------------------------------------------------------------------

def _cross_field_rules(structured_data: dict, warnings: List[str], flagged: dict) -> None:
    tr = structured_data.get("traction", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}
    ind = structured_data.get("industry_overview", {}) or {}
    fund = structured_data.get("funding", {}) or {}
    pipe = structured_data.get("pipeline", {}) or {}

    # Revenue sanity
    rev_raw = str(tr.get("revenue", "") or "")
    rev_num = _normalize_indian(rev_raw)
    if rev_num > 0 and rev_num < 100_000:
        warnings.append(f"Revenue ({rev_raw}) is very low (< ₹1L) — verify as actual earned revenue")
    if rev_num > 1_000_000_000_000:
        warnings.append(f"Revenue ({rev_raw}) unusually high (> ₹1000 Cr) — verify source for early stage")

    # Valuation sanity
    val_raw = str(fund.get("valuation", "") or "")
    raise_raw = str(fund.get("current_raise", "") or "")
    val_num = _normalize_indian(val_raw)
    raise_num = _normalize_indian(raise_raw)
    if val_num > 0 and raise_num > 0:
        ratio = val_num / raise_num
        if ratio > 10:
            warnings.append(
                f"Valuation ({val_raw}) is unusually high ({ratio:.0f}x) for raise ({raise_raw}) — verify source"
            )
        elif ratio > 3:
            warnings.append(
                f"Valuation ({val_raw}) appears high ({ratio:.0f}x) relative to raise ({raise_raw}) — verify"
            )

    # Funding field swap: previous round vs valuation
    prev_rounds = fund.get("previous_rounds", [])
    if isinstance(prev_rounds, list) and val_num > 0:
        for r in prev_rounds:
            r_val = 0.0
            if isinstance(r, dict):
                r_val = _normalize_indian(r.get("amount", ""))
            elif isinstance(r, str):
                r_val = _normalize_indian(r)
            if r_val > 0 and abs(r_val - val_num) / max(val_num, 1) < 0.05:
                warnings.append(f"Previous round value (₹{r_val:,.0f}) matches valuation — fields may be swapped")

    # Pipeline vs revenue proximity
    pipe_raw = str(pipe.get("pipeline_value", "") or "")
    pipe_num = _normalize_indian(pipe_raw)
    if pipe_num > 0 and rev_num > 0 and abs(pipe_num - rev_num) / max(pipe_num, rev_num, 1) < 0.05:
        warnings.append("Pipeline value ≈ Revenue value — likely same value copied to both fields")

    # TAM/SAM/SOM hierarchy
    tam_raw = str(ind.get("tam", "") or "")
    sam_raw = str(ind.get("sam", "") or "")
    som_raw = str(ind.get("som", "") or "")
    tam_num = _normalize_indian(tam_raw)
    sam_num = _normalize_indian(sam_raw)
    som_num = _normalize_indian(som_raw)
    if tam_num > 0 and sam_num > 0 and tam_num < sam_num:
        warnings.append("TAM < SAM — market sizes likely swapped")
    if sam_num > 0 and som_num > 0 and sam_num < som_num:
        warnings.append("SAM < SOM — market sizes likely swapped")
    if tam_num > 0 and rev_num > 0 and tam_num < rev_num:
        warnings.append("TAM < Revenue — TAM may contain revenue value")

    # TAM without currency unit
    if tam_raw and not re.search(r'[₹$]|cr|mn|bn|lakh|million|billion', str(tam_raw), re.IGNORECASE):
        warnings.append(f"TAM ({tam_raw}) lacks currency unit — may not be a market size value")

    # SOM unusually small vs TAM
    if tam_num > 0 and som_num > 0 and som_num / tam_num < 0.01:
        warnings.append(f"SOM is only {som_num/tam_num*100:.1f}% of TAM — verify market size split")

    # --- Unit cross-validation ---

    tam_unit = _detect_unit(tam_raw)
    sam_unit = _detect_unit(sam_raw)
    som_unit = _detect_unit(som_raw)
    rev_unit = _detect_unit(rev_raw)

    # Unit mismatch between TAM and Revenue
    if tam_unit and rev_unit and tam_unit != rev_unit:
        # If TAM uses "Mn" (= ~5.5 Cr) but Revenue uses "Cr" or "Lakhs", flag
        if tam_unit == "Mn" and rev_unit in ("Cr", "Lakhs"):
            warnings.append(
                f"TAM ({tam_raw}) uses '{tam_unit}' unit while Revenue ({rev_raw}) uses "
                f"'{rev_unit}' — TAM may use wrong unit (e.g., ₹55 Mn = ₹5.5 Cr, unlikely for healthcare market)"
            )
        elif tam_unit == "Mn" and tam_num < 10_000_000:
            warnings.append(
                f"TAM ({tam_raw}) is only {tam_num/10000000:.1f} Cr in 'Mn' units — "
                f"verify magnitude; may be mis-scaled for stated market"
            )
        elif tam_unit == "K" and rev_unit in ("Cr", "Lakhs"):
            warnings.append(
                f"TAM ({tam_raw}) uses 'K' units while Revenue ({rev_raw}) uses "
                f"'{rev_unit}' — TAM unit likely incorrect"
            )

    # Unit mismatch across market sizes (TAM/SAM/SOM should use same unit)
    market_units = [(tam_raw, "TAM", tam_unit), (sam_raw, "SAM", sam_unit), (som_raw, "SOM", som_unit)]
    present_units = [(label, u) for raw, label, u in market_units if raw and u]
    if len(present_units) >= 2:
        units_seen = set(u for _, u in present_units)
        if len(units_seen) > 1:
            unit_strs = [f"{l}={u}" for l, u in present_units]
            warnings.append(f"Market size unit mismatch: {'; '.join(unit_strs)} — should use consistent units")

    # --- Temporal consistency checks ---
    tr = structured_data.get("traction", {}) or {}
    rtt = str(tr.get("revenue_time_type", "") or "").lower()
    ott = str(tr.get("orders_time_type", "") or "").lower()
    rd = structured_data.get("revenue_details", {}) or {}
    crtt = str(rd.get("current_revenue_time_type", "") or "").lower()

    # Flag projections that lack a future-oriented time_type
    if rev_raw and rtt and rtt not in ("historical", "current", "projection", "pipeline", "contract", "grant", "fundraise"):
        warnings.append(f"Revenue time_type '{rtt}' is not a recognized temporal class")
    if rev_raw and not rtt:
        warnings.append(f"Revenue ({rev_raw}) has no time_type — LLM should classify temporally")

    # Flag mismatch: if revenue period suggests historical but time_type says current
    if rev_raw and rtt == "historical" and re.search(r'FY2[5-9]|20[2-9][5-9]', rev_raw):
        warnings.append(f"Revenue ({rev_raw}) is marked 'historical' but period appears current/future")
    if rev_raw and rtt == "current" and re.search(r'FY2[0-4]|202[0-4]', rev_raw):
        warnings.append(f"Revenue ({rev_raw}) is marked 'current' but period appears historical")


# ---------------------------------------------------------------------------
# 1D-vi: Deterministic Financial Rules (ARPC, dilution, projections, etc.)
# ---------------------------------------------------------------------------

def _deterministic_rules(structured_data: dict, warnings: List[str], flagged: dict) -> None:
    """Apply strong deterministic validation rules for financial consistency."""
    tr = structured_data.get("traction", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}
    ind = structured_data.get("industry_overview", {}) or {}
    fund = structured_data.get("funding", {}) or {}
    pipe = structured_data.get("pipeline", {}) or {}

    rev_raw = str(tr.get("revenue", "") or "")
    rev_num = _normalize_indian(rev_raw) if rev_raw else 0.0
    cust_raw = str(tr.get("customers", "") or "")
    cust_num = _extract_num(cust_raw)
    orders_raw = str(tr.get("orders", "") or "")
    orders_num = _extract_num(orders_raw)
    val_raw = str(fund.get("valuation", "") or "")
    val_num = _normalize_indian(val_raw) if val_raw else 0.0
    raise_raw = str(fund.get("current_raise", "") or "")
    raise_num = _normalize_indian(raise_raw) if raise_raw else 0.0
    pipe_raw = str(pipe.get("pipeline_value", "") or "")
    pipe_num = _normalize_indian(pipe_raw) if pipe_raw else 0.0

    # 1. ARPC sanity: ARR / customers
    if rev_num > 0 and cust_num > 0:
        arpc = rev_num / cust_num
        if arpc < 100:  # < ₹100 per customer — too low
            warnings.append(
                f"ARPC = ₹{arpc:,.0f} (Revenue ₹{rev_num:,.0f} / {cust_num:.0f} customers) — "
                f"revenue may be too low for customer count, or customers may be units"
            )
            flagged["arpc_sanity"] = {"arpc": arpc, "warning": "too_low"}
        elif arpc > 100_000_000:  # > ₹10 Cr per customer — too high
            warnings.append(
                f"ARPC = ₹{arpc:,.0f} (Revenue ₹{rev_num:,.0f} / {cust_num:.0f} customers) — "
                f"revenue may be too high for customer count, or customers may not be individual companies"
            )
            flagged["arpc_sanity"] = {"arpc": arpc, "warning": "too_high"}

    # 2. Dilution math: dilution = raise / (raise + pre_money)
    if val_num > 0 and raise_num > 0 and raise_num < val_num:
        dilution = raise_num / (raise_num + (val_num - raise_num))
        if dilution > 0.5:
            warnings.append(
                f"Dilution = {dilution:.0%} (Raise ₹{raise_num:,.0f} / Val ₹{val_num:,.0f}) — "
                f"high dilution suggests valuation may be post-money or fields swapped"
            )
            flagged["dilution"] = {"dilution_pct": round(dilution * 100), "warning": "high"}
        elif dilution < 0.01:
            warnings.append(
                f"Dilution = {dilution:.1%} (Raise ₹{raise_num:,.0f} / Val ₹{val_num:,.0f}) — "
                f"very low dilution, raise may be undervalued"
            )
            flagged["dilution"] = {"dilution_pct": round(dilution * 100), "warning": "low"}

    # 3. Projection monotonicity: projections should >= current (unless stated decline)
    projections = rd.get("projections", [])
    # Pull existing flagged projections from _projection_classifier (PO/contract skip list)
    already_flagged_vals = set()
    existing = flagged.get("flagged_projections", [])
    if isinstance(existing, list):
        for fp in existing:
            if isinstance(fp, dict) and fp.get("value"):
                already_flagged_vals.add(str(fp["value"]))
    if isinstance(projections, list) and rev_num > 0:
        flagged_projs = []
        for p in projections:
            if isinstance(p, dict):
                p_val = str(p.get("value", "") or "")
                p_period = str(p.get("period", "") or "")
            elif isinstance(p, str):
                p_val = p
                p_period = ""
            else:
                continue
            p_num = _normalize_indian(p_val) if p_val else 0.0
            # Skip projections already classified as PO/contract by _projection_classifier
            if p_num > 0 and p_val in already_flagged_vals:
                continue
            if p_num > 0 and p_num < rev_num * 0.5:
                flagged_projs.append({
                    "projection": p_val,
                    "period": p_period,
                    "current_revenue": rev_raw,
                    "reason": "projection < 50% of current revenue — may be misclassified metric"
                })
                warnings.append(
                    f"Projection ({p_val}) is less than 50% of current revenue ({rev_raw}) — "
                    f"may not be a revenue projection"
                )
        if flagged_projs:
            if existing and isinstance(existing, list):
                existing.extend(flagged_projs)
                flagged["flagged_projections"] = existing
            else:
                flagged["flagged_projections"] = flagged_projs

    # 4. Revenue < TAM consistency (stronger than existing — this is deterministic)
    tam_raw = str(ind.get("tam", "") or "")
    tam_num = _normalize_indian(tam_raw) if tam_raw else 0.0
    if tam_num > 0 and rev_num > 0 and rev_num > tam_num * 1.5:
        warnings.append(
            f"Revenue ({rev_raw}) is {rev_num/tam_num:.1f}x TAM ({tam_raw}) — "
            f"revenue likely exceeds total addressable market, check for swapped values"
        )
        flagged["revenue_exceeds_tam"] = {
            "revenue": rev_raw, "tam": tam_raw, "ratio": round(rev_num / tam_num, 1)
        }

    # 5. Valuation/Raise ratio bounds
    if val_num > 0 and raise_num > 0:
        ratio = val_num / raise_num
        if ratio < 1.0:
            warnings.append(
                f"Valuation ({val_raw}) < Raise ({raise_raw}) — "
                f"valuation must exceed raise amount; fields likely swapped"
            )
            flagged["valuation_raise_swap"] = {"ratio": round(ratio, 2)}
        elif ratio > 50:
            warnings.append(
                f"Valuation ({val_raw}) is {ratio:.0f}x Raise ({raise_raw}) — "
                f"unusually high; verify valuation source"
            )
            flagged["valuation_raise_ratio"] = {"ratio": round(ratio, 1)}

    # 6. Pipeline-to-Revenue ratio consistency
    if rev_num > 0 and pipe_num > 0:
        ratio = pipe_num / rev_num
        if ratio > 100:
            warnings.append(
                f"Pipeline ({pipe_raw}) is {ratio:.0f}x Revenue ({rev_raw}) — "
                f"unusually high pipeline-to-revenue ratio; may be overvalued pipeline"
            )
            flagged["pipeline_revenue_ratio"] = {"ratio": round(ratio, 1)}

    # 7. Customer-order name confusion: if orders and customers have same numeric value
    if orders_num > 0 and cust_num > 0 and abs(orders_num - cust_num) / max(orders_num, cust_num, 1) < 0.05:
        warnings.append(
            f"Orders ({orders_raw}) and Customers ({cust_raw}) have nearly identical counts — "
            f"may be same value copied to both fields"
        )
        flagged["orders_customers_same"] = True


# ---------------------------------------------------------------------------
# 1D-iii: Entity Type Classifier
# ---------------------------------------------------------------------------

def _entity_classifier(structured_data: dict, context: str, warnings: List[str], flagged: dict) -> None:
    tr = structured_data.get("traction", {}) or {}

    customers_raw = str(tr.get("customers", "") or "")
    cust_num = _extract_num(customers_raw)
    if customers_raw and 0 < cust_num < 50:
        nearby = _nearby_text(context, customers_raw)
        if _keyword_hit(nearby, ["unit", "set", "system", "module", "equipment", "kit"]):
            warnings.append(
                f"Customers count ({customers_raw}) likely refers to product units, not customers"
            )
            flagged["entity_customers"] = "product_units"

    orders_raw = str(tr.get("orders", "") or "")
    ord_num = _extract_num(orders_raw)
    if orders_raw and 0 < ord_num < 100:
        nearby = _nearby_text(context, orders_raw)
        if _keyword_hit(nearby, ["expected", "projected", "po", "purchase order", "order set", "anticipated"]):
            warnings.append(
                f"Orders count ({orders_raw}) likely reflects expected/pipeline orders, not actual bookings"
            )
            flagged["entity_orders"] = "expected_orders"


# ---------------------------------------------------------------------------
# 1D-iv: Projection vs Actual Classifier
# ---------------------------------------------------------------------------

def _projection_classifier(structured_data: dict, context: str, warnings: List[str], flagged: dict) -> None:
    rd = structured_data.get("revenue_details", {}) or {}
    projections = rd.get("projections", [])
    if not isinstance(projections, list):
        return

    flagged_projs = []
    for p in projections:
        if isinstance(p, dict):
            p_val = str(p.get("value", "") or "")
            p_period = str(p.get("period", "") or "")
            p_context = p_val + " " + p_period
        elif isinstance(p, str):
            p_val = p
            p_context = p
        else:
            continue
        if not p_val or not re.search(r'\d', p_val):
            continue
        nearby = _nearby_text(context, p_val)
        if _keyword_hit(nearby, ["po", "purchase order", "contract", "deal", "order", "expected"]):
            flagged_projs.append({
                "value": p_val,
                "reason": "likely contract/PO value, not revenue projection"
            })
            warnings.append(f"Projection ({p_val}) classified as PO/contract value — not a revenue projection")
    if flagged_projs:
        flagged["flagged_projections"] = flagged_projs


# ---------------------------------------------------------------------------
# 1D-v: Grant & Pipeline Missing Detection
# ---------------------------------------------------------------------------

def _missing_detector(structured_data: dict, context: str, warnings: List[str], flagged: dict) -> None:
    if not context:
        return
    context_lower = context.lower()

    # Grants
    grant_keywords = [
        ("grant", r'(?:grant|sanctioned)[^.]*?(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))'),
        ("subsidy", r'(?:subsidy|subsidised)[^.]*?(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))'),
        ("non-dilutive", r'(?:non.dilutive)[^.]*?(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))'),
        ("gst", r'(?:gst|government funding)[^.]*?(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))'),
    ]
    found_grants = []
    for label, pattern in grant_keywords:
        matches = re.findall(pattern, context_lower, re.IGNORECASE)
        for m in matches:
            found_grants.append(f"{label}: {m if isinstance(m, str) else m[0]}")
    if found_grants:
        fund = structured_data.get("funding", {}) or {}
        if not fund.get("current_raise"):
            warnings.append(
                f"Government grants/funding mentioned ({'; '.join(found_grants[:3])}) — may not be captured in output"
            )
            flagged["possible_grants"] = found_grants[:5]

    # Pipeline opportunities
    pipeline_keywords = [
        (r'(?:po|purchase order|first order|expected order)\s*(?:worth|of|valued at)?\s*(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))', "PO"),
        (r'(?:idel|indigen|drdo)[^.]*?(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))', "IDEX/DRDO"),
        (r'(?:pipeline|letter of intent|loi)[^.]*?(₹\s*[\d,.]+\s*(?:cr|lakh|l|mn))', "pipeline"),
    ]
    found_pipeline = []
    for pattern, label in pipeline_keywords:
        matches = re.findall(pattern, context_lower, re.IGNORECASE)
        for m in matches:
            found_pipeline.append(f"{label}: {m if isinstance(m, str) else m[0]}")
    if found_pipeline:
        pipe = structured_data.get("pipeline", {}) or {}
        if not pipe.get("pipeline_value"):
            warnings.append(
                f"Major pipeline/PO opportunities found ({'; '.join(found_pipeline[:3])}) — consider updating pipeline section"
            )
            flagged["uncaptured_pipeline"] = found_pipeline[:5]

    # Additional_metrics — scan for uncategorized metrics
    additional = structured_data.get("additional_metrics", [])
    if isinstance(additional, list):
        for entry in additional:
            if isinstance(entry, dict):
                ev = str(entry.get("value", "") or "")
                ek = str(entry.get("key", "") or "")
            elif isinstance(entry, str):
                ev = entry
                ek = ""
            else:
                continue
            if ev and re.search(r'\d', ev):
                nearby = _nearby_text(context, ev)
                cat = _classify_metric(ev, context if nearby else "")
        # No direct warning for additional_metrics entries — they're already captured


# ---------------------------------------------------------------------------
# Auto-fix bare numbers
# ---------------------------------------------------------------------------

def _auto_fix_bare_numbers(structured_data: dict, warnings: List[str]) -> None:
    tr = structured_data.get("traction", {})
    if not isinstance(tr, dict):
        return
    for field, noun in [("customers", "customers"), ("orders", "orders")]:
        val = tr.get(field, "")
        if isinstance(val, dict):
            val_str = val.get("value", "")
            if val_str and re.match(r'^\d+(?:\s*\(FY\d{2}-\d{2}\)\s*)?$', val_str.strip()):
                val["value"] = re.sub(r'(\d+)', r'\1 ' + noun, val_str)
                warnings.append(f"{noun.capitalize()} count missing noun — auto-corrected")
        else:
            if val and re.match(r'^\d+(?:\s*\(FY\d{2}-\d{2}\)\s*)?$', str(val).strip()):
                tr[field] = re.sub(r'(\d+)', r'\1 ' + noun, str(val))
                warnings.append(f"{noun.capitalize()} count missing noun — auto-corrected")


# ---------------------------------------------------------------------------
# Ensure market sizes have FY format
# ---------------------------------------------------------------------------

def _ensure_fy_on_market_sizes(structured_data: dict) -> None:
    ind = structured_data.get("industry_overview", {})
    if not isinstance(ind, dict):
        return
    for field in ["tam", "sam", "som"]:
        val = ind.get(field, "")
        if isinstance(val, dict):
            val_str = val.get("value", "")
            if val_str and re.search(r'\d', val_str) and not re.search(r'FY\d{2}-\d{2}', val_str):
                val["value"] = f"{val_str} (FY25-26)"
        else:
            if val and re.search(r'\d', str(val)) and not re.search(r'FY\d{2}-\d{2}', str(val)):
                ind[field] = f"{val} (FY25-26)"


# ---------------------------------------------------------------------------
# 1E: Confidence Scoring Integration
# ---------------------------------------------------------------------------

# Source type weights used when metadata is available
SOURCE_WEIGHTS = {
    "table": 0.9,
    "text": 0.7,
    "chart": 0.6,
    "image": 0.5,
    "heading": 0.3,
}
DEFAULT_SOURCE_WEIGHT = 0.7


def _format_confidence(val: str, val_context: str = "") -> float:
    """Score format quality of a metric value with unit-type awareness."""
    if not val or not str(val).strip():
        return 0.0
    s = str(val)
    score = 0.5  # baseline: text-only
    if re.search(r'[₹$€£]', s):
        score = 0.95  # currency symbol present — highest confidence
    elif re.search(r'(?:Cr|Lakh|L|Mn|Bn|Million|Billion|Thousand|K)\b', s, re.IGNORECASE):
        score = 0.85  # unit present
    elif re.search(r'\d+', s):
        score = 0.7  # numeric but no unit
    if re.search(r'FY\d{2}-\d{2}', s):
        score = min(score + 0.1, 1.0)  # FY label present
    elif re.search(r'FY\d{2,4}', s, re.IGNORECASE):
        score = min(score + 0.05, 1.0)  # partial FY

    # Unit-type boost: if context helps classify, it's more reliable
    if val_context:
        try:
            from app.rag.number_utils import classify_unit_type
            ut = classify_unit_type(val, val_context)
            if ut.value in ("currency", "percentage", "count"):
                score = min(score + 0.05, 1.0)
        except Exception:
            pass

    return round(score, 2)


def _consistency_boost(structured_data: dict, context: str = "") -> Dict[str, float]:
    """Score cross-field consistency and return per-field adjustments.
    Returns per-field adjustments as confidence delta (positive or negative)."""
    boosts = {}
    ind = structured_data.get("industry_overview", {}) or {}
    tr = structured_data.get("traction", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}
    fund = structured_data.get("funding", {}) or {}
    pipe = structured_data.get("pipeline", {}) or {}

    tam_n = _normalize_indian(str(ind.get("tam", "") or ""))
    sam_n = _normalize_indian(str(ind.get("sam", "") or ""))
    som_n = _normalize_indian(str(ind.get("som", "") or ""))

    # TAM > SAM > SOM hierarchy boost
    for field, larger, smaller in [("tam", None, sam_n), ("sam", tam_n, som_n), ("som", sam_n, None)]:
        if larger is not None and smaller is not None and larger >= smaller:
            boosts[f"industry_overview.{field}"] = 0.1
        elif larger is not None and smaller is not None and larger < smaller:
            boosts[f"industry_overview.{field}"] = -0.2

    # Revenue < TAM sanity
    rev_n = _normalize_indian(str(tr.get("revenue", "") or ""))
    if tam_n > 0 and rev_n > 0 and rev_n < tam_n:
        boosts["traction.revenue"] = 0.1
    elif tam_n > 0 and rev_n > 0 and rev_n >= tam_n:
        boosts["traction.revenue"] = -0.2

    # Valuation > Raise
    val_n = _normalize_indian(str(fund.get("valuation", "") or ""))
    raise_n = _normalize_indian(str(fund.get("current_raise", "") or ""))
    if val_n > 0 and raise_n > 0 and val_n > raise_n:
        boosts["funding.valuation"] = 0.1
    elif val_n > 0 and raise_n > 0 and val_n <= raise_n:
        boosts["funding.valuation"] = -0.1

    # Revenue-to-current_revenue consistency
    curr_rev_n = _normalize_indian(str(rd.get("current_revenue", "") or ""))
    if rev_n > 0 and curr_rev_n > 0:
        ratio = abs(rev_n - curr_rev_n) / max(rev_n, curr_rev_n, 1)
        if ratio < 0.05:
            boosts["traction.revenue"] = boosts.get("traction.revenue", 0) + 0.05
            boosts["revenue_details.current_revenue"] = 0.05
        elif ratio > 0.5:
            boosts["revenue_details.current_revenue"] = -0.1

    # Temporal consistency: if time_type matches the period context
    rtt = str(tr.get("revenue_time_type", "") or "").lower()
    rev_raw = str(tr.get("revenue", "") or "")
    if rev_raw and rtt:
        has_fy = bool(re.search(r'FY\d{2}-\d{2}', rev_raw))
        if rtt in ("historical", "current") and has_fy:
            boosts["traction.revenue"] = boosts.get("traction.revenue", 0) + 0.05
        elif rtt in ("projection", "pipeline") and not has_fy:
            boosts["traction.revenue"] = boosts.get("traction.revenue", 0) - 0.05

    # Pipeline-to-revenue ratio sanity boost
    pipe_n = _normalize_indian(str(pipe.get("pipeline_value", "") or ""))
    if rev_n > 0 and pipe_n > 0 and 0.5 < pipe_n / rev_n < 20:
        boosts["pipeline.pipeline_value"] = 0.05
        boosts["traction.revenue"] = boosts.get("traction.revenue", 0) + 0.05

    return boosts


def calculate_field_confidence(structured_data: dict, context: str = "") -> Dict[str, float]:
    """Return per-field confidence scores (0.0 - 1.0) with unit-type and source awareness."""
    conf: Dict[str, float] = {}
    boosts = _consistency_boost(structured_data, context)

    # Map fields to their values
    tr = structured_data.get("traction", {}) or {}
    ind = structured_data.get("industry_overview", {}) or {}
    fund = structured_data.get("funding", {}) or {}
    pipe = structured_data.get("pipeline", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}

    field_map: List[Tuple[str, str, str]] = [
        ("company_brief.name", structured_data.get("company_brief", {}).get("name", ""), ""),
        ("traction.revenue", tr.get("revenue", ""), context),
        ("traction.customers", tr.get("customers", ""), context),
        ("traction.orders", tr.get("orders", ""), context),
        ("industry_overview.tam", ind.get("tam", ""), context),
        ("industry_overview.sam", ind.get("sam", ""), context),
        ("industry_overview.som", ind.get("som", ""), context),
        ("funding.current_raise", fund.get("current_raise", ""), context),
        ("funding.valuation", fund.get("valuation", ""), context),
        ("pipeline.pipeline_value", pipe.get("pipeline_value", ""), context),
        ("revenue_details.current_revenue", rd.get("current_revenue", ""), context),
        ("traction.revenue_time_type", tr.get("revenue_time_type", ""), ""),
    ]

    for field_key, raw_val, val_ctx in field_map:
        base = _format_confidence(str(raw_val), val_ctx)
        src = DEFAULT_SOURCE_WEIGHT
        field_conf = round(base * src, 2)
        boost = boosts.get(field_key, 0.0)
        field_conf = round(max(0.0, min(1.0, field_conf + boost)), 2)
        conf[field_key] = field_conf

    # Section-level aggregates
    sec_map: Dict[str, List[str]] = {
        "revenue": ["traction.revenue", "revenue_details.current_revenue"],
        "market": ["industry_overview.tam", "industry_overview.sam", "industry_overview.som"],
        "funding": ["funding.current_raise", "funding.valuation"],
        "traction": ["traction.customers", "traction.orders", "traction.revenue_time_type"],
        "pipeline": ["pipeline.pipeline_value"],
    }
    for sec, fields in sec_map.items():
        vals = [conf.get(f, 0.0) for f in fields]
        conf[sec] = round(sum(vals) / len(vals), 2) if vals else 0.0

    # Overall financial confidence (weighted average of all financial fields)
    fin_fields = ["traction.revenue", "revenue_details.current_revenue",
                  "funding.current_raise", "funding.valuation",
                  "pipeline.pipeline_value", "industry_overview.tam",
                  "traction.customers", "traction.orders"]
    fin_vals = [conf.get(f, 0.0) for f in fin_fields]
    conf["overall"] = round(sum(fin_vals) / len(fin_vals), 2) if fin_vals else 0.0

    return conf


# ---------------------------------------------------------------------------
# Ontological Re-classifier — moves data to correct fields based on type
# ---------------------------------------------------------------------------

FIELD_CLASSIFICATION_MAP = {
    "traction.revenue": ["revenue", "sales", "income", "invoiced", "arr"],
    "traction.orders": ["order", "booking", "unit"],
    "funding.current_raise": ["raise", "funding", "round"],
    "funding.valuation": ["valuation"],
    "pipeline.pipeline_value": ["pipeline", "expected", "upcoming"],
    "revenue_details.current_revenue": ["revenue", "current", "arr", "run_rate"],
}

def ontological_reclassifier(structured_data: dict, context: str = "", slide_headers: Optional[List[str]] = None) -> dict:
    """
    Reclassify financial data based on ontological analysis.
    MOVES values between fields when classification doesn't match.
    E.g., "₹60 Cr" in revenue → pipeline if classified as PO_VALUE.
    """
    overrides = structured_data.get("_canonical_overrides", {})
    warnings = structured_data.get("_validation_warnings", [])
    if not isinstance(overrides, dict):
        overrides = {}
    if not isinstance(warnings, list):
        warnings = []

    tr = structured_data.get("traction", {}) or {}
    rd = structured_data.get("revenue_details", {}) or {}
    pipe = structured_data.get("pipeline", {}) or {}
    fund = structured_data.get("funding", {}) or {}
    ind = structured_data.get("industry_overview", {}) or {}
    additional = structured_data.get("additional_metrics", [])

    # 1. Classify traction.revenue — move if not earned revenue
    rev_raw = tr.get("revenue", "")
    if rev_raw:
        cat = _classify_metric(str(rev_raw), context, slide_headers)
        if cat == MetricCategory.PO_VALUE:
            overrides["revenue→pipeline"] = {"value": rev_raw, "reason": f"Classified as {cat.value}"}
            pipe["pipeline_value"] = pipe.get("pipeline_value", "") or rev_raw
            tr["revenue"] = ""  # Clear from revenue
            warnings.append(f"[ONTOLOGY] Moved '{rev_raw}' from revenue to pipeline (classified as {cat.value})")
        elif cat == MetricCategory.GRANT:
            overrides["revenue→grant"] = {"value": rev_raw, "reason": "Classified as grant"}
            additional.append({"key": "Grant Received", "value": rev_raw, "context": "government_grant"})
            tr["revenue"] = ""
            warnings.append(f"[ONTOLOGY] Moved '{rev_raw}' from revenue to grants")
        elif cat == MetricCategory.PROJECT_VALUE:
            overrides["revenue→project_value"] = {"value": rev_raw, "reason": "Classified as project value"}
            pipe["pipeline_value"] = pipe.get("pipeline_value", "") or rev_raw
            tr["revenue"] = ""
            warnings.append(f"[ONTOLOGY] Moved '{rev_raw}' from revenue to project value")

    # 2. Classify pipeline — move to grant/po if classified as such
    pipe_val = pipe.get("pipeline_value", "")
    if pipe_val:
        cat = _classify_metric(str(pipe_val), context, slide_headers, strict=True)
        if cat == MetricCategory.GRANT:
            overrides["pipeline→grant"] = {"value": pipe_val, "reason": "Classified as grant"}
            additional.append({"key": "Grant Received", "value": pipe_val, "context": "government_grant"})
            pipe["pipeline_value"] = ""
            warnings.append(f"[ONTOLOGY] Moved '{pipe_val}' from pipeline to grants")
        elif cat == MetricCategory.PO_VALUE:
            overrides["pipeline→po"] = {"value": pipe_val, "reason": "Classified as PO"}
            pipe["pipeline_value"] = ""  # Don't keep in pipeline — create separate expected_po
            additional.append({"key": "Expected Purchase Order", "value": pipe_val, "context": "expected_po"})
            pipe["expected_po"] = pipe_val
            warnings.append(f"[ONTOLOGY] Reclassified pipeline '{pipe_val}' as expected PO")

    # 3. Classify current_revenue
    curr_rev = rd.get("current_revenue", "")
    if curr_rev:
        cat = _classify_metric(str(curr_rev), context, slide_headers)
        if cat in (MetricCategory.PO_VALUE, MetricCategory.GRANT, MetricCategory.PROJECT_VALUE):
            if cat == MetricCategory.GRANT:
                additional.append({"key": "Grant Received", "value": str(curr_rev), "context": "government_grant"})
                rd["current_revenue"] = ""
                warnings.append(f"[ONTOLOGY] Moved current_revenue '{curr_rev}' to grants")
            elif cat == MetricCategory.PO_VALUE:
                pipe["expected_po"] = pipe.get("expected_po", "") or str(curr_rev)
                rd["current_revenue"] = ""
                warnings.append(f"[ONTOLOGY] Moved current_revenue '{curr_rev}' to expected PO")

    # 4. Classify projections
    projections = rd.get("projections", [])
    if isinstance(projections, list):
        for i, proj in enumerate(projections):
            if isinstance(proj, dict):
                pval = str(proj.get("value", "") or "")
                if pval:
                    cat = _classify_metric(pval, context, slide_headers)
                    if cat in (MetricCategory.PO_VALUE, MetricCategory.GRANT):
                        if cat == MetricCategory.GRANT:
                            additional.append({"key": "Grant Received", "value": pval, "context": "government_grant"})
                        elif cat == MetricCategory.PO_VALUE:
                            pipe["expected_po"] = pipe.get("expected_po", "") or pval
                        proj["value"] = ""
                        warnings.append(f"[ONTOLOGY] Reclassified projection '{pval}' as {cat.value}")

    structured_data["traction"] = tr
    structured_data["revenue_details"] = rd
    structured_data["pipeline"] = pipe
    structured_data["funding"] = fund
    structured_data["industry_overview"] = ind
    structured_data["additional_metrics"] = additional
    structured_data["_canonical_overrides"] = overrides
    structured_data["_validation_warnings"] = warnings
    return structured_data


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_financials(structured_data: dict, context: str = "") -> dict:
    warnings: List[str] = structured_data.get("_validation_warnings", [])
    flagged: Dict = structured_data.get("_flagged_metrics", {})
    if not isinstance(flagged, dict):
        flagged = {}

    # Run all 5 sub-modules
    _semantic_classifier(structured_data, context, warnings, flagged)
    _cross_field_rules(structured_data, warnings, flagged)
    _entity_classifier(structured_data, context, warnings, flagged)
    _projection_classifier(structured_data, context, warnings, flagged)
    _missing_detector(structured_data, context, warnings, flagged)
    _deterministic_rules(structured_data, warnings, flagged)

    # Auto-fixes
    # Rigid auto-fix for TAM >= SAM >= SOM
    try:
        ind = structured_data.get("industry_overview", {}) or {}
        tam_raw = str(ind.get("tam", "") or "")
        sam_raw = str(ind.get("sam", "") or "")
        som_raw = str(ind.get("som", "") or "")
        
        tam_num = _normalize_indian(tam_raw)
        sam_num = _normalize_indian(sam_raw)
        som_num = _normalize_indian(som_raw)
        
        market_sizes = []
        if tam_num > 0: market_sizes.append(("tam", tam_num, tam_raw))
        if sam_num > 0: market_sizes.append(("sam", sam_num, sam_raw))
        if som_num > 0: market_sizes.append(("som", som_num, som_raw))
        
        if len(market_sizes) >= 2:
            sorted_sizes = sorted(market_sizes, key=lambda x: x[1], reverse=True)
            expected_keys = sorted([x[0] for x in market_sizes], key=lambda x: {"tam": 0, "sam": 1, "som": 2}[x])
            sorted_keys = [x[0] for x in sorted_sizes]
            
            if sorted_keys != expected_keys:
                for i, target_key in enumerate(expected_keys):
                    ind[target_key] = sorted_sizes[i][2]
                warnings.append(f"[SANITY] Rigid TAM/SAM/SOM hierarchy violation auto-corrected: sorted {sorted_keys} into expected {expected_keys}")
                structured_data["industry_overview"] = ind
    except Exception as ex:
        print(f"[SANITY] Failed to apply TAM/SAM/SOM auto-correction: {ex}")

    _auto_fix_bare_numbers(structured_data, warnings)
    _ensure_fy_on_market_sizes(structured_data)

    # Ontological re-classification — moves data to correct fields
    structured_data = ontological_reclassifier(structured_data, context)

    structured_data["_validation_warnings"] = warnings
    structured_data["_flagged_metrics"] = flagged
    return structured_data
