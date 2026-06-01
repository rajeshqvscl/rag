"""
Shared rendering utilities: null guards, completeness scoring, semantic compression.
"""

import re
from typing import List, Dict, Optional, Any, Tuple


def safe(value: Any, fallback: str = "Not explicitly stated") -> str:
    """Null guard — never allow empty values to reach rendered output.
    Unpacks metric dictionaries and lists to prevent raw dict leakage."""
    if value is None:
        return fallback
    if isinstance(value, dict):
        value = value.get("value") or value.get("display_value") or value.get("value_str") or str(value)
    elif isinstance(value, list):
        value = ", ".join(safe(item, "") for item in value if item is not None)
    s = str(value).strip()
    if not s or s.lower() in ("", "null", "none", "n/a", "not provided", "unknown"):
        return fallback
    return s


def get_val(value: Any) -> str:
    """Safely unpacks metric dictionaries/lists to clean primitive strings.
    If the value is a dictionary or list, extracts its flat display value."""
    if value is None:
        return ""
    if isinstance(value, dict):
        v = value.get("value") or value.get("display_value") or value.get("value_str")
        if v is not None:
            return str(v).strip()
        # Fall back to checking common keys
        for k in ["value", "display_value", "value_str", "text"]:
            if k in value and value[k] is not None:
                return str(value[k]).strip()
        return str(value).strip()
    if isinstance(value, list):
        return ", ".join(get_val(item) for item in value if item is not None)
    return str(value).strip()


def safe_join(parts: List[str], sep: str = " ") -> str:
    """Join non-empty string parts with separator."""
    return sep.join(p for p in parts if p and p.strip())



def join_clauses(clauses: List[str]) -> str:
    """'A', 'B', 'C' → 'A, B, and C'"""
    if not clauses:
        return ""
    cleaned = [c for c in clauses if c and c.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _filter_empty_clause_parts(clauses: List[str]) -> List[str]:
    """Remove clauses that end with empty template slots or are single-word orphans."""
    filtered = []
    for c in clauses:
        stripped = c.strip().rstrip(",").strip()
        if not stripped:
            continue
        if re.search(r'\b(of|by|with|from|using)\s*$', stripped, re.IGNORECASE):
            continue
        if len(stripped.split()) <= 1:
            continue
        filtered.append(stripped)
    return filtered


def completeness_score(data: dict, required_fields: List[str]) -> float:
    """Score 0.0–1.0 for how complete a section's data is."""
    if not data:
        return 0.0
    filled = 0
    for field in required_fields:
        val = data.get(field)
        if isinstance(val, str) and val.strip():
            filled += 1
        elif isinstance(val, (list, dict)) and val:
            filled += 1
        elif val not in (None, "", [], {}):
            filled += 1
    return filled / max(len(required_fields), 1)


def semantic_compress(bullets: List[str], context_hint: str = "") -> str:
    """Compress multiple bullet points into a concise summary sentence.
    When context_hint is provided (e.g. company name + sector), builds a
    coherent sentence instead of concatenating bullets."""
    if not bullets:
        return ""
    if len(bullets) == 1:
        return bullets[0].rstrip(".") + "."
    if context_hint:
        return f"{context_hint}: {'; '.join(b.strip().rstrip('.') for b in bullets[:3])}."
    return ". ".join(b.strip().rstrip(".").capitalize() for b in bullets[:3]) + "."


_PRONOM_PAT = re.compile(r'^(they|it|he|she|them|these|those|we|you|i)\W*$', re.IGNORECASE)


def filter_competitors(competitors: List[str]) -> List[str]:
    """Filter pronouns and short fragments from competitor lists."""
    result = []
    for c in competitors:
        s = str(c).strip()
        if len(s) > 2 and not _PRONOM_PAT.match(s):
            result.append(s)
    return result[:5]


def fmt_period_short(period: str) -> str:
    """Convert period string to compact display: FY2026 -> FY25-26"""
    if not period:
        return ""
    p = period.strip()
    qm = re.search(r'(Q[1-4])[\s\-]*(?:FY[\s\-]*)?(\d{2,4})', p, re.IGNORECASE)
    if qm:
        yr = qm.group(2)
        if len(yr) == 2:
            yr = f"20{yr}"
        prev = (int(yr[-2:]) - 1) % 100
        return f"{qm.group(1).upper()} FY{prev:02d}-{yr[-2:]}"
    fm = re.search(r'FY[\s\-]*(\d{2,4})', p, re.IGNORECASE)
    if fm:
        yr = fm.group(1)
        if len(yr) == 2:
            yr = f"20{yr}"
        prev = (int(yr[-2:]) - 1) % 100
        return f"FY{prev:02d}-{yr[-2:]}"
    ym = re.search(r'\b(20\d{2})\b', p)
    if ym:
        yr = ym.group(1)
        prev = (int(yr[-2:]) - 1) % 100
        return f"FY{prev:02d}-{yr[-2:]}"
    return p


def render_full_report(structured_data: dict,
                        field_confidence: Optional[Dict[str, float]] = None,
                        include_sources: bool = False,
                        sector_profile: Optional[dict] = None) -> str:
    """Top-level entry point: renders the full structured_data into markdown.
    Delegates to individual section renderers."""
    from . import (render_company_brief, render_business_overview,
                   render_traction, render_funding, render_pipeline,
                   render_revenue_details, render_industry_overview,
                   render_competitive_landscape, render_recognition,
                   render_problem, render_solution)

    if field_confidence is None:
        field_confidence = structured_data.get("_field_confidence", {})

    brief_data = structured_data.get("company_brief", {})
    biz_data = structured_data.get("business_overview", {})
    ind_data = structured_data.get("industry_overview", {})
    prob_data = structured_data.get("problem", {})
    sol_data = structured_data.get("solution", {})
    tr_data = structured_data.get("traction", {})
    fund_data = structured_data.get("funding", {})
    pipe_data = structured_data.get("pipeline", {})
    rd_data = structured_data.get("revenue_details", {})
    comp_data = structured_data.get("competition", {})
    rec_data = structured_data.get("recognition", {})
    canonical = structured_data.get("_canonical", {}) or {}

    output = []

    # 1. COMPANY BRIEF
    output.append("### COMPANY BRIEF")
    output.append(f"  {render_company_brief(brief_data, sector_profile)}")
    output.append("")

    # 2. BUSINESS OVERVIEW
    output.append("### BUSINESS OVERVIEW")
    biz_rendered = render_business_overview(biz_data, field_confidence, sector_profile)
    output.append(f"  {biz_rendered}" if biz_rendered else "  Business model and operations not explicitly stated in the deck.")
    output.append("")

    # 3. INDUSTRY OVERVIEW
    output.append("### INDUSTRY OVERVIEW")
    ind_rendered = render_industry_overview(ind_data, field_confidence, sector_profile)
    output.append(f"  {ind_rendered}" if ind_rendered else "  Market sizing (TAM/SAM/SOM) not explicitly defined in the deck.")
    output.append("")

    # 4. PROBLEM
    output.append("### PROBLEM STATEMENT")
    prob_rendered = render_problem(prob_data)
    output.append(f"  {prob_rendered}" if prob_rendered else "  Problem context being inferred from available data.")
    output.append("")

    # 5. SOLUTION
    output.append("### SOLUTION")
    sol_rendered = render_solution(sol_data)
    output.append(f"  {sol_rendered}" if sol_rendered else "  Solution being inferred from available data.")
    output.append("")

    # 6. TRACTION
    output.append("### TRACTION & VALIDATION")
    tr_rendered = render_traction(tr_data, canonical, field_confidence, sector_profile)
    output.append(f"  {tr_rendered}" if tr_rendered else "  Traction metrics not explicitly stated in the deck.")
    output.append("")

    # 7. FUNDING
    output.append("### FUNDING & INVESTMENT HISTORY")
    fund_rendered = render_funding(fund_data, field_confidence, sector_profile)
    output.append(f"  {fund_rendered}" if fund_rendered else "  Funding details not explicitly stated in the deck.")
    output.append("")

    # 8. PIPELINE
    output.append("### PIPELINE")
    pipe_rendered = render_pipeline(pipe_data, field_confidence, sector_profile)
    output.append(f"  {pipe_rendered}" if pipe_rendered else "  Pipeline information not explicitly stated in the deck.")
    output.append("")

    # 9. REVENUE DETAILS (only if non-empty)
    rd_rendered = render_revenue_details(rd_data, canonical)
    if rd_rendered:
        output.append("### REVENUE DETAILS")
        output.append(f"  {rd_rendered}")
        output.append("")

    # 10. COMPETITIVE LANDSCAPE
    output.append("### COMPETITIVE LANDSCAPE")
    cc_rendered = render_competitive_landscape(comp_data, sector_profile)
    output.append(f"  {cc_rendered}" if cc_rendered else "  No explicit competitors identified in the deck.")
    output.append("")

    # 11. AWARDS & RECOGNITION
    output.append("### AWARDS & RECOGNITION")
    rec_rendered = render_recognition(rec_data)
    output.append(f"  {rec_rendered}" if rec_rendered else "  Recognition and media coverage details not explicitly captured from the deck content.")
    output.append("")

    # DATA QUALITY NOTES
    warnings = structured_data.get("_validation_warnings", [])
    if warnings:
        from app.rag.semantic_narrative import improve_warning
        output.append("### DATA QUALITY NOTES")
        unique = list(dict.fromkeys(warnings))
        for w in unique:
            output.append(f"- {improve_warning(w)}")
        output.append("")

    return "\n".join(output)
