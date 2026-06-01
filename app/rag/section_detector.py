"""
Page-level section classifier.
Determines which section(s) each page belongs to using keyword scoring,
heading analysis, and layout metadata. Enables field-specific extraction agents.
"""
import re
from typing import Dict, List, Tuple


SECTION_PROFILES = {
    "team": {
        "keywords": ["founder", "ceo", "cto", "coo", "advisor", "team", "management",
                     "iit", "iim", "experience", "background", "alumni", "leadership",
                     "board", "director", "chief", "head of"],
        "weight": 1.0,
    },
    "market": {
        "keywords": ["market", "tam", "sam", "som", "opportunity", "industry", "size",
                     "addressable", "total addressable", "serviceable", "segment",
                     "billion", "trillion", "market share", "market size", "growth",
                     "white space", "gap", "trend", "landscape"],
        "weight": 1.2,
    },
    "product": {
        "keywords": ["product", "platform", "technology", "solution", "feature",
                     "architecture", "pipeline", "tech stack", "ai", "ml", "algorithm",
                     "patent", "ip", "proprietary", "innovation", "roadmap"],
        "weight": 1.0,
    },
    "traction": {
        "keywords": ["traction", "milestone", "customer", "revenue", "growth",
                     "user", "client", "pilot", "deployment", "partner", "adoption",
                     "download", "signup", "monthly", "annual", "arr", "mrr"],
        "weight": 1.1,
    },
    "financials": {
        "keywords": ["revenue", "profit", "ebitda", "margin", "unit economics",
                     "pricing", "burn", "runway", "cost", "expense", "financial",
                     "p&l", "balance sheet", "cash flow", "projection", "forecast",
                     "income", "arr", "mrr", "cac", "ltv", "churn", "gross margin"],
        "weight": 1.3,
    },
    "funding": {
        "keywords": ["funding", "raising", "investment", "capital", "valuation",
                     "series", "seed", "angel", "round", "investor", "pre-money",
                     "post-money", "dilution", "use of funds", "allocation",
                     "grant", "subsidy", "non-dilutive"],
        "weight": 1.3,
    },
    "competition": {
        "keywords": ["competition", "competitor", "differentiation", "moat",
                     "advantage", "positioning", "landscape", "market position",
                     "competitive", "vs ", "versus", "barrier", "swot"],
        "weight": 1.0,
    },
    "problem": {
        "keywords": ["problem", "pain point", "challenge", "gap", "inefficiency",
                     "frustration", "difficulty", "issue", "lack of", "manual"],
        "weight": 0.8,
    },
    "recognition": {
        "keywords": ["award", "recognition", "achievement", "certification",
                     "winner", "accelerator", "incubator", "featured", "media"],
        "weight": 0.8,
    },
}


_HEADING_PATTERNS = [
    re.compile(r'^(?:TRACTION|TEAM|FUNDING|MARKET|COMPETITION|FINANCIALS|'
               r'USE OF FUNDS|TECHNOLOGY|PRODUCT|SOLUTION|BUSINESS MODEL|'
               r'REVENUE|CUSTOMERS|PARTNERS|INVESTMENT|MILESTONES|PROBLEM|'
               r'RECOGNITION|AWARDS|PIPELINE|ROADMAP|GO TO MARKET)', re.IGNORECASE),
    re.compile(r'^[A-Z][A-Z\s]{5,50}$'),
]


def classify_page(text: str, headings: List[str] = None, page_num: int = 0) -> Dict[str, float]:
    """
    Score a page against all section profiles.
    Returns {section_name: score} dict with normalized scores (0-1).
    """
    if not text:
        return {}
    text_lower = text.lower()
    scores = {}

    for section, profile in SECTION_PROFILES.items():
        score = 0.0
        for kw in profile["keywords"]:
            count = text_lower.count(kw)
            if count > 0:
                score += count * profile["weight"]
        scores[section] = score

    # Boost from headings
    if headings:
        h_lower = " ".join(h.lower() for h in headings)
        for section, profile in SECTION_PROFILES.items():
            if section in h_lower:
                scores[section] = scores.get(section, 0) + 5.0

    # Normalize
    max_score = max(scores.values()) if scores else 1.0
    if max_score > 0:
        scores = {k: round(v / max_score, 3) for k, v in scores.items()}

    return scores


def get_page_sections(text: str, headings: List[str] = None, threshold: float = 0.3,
                      page_num: int = 0) -> List[str]:
    """
    Return list of section names for a page, where score >= threshold.
    """
    scores = classify_page(text, headings, page_num)
    return [sec for sec, score in scores.items() if score >= threshold]


def get_page_section_map(pages: List[dict]) -> Dict[str, List[int]]:
    """
    Given list of page dicts with 'text' and 'headings' fields,
    return {section_name: [page_numbers]}.
    """
    section_map: Dict[str, List[int]] = {}
    for page in pages:
        pn = page.get("page", 0)
        text = page.get("text", "") or page.get("cleaned_text", "")
        headings = page.get("headings", []) or page.get("heading_candidates", [])
        if not text:
            continue
        sections = get_page_sections(text, headings, page_num=pn)
        for sec in sections:
            if sec not in section_map:
                section_map[sec] = []
            section_map[sec].append(pn)
    return section_map


def get_financial_pages(pages: List[dict]) -> List[int]:
    """Return page numbers classified as financials or traction."""
    section_map = get_page_section_map(pages)
    result = []
    for sec in ("financials", "traction", "funding"):
        result.extend(section_map.get(sec, []))
    return sorted(set(result))


def get_market_pages(pages: List[dict]) -> List[int]:
    """Return page numbers classified as market."""
    section_map = get_page_section_map(pages)
    return sorted(set(section_map.get("market", [])))
