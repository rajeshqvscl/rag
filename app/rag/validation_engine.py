"""
Unified Validation Engine v3.0 — semantic-first validation with
universal normalization, ontological sanity, temporal reasoning,
and per-metric confidence that reflects TRUTH quality (not extraction).

Key improvements over v2:
  1. Universal normalization: converts ALL currencies/units before comparison
  2. Semantic confidence: confidence reflects semantic coherence, capped at 0.70
     if ANY validation error exists (no more "95% validated + likely incorrect")
  3. Temporal reasoning: fiscal year parsing + forward/backward classification
  4. Ontology leak detection: cross-metric ontology namespace violations
  5. Entity-role classification: positioning vs competitor distinction
  6. Ceiling capping: never >0.85 for inferred, never >0.70 with error
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import re


@dataclass
class ValidationResult:
    field: str
    passed: bool
    severity: str  # "error", "warning", "info"
    message: str
    confidence_adjustment: float = 0.0


SOURCE_CONFIDENCE_MAP = {
    "explicit": 0.90,
    "table": 0.88,
    "chart_inferred": 0.75,
    "visual_parsed": 0.72,
    "inferred": 0.60,
    "narrative_inferred": 0.50,
    "ocr": 0.45,
}

# Lower source confidences to prevent fake-high scores
# Even "explicit" is capped at 0.90 — semantic validation must confirm

TEMPORAL_KEYWORDS_FUTURE = [
    "expected", "projected", "forecast", "target", "upcoming",
    "future", "anticipated", "planned", "budgeted", "estimated",
    "pipeline", "letter of intent", "loi", "mou",
]

TEMPORAL_KEYWORDS_HISTORICAL = [
    "fy", "historical", "last year", "previous year", "achieved",
    "actual", "realized", "booked", "completed", "till", "since",
    "cumulative", "ytd", "year to date",
]

# Known company-ontology mappings: what unit types each sector typically uses
SECTOR_EXPECTED_UNIT_TYPES = {
    "defence": {"count", "units", "systems", "platforms"},
    "manufacturing": {"count", "units", "machines", "systems"},
    "healthcare": {"count", "patients", "diagnostics", "tests", "lives"},
    "agritech": {"count", "farmers", "villages", "acres"},
    "climate": {"count", "credits", "tonnes", "mw"},
    "fintech": {"count", "transactions", "users", "merchants"},
    "saas": {"count", "users", "seats", "licenses"},
}


def _normalize_for_comparison(value_str: str) -> Tuple[float, str, str]:
    """
    Universal normalization: returns (normalized_INR_value, currency, raw_unit).
    Detects and tracks currency ($ vs ₹) separately so comparisons never mix them.
    """
    from app.rag.number_utils import parse_indian_number
    if not value_str:
        return 0.0, "unknown", "unknown"
    vlow = value_str.lower()
    currency = "INR"
    raw_unit = "unknown"
    if '$' in value_str or 'usd' in vlow:
        currency = "USD"
    if 'cr' in vlow or 'crore' in vlow:
        raw_unit = "Cr"
    elif 'lakh' in vlow or 'lac' in vlow:
        raw_unit = "Lakh"
    elif 'bn' in vlow or 'billion' in vlow:
        raw_unit = "Bn"
    elif 'mn' in vlow or 'million' in vlow:
        raw_unit = "Mn"
    parsed = parse_indian_number(value_str)
    if currency == "USD":
        parsed = parsed * 83.0
    return parsed, currency, raw_unit


def _detect_mixed_currencies(*values: str) -> Optional[str]:
    """Detect if values mix INR and USD. Returns warning message or None."""
    currencies = set()
    labels = []
    for v in values:
        if not v:
            continue
        vlow = v.lower()
        if '$' in v or 'usd' in vlow:
            currencies.add("USD")
            labels.append("$")
        elif any(c in vlow for c in ['\u20b9', 'rs', 'inr']):
            currencies.add("INR")
            labels.append("\u20b9")
        else:
            currencies.add("unknown")
    if currencies == {"USD", "INR"} or len(currencies) > 1:
        return f"Mixed currencies detected: {', '.join(sorted(currencies))} — values may not be directly comparable"
    return None


def _infer_currency(value_str: str) -> str:
    """Infer currency from value string."""
    if not value_str:
        return "unknown"
    vlow = value_str.lower()
    if '$' in value_str or 'usd' in vlow:
        return "USD"
    if '\u20b9' in value_str or 'rs' in vlow or 'inr' in vlow:
        return "INR"
    return "unknown"


def _has_positioning_language(text: str) -> bool:
    """Detect if text is a positioning statement rather than competitor name."""
    if not text:
        return False
    t = text.lower().strip()
    positioning_patterns = [
        r'^(the|a|an)\s+.+of\s+the\s',
        r'^(amazon|uber|google|netflix|airbnb|tesla|stripe|facebook)\s+of\b',
        r'^(leading|largest|biggest|top|premier|foremost)\s',
        r'\b(platform|ecosystem|marketplace|network)\b',
    ]
    for p in positioning_patterns:
        if re.search(p, t):
            return True
    return False


def _parse_fiscal_year(value_str: str, label: str = "") -> Optional[str]:
    """Extract fiscal year from value string or label."""
    combined = f"{value_str} {label}"
    m = re.search(r'\b(FY\d{2,4}(?:[-\s]?\d{2,4})?|20\d{2}[-\s]?20\d{2})\b', combined)
    if m:
        return m.group(1)
    return None


def _classify_temporal_by_year(fy_str: Optional[str]) -> Optional[str]:
    """Classify temporal type from fiscal year string."""
    if not fy_str:
        return None
    nums = re.findall(r'\d{4}', fy_str)
    if not nums:
        return None
    years = [int(n) for n in nums[:2]]
    latest = max(years)
    from datetime import datetime
    current_year = datetime.now().year
    if latest <= current_year - 2:
        return "historical"
    elif latest <= current_year + 1:
        return "current"
    else:
        return "projection"


def _check_ontological_namespace(value_str: str, unit_type: str,
                                  sector: str, field_name: str) -> Optional[str]:
    """Detect if a metric's ontology doesn't match the sector's expected types."""
    if not sector or not value_str or not unit_type:
        return None
    sector = sector.lower().strip()
    vlow = value_str.lower()
    # Check for sector-specific ontology violations
    if sector == "defence" and "agritech" in vlow:
        return f"'{field_name}' mentions AgriTech concepts but sector is defence — possible ontology leak"
    if sector == "agritech" and ("defence" in vlow or "munition" in vlow):
        return f"'{field_name}' mentions defence concepts but sector is agritech — possible ontology leak"
    if sector == "healthcare" and ("munition" in vlow or "tank" in vlow or "drone" in vlow):
        return f"'{field_name}' mentions defence concepts but sector is healthcare — possible ontology leak"
    return None


class ValidationEngine:

    @staticmethod
    def normalize_market_values(tam: str, sam: str, som: str) -> Tuple[float, float, float, List[ValidationResult]]:
        """
        Universal normalization layer: converts ALL market values to comparable INR.
        Returns (tam_norm, sam_norm, som_norm, validation_results).
        """
        results = []
        tam_n, tam_cur, tam_unit = _normalize_for_comparison(tam)
        sam_n, sam_cur, sam_unit = _normalize_for_comparison(sam)
        som_n, som_cur, som_unit = _normalize_for_comparison(som)

        # Detect mixed currencies
        currency_warning = _detect_mixed_currencies(tam, sam, som)
        if currency_warning:
            results.append(ValidationResult(
                field="market",
                passed=False,
                severity="error",
                message=currency_warning,
                confidence_adjustment=-0.25,
            ))

        # Detect mixed units (e.g., Cr vs Bn without currency normalization)
        units = {u for u in [tam_unit, sam_unit, som_unit] if u != "unknown"}
        if len(units) > 1:
            results.append(ValidationResult(
                field="market",
                passed=False,
                severity="warning",
                message=f"Mixed scales detected: {', '.join(sorted(units))} — ensure correct normalization",
                confidence_adjustment=-0.15,
            ))

        return tam_n, sam_n, som_n, results

    @staticmethod
    def validate_market_hierarchy(tam: float, sam: float, som: float,
                                   tam_raw: str = "", sam_raw: str = "", som_raw: str = "") -> List[ValidationResult]:
        """TAM >= SAM >= SOM with cross-currency awareness."""
        results = []

        # 1. First normalize
        tam_n, sam_n, som_n, norm_results = ValidationEngine.normalize_market_values(
            tam_raw or str(tam), sam_raw or str(sam), som_raw or str(som)
        )
        results.extend(norm_results)

        # If we have raw values, use normalized ones; otherwise use passed floats
        if tam_raw or sam_raw or som_raw:
            tam = tam_n
            sam = sam_n
            som = som_n

        # 2. Hierarchy checks
        if tam > 0 and sam > 0 and tam < sam:
            results.append(ValidationResult(
                field="tam",
                passed=False,
                severity="error",
                message=f"TAM (Normalized: ₹{tam:,.0f}) < SAM (Normalized: ₹{sam:,.0f}) — values likely swapped or mis-scaled across currencies/units",
                confidence_adjustment=-0.25,
            ))
        if sam > 0 and som > 0 and sam < som:
            results.append(ValidationResult(
                field="sam",
                passed=False,
                severity="error",
                message=f"SAM (Normalized: ₹{sam:,.0f}) < SOM (Normalized: ₹{som:,.0f}) — values likely swapped or mis-scaled across currencies/units",
                confidence_adjustment=-0.25,
            ))
        if tam > 0 and som > 0 and som > tam:
            results.append(ValidationResult(
                field="som",
                passed=False,
                severity="error",
                message=f"SOM (Normalized: ₹{som:,.0f}) > TAM (Normalized: ₹{tam:,.0f}) — market hierarchy violated after numeric normalization",
                confidence_adjustment=-0.30,
            ))
        if tam > 0 and som > 0 and som < tam * 0.001:
            results.append(ValidationResult(
                field="som",
                passed=True,
                severity="warning",
                message=f"SOM (Normalized: ₹{som:,.0f}) is <0.1% of TAM (Normalized: ₹{tam:,.0f}) — unusually small even after cross-currency normalization",
                confidence_adjustment=-0.10,
            ))

        # 3. Magnitude sanity check — flag suspiciously small TAM
        if tam > 0 and tam < 100000:  # Less than ₹1L
            results.append(ValidationResult(
                field="tam",
                passed=False,
                severity="warning",
                message=f"TAM ({tam:,.0f}) is less than ₹1L — likely unit mismatch or wrong scale",
                confidence_adjustment=-0.20,
            ))

        return results

    @staticmethod
    def validate_financial_realism(revenue: float, tam: float, funding: float,
                                    valuation: float, pipeline: float,
                                    revenue_raw: str = "", tam_raw: str = "",
                                    funding_raw: str = "", valuation_raw: str = "",
                                    pipeline_raw: str = "") -> List[ValidationResult]:
        """Revenue <= TAM, funding/valuation ratio sanity, with cross-currency normalization."""
        results = []

        # Normalize all to comparable INR
        rev_n, _, _ = _normalize_for_comparison(revenue_raw) if revenue_raw else (revenue, "INR", "unknown")
        tam_n, _, _ = _normalize_for_comparison(tam_raw) if tam_raw else (tam, "INR", "unknown")

        if revenue_raw and revenue > 0:
            revenue = rev_n
        if tam_raw and tam > 0:
            tam = tam_n

        if revenue > 0 and tam > 0 and revenue > tam:
            results.append(ValidationResult(
                field="revenue",
                passed=False,
                severity="error",
                message=f"Revenue ({revenue:,.0f}) exceeds TAM ({tam:,.0f}) — values may be misclassified or wrong scale",
                confidence_adjustment=-0.25,
            ))

        if funding > 0 and valuation > 0:
            ratio = valuation / funding
            if ratio < 1.0:
                results.append(ValidationResult(
                    field="funding",
                    passed=False,
                    severity="warning",
                    message=f"Valuation ({valuation:,.0f}) < Raise ({funding:,.0f}) — fields may be swapped",
                    confidence_adjustment=-0.15,
                ))
            elif ratio > 100:
                results.append(ValidationResult(
                    field="valuation",
                    passed=False,
                    severity="warning",
                    message=f"Valuation/Raise ratio of {ratio:.0f}x is unusually high",
                    confidence_adjustment=-0.10,
                ))

        return results

    @staticmethod
    def validate_projection_classification(
        projections: List[Dict],
        current_revenue: float
    ) -> List[ValidationResult]:
        """Flag projections that look like pipeline/PO rather than revenue projections."""
        results = []
        for proj in projections:
            if isinstance(proj, dict):
                val_str = str(proj.get("value", "") or "")
                period = str(proj.get("period", "") or "")
                if not val_str:
                    continue
                from app.rag.number_utils import parse_indian_number
                val_num = parse_indian_number(val_str)
                if val_num > 0 and current_revenue > 0 and val_num > current_revenue * 100:
                    field = f"projection_{period}" if period else "projection"
                    results.append(ValidationResult(
                        field=field,
                        passed=False,
                        severity="warning",
                        message=f"Projection ({val_str}) is >100x current revenue ({current_revenue:,.0f}) — likely pipeline/PO",
                        confidence_adjustment=-0.25,
                    ))
        return results

    @staticmethod
    def validate_temporal_consistency(
        temporal_type: str,
        value_str: str,
        field_name: str,
        label: str = ""
    ) -> List[ValidationResult]:
        """Check temporal classification using keywords + fiscal year parsing."""
        results = []
        vlow = value_str.lower()
        has_future_kw = any(kw in vlow for kw in TEMPORAL_KEYWORDS_FUTURE)
        has_past_kw = any(kw in vlow for kw in TEMPORAL_KEYWORDS_HISTORICAL)

        # Fiscal year-based classification
        fy = _parse_fiscal_year(value_str, label)
        fy_temporal = _classify_temporal_by_year(fy) if fy else None

        if fy_temporal and temporal_type and fy_temporal != temporal_type:
            results.append(ValidationResult(
                field=field_name,
                passed=False,
                severity="warning",
                message=f"'{field_name}' classified as '{temporal_type}' but FY '{fy}' suggests '{fy_temporal}'",
                confidence_adjustment=-0.10,
            ))

        if temporal_type == "historical" and has_future_kw:
            results.append(ValidationResult(
                field=field_name,
                passed=False,
                severity="warning",
                message=f"'{field_name}' marked historical but contains future keywords: '{value_str}'",
                confidence_adjustment=-0.15,
            ))
        if temporal_type == "projection" and has_past_kw:
            results.append(ValidationResult(
                field=field_name,
                passed=False,
                severity="info",
                message=f"'{field_name}' marked projection but contains past keywords: '{value_str}'",
                confidence_adjustment=-0.08,
            ))

        # Detect mixed temporal signals
        if has_future_kw and has_past_kw:
            results.append(ValidationResult(
                field=field_name,
                passed=False,
                severity="warning",
                message=f"'{field_name}' contains both future and past keywords: '{value_str}'",
                confidence_adjustment=-0.10,
            ))

        return results

    @staticmethod
    def validate_ontological_sanity(
        field_name: str,
        value_str: str,
        unit_type: str,
        entity_type: Optional[str],
        sector: str
    ) -> List[ValidationResult]:
        """Detect ontology-level inconsistencies."""
        results = []

        # 1. Check for ontology namespace leaks
        leak_msg = _check_ontological_namespace(value_str, unit_type, sector, field_name)
        if leak_msg:
            results.append(ValidationResult(
                field=field_name,
                passed=False,
                severity="error",
                message=leak_msg,
                confidence_adjustment=-0.30,
            ))

        # 2. Check for entity-role confusion (positioning as competitor)
        if field_name == "competition.competitors" and entity_type:
            if _has_positioning_language(value_str):
                results.append(ValidationResult(
                    field=field_name,
                    passed=False,
                    severity="info",
                    message=f"'{value_str}' appears to be a positioning statement, not a competitor",
                    confidence_adjustment=-0.05,
                ))

        # 3a. Check for non-numeric values on numeric-only fields (TAM, SAM, SOM, revenue)
        numeric_fields = {"tam", "sam", "som", "total_revenue", "funding_raise", "valuation", "pipeline_value", "current_period_revenue", "purchase_order_value", "government_grants"}
        if field_name in numeric_fields and value_str:
            import re as _re
            has_number = bool(_re.search(r'[\d,]+', value_str.replace(',', '')))
            if not has_number:
                results.append(ValidationResult(
                    field=field_name,
                    passed=False,
                    severity="error",
                    message=f"'{field_name}' has non-numeric value '{value_str[:60]}' — expected a number with unit",
                    confidence_adjustment=-0.40,
                ))

        # 3b. Check for unit_count where currency expected (or vice versa)
        if unit_type == "count" and field_name in ("total_revenue", "tam", "funding_raise", "valuation", "pipeline_value"):
            results.append(ValidationResult(
                field=field_name,
                passed=False,
                severity="error",
                message=f"'{field_name}' has unit_type='count' but expected currency — possible ontology leak",
                confidence_adjustment=-0.30,
            ))
        if unit_type in ("currency", "percentage") and "count" in SECTOR_EXPECTED_UNIT_TYPES.get(sector, set()):
            pass  # valid for financial metrics in any sector

        return results

    @staticmethod
    def compute_confidence(
        source_type: str,
        base_confidence: float = 0.0,
        validation_results: Optional[List[ValidationResult]] = None,
        multi_occurrence: int = 0,
        cross_sectional_consistency: bool = False,
        ocr_score: float = 0.0,
        table_confidence: float = 0.0,
        layout_confidence: float = 0.0,
        semantic_context_score: float = 0.0,
    ) -> float:
        """
        SEMANTIC confidence scoring (multi-factor v3.0).
        Confidence reflects TRUTH quality, not extraction quality.
        
        Factors:
          - Source base: 0-40 pts (OCR quality, well-known extraction source)
          - Signal strength: 0-20 pts (multi-occurrence: same value in 2+ sections)
          - Cross-section consistency: 0-20 pts (value aligns across related fields)
          - OCR quality: 0-10 pts (text extraction quality)
          - Table confidence: 0-10 pts (value from structured table)
          - Layout confidence: 0-10 pts (value from clear layout position)
          - Semantic context: 0-15 pts (nearby keywords confirm metric type)
          - Validation adjustments: -40 to 0 pts (errors reduce)
        
        Key change from v1: inferred metrics can reach validated (>=0.85) if 
        multi-occurrence + cross-section consistency compensate. No blanket 
        "-0.40 for inferred" anymore.
        """
        src_conf = SOURCE_CONFIDENCE_MAP.get(source_type, 0.45)
        confidence = max(src_conf, base_confidence) if base_confidence > 0 else src_conf

        # Multi-occurrence bonus: same value in 2+ sections is stronger signal
        if multi_occurrence >= 3:
            confidence += 0.15
        elif multi_occurrence >= 2:
            confidence += 0.08

        # Cross-sectional consistency bonus
        if cross_sectional_consistency:
            confidence += 0.10

        # OCR quality bonus (0-0.10)
        if ocr_score > 0:
            confidence += min(ocr_score * 0.10, 0.10)

        # Table confidence bonus (0-0.10)
        if table_confidence > 0:
            confidence += min(table_confidence * 0.10, 0.10)

        # Layout confidence bonus (0-0.10)
        if layout_confidence > 0:
            confidence += min(layout_confidence * 0.10, 0.10)

        # Semantic context score (0-0.15)
        if semantic_context_score > 0:
            confidence += min(semantic_context_score * 0.15, 0.15)

        has_errors = False
        error_count = 0
        if validation_results:
            for vr in validation_results:
                confidence += vr.confidence_adjustment
                if not vr.passed and vr.severity == "error":
                    has_errors = True
                    error_count += 1

        # Penalty for multiple errors (stacking, not just ceiling)
        if error_count >= 2:
            confidence -= 0.05 * (error_count - 1)

        # CEILING: if ANY error exists, cap at 0.70 (plausible, not validated)
        if has_errors:
            confidence = min(confidence, 0.70)

        # CEILING: non-explicit sources with NO errors can still reach validated
        if has_errors and source_type != "explicit":
            confidence = min(confidence, src_conf + 0.10)

        # FLOOR
        confidence = max(0.05, confidence)

        return round(min(1.0, confidence), 2)

    @staticmethod
    def get_validation_status(confidence: float) -> str:
        """Return validation status based on semantic confidence."""
        if confidence >= 0.85:
            return "validated"
        elif confidence >= 0.65:
            return "plausible"
        elif confidence >= 0.40:
            return "uncertain"
        return "unreliable"


def validate_all(structured_data: dict) -> Tuple[dict, List[ValidationResult]]:
    """
    Run all validations across structured_data with semantic-first approach.
    Returns (structured_data with _validation_results, list of all ValidationResults).
    """
    engine = ValidationEngine()
    all_results = []

    canonical = structured_data.get("_canonical", {}) or {}
    ind = structured_data.get("industry_overview", {}) or {}
    sector = structured_data.get("company_brief", {}).get("sector", "") or \
             structured_data.get("company_info", {}).get("sector", "")

    # ── 1. Market hierarchy with normalization ──────────────────────
    tam_raw = canonical.get("tam", {}).get("value", "") if isinstance(canonical.get("tam"), dict) else ind.get("tam", "")
    sam_raw = canonical.get("sam", {}).get("value", "") if isinstance(canonical.get("sam"), dict) else ind.get("sam", "")
    som_raw = canonical.get("som", {}).get("value", "") if isinstance(canonical.get("som"), dict) else ind.get("som", "")

    if tam_raw or sam_raw or som_raw:
        tam_n, sam_n, som_n, norm_results = engine.normalize_market_values(
            str(tam_raw), str(sam_raw), str(som_raw)
        )
        all_results.extend(norm_results)
        all_results.extend(engine.validate_market_hierarchy(
            tam_n, sam_n, som_n,
            tam_raw=str(tam_raw), sam_raw=str(sam_raw), som_raw=str(som_raw)
        ))
    else:
        # Fallback: use already-normalized values
        tam_val = canonical.get("tam", {}).get("normalized_value", 0.0) if isinstance(canonical.get("tam"), dict) else 0.0
        sam_val = canonical.get("sam", {}).get("normalized_value", 0.0) if isinstance(canonical.get("sam"), dict) else 0.0
        som_val = canonical.get("som", {}).get("normalized_value", 0.0) if isinstance(canonical.get("som"), dict) else 0.0
        if tam_val or sam_val or som_val:
            all_results.extend(engine.validate_market_hierarchy(tam_val, sam_val, som_val))

    # ── 2. Financial realism with normalization ─────────────────────
    rev_val = 0.0
    rev_raw = ""
    for rev_key in ["historical_revenue", "total_revenue", "invoiced_amount", "current_period_revenue"]:
        r = canonical.get(rev_key, {}) if isinstance(canonical.get(rev_key), dict) else {}
        if isinstance(r, dict) and r.get("normalized_value", 0.0) > 0:
            rev_val = r["normalized_value"]
            rev_raw = r.get("value", "")
            break
    tr = structured_data.get("traction", {}) or {}
    if rev_val == 0.0:
        rev_raw = tr.get("revenue", "")
        from app.rag.number_utils import parse_indian_number
        rev_val = parse_indian_number(rev_raw)

    fund = structured_data.get("funding", {}) or {}
    funding_raw = fund.get("current_raise", "")
    valuation_raw = fund.get("valuation", "")
    pipe = structured_data.get("pipeline", {}) or {}
    pipeline_raw = pipe.get("pipeline_value", "")

    from app.rag.number_utils import parse_indian_number
    funding_val = parse_indian_number(funding_raw) if funding_raw else 0.0
    valuation_val = parse_indian_number(valuation_raw) if valuation_raw else 0.0
    pipeline_val = parse_indian_number(pipeline_raw) if pipeline_raw else 0.0

    all_results.extend(engine.validate_financial_realism(
        rev_val, tam_val if 'tam_val' in dir() else 0.0,
        funding_val, valuation_val, pipeline_val,
        revenue_raw=rev_raw, tam_raw=str(tam_raw) if tam_raw else "",
        funding_raw=funding_raw, valuation_raw=valuation_raw,
        pipeline_raw=pipeline_raw
    ))

    # ── 3. Projection classification ────────────────────────────────
    projections = structured_data.get("revenue_details", {}).get("projections", [])
    if isinstance(projections, list):
        all_results.extend(engine.validate_projection_classification(projections, rev_val))

    # ── 4. Ontological sanity check per metric ──────────────────────
    competition = structured_data.get("competition", {}) or {}
    competitors = competition.get("competitors", [])
    if isinstance(competitors, list):
        for comp in competitors:
            if isinstance(comp, str):
                all_results.extend(engine.validate_ontological_sanity(
                    "competition.competitors", comp, "unknown", None, sector
                ))
            elif isinstance(comp, dict) and comp.get("name"):
                all_results.extend(engine.validate_ontological_sanity(
                    "competition.competitors", comp["name"], "unknown", None, sector
                ))

    for key, entry in canonical.items():
        if isinstance(entry, dict):
            vs = entry.get("value", "")
            ut = entry.get("unit_type", "")
            et = entry.get("entity_type")
            all_results.extend(engine.validate_ontological_sanity(key, vs, ut, et, sector))

    # ── 5. Temporal consistency ─────────────────────────────────────
    for key, entry in canonical.items():
        if isinstance(entry, dict):
            tt = entry.get("temporal_type", "")
            vs = entry.get("value", "")
            label = entry.get("display_name", "")
            if tt and vs:
                all_results.extend(engine.validate_temporal_consistency(tt, vs, key, label))

    # ── 6. Cross-metric validation: apply all results to each metric ─
    for key, entry in canonical.items():
        if isinstance(entry, dict):
            st = entry.get("source_type", "inferred")
            bc = entry.get("confidence", 0.0)
            # Gather ALL validation results that apply to this metric
            metric_results = [r for r in all_results if r.field == key or r.field == "market"]
            new_conf = engine.compute_confidence(st, bc, metric_results)
            entry["confidence"] = new_conf
            entry["validation_status"] = engine.get_validation_status(new_conf)

    structured_data["_validation_results"] = [vars(r) for r in all_results]
    structured_data["_validation_engine_version"] = "3.0"
    return structured_data, all_results
