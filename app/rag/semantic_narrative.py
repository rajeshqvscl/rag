"""
Semantic Narrative Engine — confidence-aware, sector-aware narrative generation.
Wraps raw extracted data into investor-grade prose with confidence tiers.
"""
import re


def _safe_join(parts, sep=" "):
    return sep.join(p for p in parts if p and p.strip())


def _filter_empty_clause_parts(clauses):
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
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass


_SECTOR_PROFILES = {
    "saas": {
        "keywords": ["saas", "software", "platform", "subscription", "cloud", "b2b", "b2c"],
        "revenue_label": "ARR",
        "narrative_theme": "scalable recurring revenue model with strong unit economics and predictable growth",
        "market_frame": "large addressable software market with digital transformation tailwinds",
        "investor_lens": "indicating capital-efficient growth with potential for durable compounding returns",
    },
    "deeptech": {
        "keywords": ["deeptech", "deep tech", "ai", "ml", "patent", "r&d", "research", "ip", "proprietary"],
        "revenue_label": "revenue",
        "narrative_theme": "IP-driven technology platform with significant R&D moat and government/enterprise validation",
        "market_frame": "high-barrier technology market with strategic national importance",
        "investor_lens": "suggesting strong intellectual property positioning and long-term strategic value creation",
    },
    "healthcare": {
        "keywords": ["health", "healthcare", "diagnostic", "medical", "hospital", "clinic", "wellness", "pharma"],
        "revenue_label": "revenue",
        "narrative_theme": "infrastructure-led healthcare platform with recurring patient/service revenue and regulatory defensibility",
        "market_frame": "large and growing healthcare infrastructure market driven by preventive care and digitization",
        "investor_lens": "pointing to asset-light healthcare delivery with network effects and sticky institutional relationships",
    },
    "defence": {
        "keywords": ["defence", "defense", "military", "government", "drdo", "idel", "security", "surveillance"],
        "revenue_label": "contract value",
        "narrative_theme": "government-contract-led business with long procurement cycles, high entry barriers, and strategic national relevance",
        "market_frame": "high-value government procurement market with multi-year contracting cycles",
        "investor_lens": "reflecting strategic government relationships and non-dilutive revenue streams through long-term contracts",
    },
    "fintech": {
        "keywords": ["fintech", "financial", "payment", "lending", "insurance", "banking", "neobank", "insurtech"],
        "revenue_label": "GMV",
        "narrative_theme": "transaction-driven financial platform with regulatory compliance and scalable payment/lending infrastructure",
        "market_frame": "rapidly digitizing financial services market with favorable regulatory tailwinds",
        "investor_lens": "demonstrating transaction-led growth with potential for high-margin financial service layering",
    },
    "climate": {
        "keywords": ["climate", "renewable", "clean energy", "solar", "wind", "sustainable", "esg", "carbon"],
        "revenue_label": "revenue",
        "narrative_theme": "climate-positive infrastructure platform with policy tailwinds and institutional offtake agreements",
        "market_frame": "accelerating clean energy transition market with strong regulatory and ESG-driven demand",
        "investor_lens": "aligned with global sustainability megatrends and providing climate-adjusted return profiles",
    },
    "agritech": {
        "keywords": ["agritech", "agriculture", "farm", "rural", "crop", "supply chain", "food"],
        "revenue_label": "revenue",
        "narrative_theme": "technology-enabled agricultural platform transforming rural value chains and farm-level productivity",
        "market_frame": "large underserved agricultural market with technology adoption inflection point",
        "investor_lens": "targeting a massive unorganized market with technology-led formalization and efficiency gains",
    },
    "hrtech": {
        "keywords": ["hr", "hiring", "recruitment", "recruiter", "ats", "workforce", "staffing", "onboarding", "bgv", "sourcing", "verification", "hiring platform"],
        "revenue_label": "revenue",
        "narrative_theme": "AI-powered hiring and workforce productivity platform with scalable recruitment workflows, verification infrastructure, and ATS integrations",
        "market_frame": "large and expanding HR automation and recruiter productivity software market",
        "investor_lens": "demonstrating recruiter efficiency gains, rapid sourcing, and automated verification workflows",
    },
    "general": {
        "keywords": [],
        "revenue_label": "revenue",
        "narrative_theme": "technology-enabled platform with early commercial traction and scalable operations",
        "market_frame": "growing end-market with technology adoption tailwinds",
        "investor_lens": "indicating early product-market fit with potential for scalable growth in a large addressable market",
    },
}


def _detect_sector(sector_str: str) -> str:
    """Detect sector from a sector string (often stringified brief dict). Returns profile key."""
    if not sector_str:
        return "general"
    
    # Try to parse or extract fields using simple regex if it is a stringified dict
    tagline = ""
    one_liner = ""
    sector_val = ""
    
    tm = re.search(r"'tagline':\s*['\"](.*?)['\"]", sector_str)
    if tm:
        tagline = tm.group(1).lower()
    om = re.search(r"'one_liner':\s*['\"](.*?)['\"]", sector_str)
    if om:
        one_liner = om.group(1).lower()
    sm = re.search(r"'sector':\s*['\"](.*?)['\"]", sector_str)
    if sm:
        sector_val = sm.group(1).lower()
        
    lower_full = sector_str.lower()
    
    # Priority 1: Tagline / one-liner matching (the most authoritative evidence)
    for sect_key, profile in _SECTOR_PROFILES.items():
        if sect_key == "general":
            continue
        for kw in profile["keywords"]:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if (tagline and re.search(pattern, tagline)) or (one_liner and re.search(pattern, one_liner)):
                return sect_key

    # Priority 2: Keyword match in the text content
    # Count occurrences to find dominant sector
    counts = {k: 0 for k in _SECTOR_PROFILES if k != "general"}
    for sect_key, profile in _SECTOR_PROFILES.items():
        if sect_key == "general":
            continue
        for kw in profile["keywords"]:
            pattern = r'\b' + re.escape(kw) + r'\b'
            matches = re.findall(pattern, lower_full)
            counts[sect_key] += len(matches)
            
    if counts:
        best_sect = max(counts, key=counts.get)
        if counts[best_sect] >= 2:
            return best_sect

    # Priority 3: Declared sector field
    if sector_val:
        for sect_key, profile in _SECTOR_PROFILES.items():
            if sect_key == "general":
                continue
            for kw in profile["keywords"]:
                if kw in sector_val:
                    return sect_key

    # Fallback to standard substring search in lower_full
    for sect_key, profile in _SECTOR_PROFILES.items():
        if sect_key == "general":
            continue
        for kw in profile["keywords"]:
            if kw in lower_full:
                return sect_key
                
    return "general"


def _confidence_tier(score: float) -> str:
    if score >= 0.7:
        return "high"
    elif score >= 0.4:
        return "medium"
    return "low"


def _confidence_prefix(tier: str) -> str:
    return {"high": "", "medium": "The deck suggests that ", "low": "Based on limited available data, "}[tier]


def _missing_data_msg(field_name: str, sector_profile: dict, tier: str = "low") -> str:
    """Generate contextual 'missing data' messages instead of robotic 'not explicitly stated'."""
    if tier == "high":
        return ""
    theme = sector_profile.get("narrative_theme", "technology-enabled platform")
    msgs = {
        "business_overview": {
            "low": f"The deck content suggests a {theme}, though specific business model details, revenue architecture, and operational structure were not fully captured in structured extraction.",
            "medium": f"The company appears to operate as a {theme}, with business model context partially referenced in the deck but not fully structured.",
        },
        "traction": {
            "low": "Specific revenue and traction metrics were not clearly extractable from the available deck content, though the overall business context suggests early-stage commercial activity.",
            "medium": "The deck references operational activity and market engagement, though detailed revenue and traction figures were not fully captured in structured extraction.",
        },
        "funding": {
            "low": "The deck content indicates the company may be exploring fundraising or capital allocation strategies, though detailed funding structure and historical capitalization data were not explicitly extractable from this document.",
            "medium": "Funding-related context was partially referenced in the deck, but specific raise amounts, valuation details, and investor composition were not clearly articulated in the available materials.",
        },
        "pipeline": {
            "low": "Forward-looking business development and contractual pipeline details were not comprehensively captured from the deck, though the company's operating context suggests potential institutional engagement.",
            "medium": "The deck references commercial discussions and potential engagements, though structured pipeline quantification was not fully extractable from the available context.",
        },
        "revenue_details": {
            "low": "Detailed revenue breakdown and historical financial performance data were not explicitly presented in a structured format within the deck materials.",
            "medium": "Revenue-related context was identified in the deck, but temporal financial data and period-over-period comparisons were not fully captured in the extraction process.",
        },
        "competitive": {
            "low": "Competitive positioning and market landscape details were not comprehensively captured from the available deck content.",
            "medium": "The deck references the competitive environment, though detailed competitor analysis and market positioning data were not fully structured in the extraction.",
        },
        "market": {
            "low": "Market size data and industry context were referenced in the deck, though specific TAM/SAM/SOM quantification and supporting data sources were not fully captured.",
            "medium": "The deck provides market context and industry positioning, though structured market sizing with clear TAM/SAM/SOM breakdowns was not comprehensively extracted.",
        },
    }
    msg = msgs.get(field_name, {}).get(tier, "")
    if msg:
        return msg
    theme_msg = sector_profile.get("narrative_theme", "")
    if theme_msg and field_name in ("solution", "problem"):
        return f"Specific {field_name.replace('_', ' ')} details were not explicitly articulated in the deck, though the operating context suggests {theme_msg}."
    return f"{field_name.replace('_', ' ').title()} details were not explicitly stated in the available deck content."


def generate_rich_company_brief(brief: dict, sector_profile: dict) -> str:
    """Generate 2-3 line investor-grade company description from brief data."""
    name = str(brief.get("name", "") or "").strip()
    tagline = str(brief.get("tagline", "") or "").strip()
    one_liner = str(brief.get("one_liner", "") or "").strip()
    stage = str(brief.get("stage", "") or "").strip()
    sector = str(brief.get("sector", "") or "").strip()
    biz_model = str(brief.get("business_model", "") or brief.get("model", "") or "").strip()
    revenue_model = str(brief.get("revenue_model", "") or "").strip()

    parts = []
    if name:
        line = name

        # Stage
        if stage:
            sl = stage.lower()
            if "series" in sl:
                sm = re.search(r'series\s*([a-z])', sl)
                if sm:
                    line += f" (Series {sm.group(1).upper()})"
            elif "seed" in sl:
                line += " (Seed)"
            elif "growth" in sl:
                line += " (Growth Stage)"
            else:
                line += f" ({stage.title()})"

        # Sector
        if sector:
            line += f" | {sector.title()}"

        parts.append(line)

    # Thematic description — combine tagline + one_liner + sector theme
    theme = sector_profile.get("narrative_theme", "technology-enabled platform with early commercial traction")
    desc_parts = []
    if tagline:
        desc_parts.append(tagline.rstrip("."))
    if one_liner and one_liner not in tagline:
        desc_parts.append(one_liner.rstrip("."))
    if not desc_parts:
        desc_parts.append(f"A {sector or 'technology'} company building {theme}")

    if revenue_model:
        desc_parts.append(f"generating revenue through {revenue_model}")
    if biz_model and biz_model.lower() not in str(desc_parts).lower():
        desc_parts.append(f"operating a {biz_model} model")

    combined = ". ".join(p.capitalize() for p in desc_parts if p)
    if combined:
        combined = combined[0].upper() + combined[1:]
        if not combined.endswith("."):
            combined += "."

    parts.append(combined)
    return " — ".join(parts)


def generate_investor_interpretation(section: str, data: dict, sector_profile: dict,
                                     confidence: float) -> str:
    """Generate 1-sentence 'what this means' insight for a section."""
    tier = _confidence_tier(confidence)
    if tier == "low":
        return ""

    lens = sector_profile.get("investor_lens", "")
    if not lens:
        return ""

    interpretations = {
        "traction": f"The company's operational metrics suggest early commercial validation, {lens}.",
        "market": f"Market positioning in this segment suggests a substantial growth runway, {lens}.",
        "funding": f"The capitalization strategy reflects measured capital deployment, {lens}.",
        "team": f"The founding team's background and experience profile aligns with the company's strategic requirements, {lens}.",
    }
    return interpretations.get(section, "")


def _join_clauses(clauses: List[str]) -> str:
    """Join clauses with commas and 'and' for the last."""
    if not clauses:
        return ""
    if len(clauses) == 1:
        return str(clauses[0])
    if len(clauses) == 2:
        return f"{clauses[0]} and {clauses[1]}"
    return f"{', '.join(str(c) for c in clauses[:-1])}, and {clauses[-1]}"


def generate_confidence_summary(structured_data: dict,
                                 field_confidence: Optional[Dict[str, float]] = None,
                                 include_sources: bool = False) -> str:
    """
    Generate section-by-section summary with confidence-aware narrative tiers.
    Delegates to deterministic renderer package for all section rendering.
    Uses field_confidence dict to adjust language per section.
    """
    if field_confidence is None:
        field_confidence = structured_data.get("_field_confidence", {})

    sector_str = str(structured_data.get("company_brief", {}).get("sector", "") or "technology")
    sector_profile = _SECTOR_PROFILES.get(_detect_sector(sector_str), _SECTOR_PROFILES["general"])

    # Delegate to deterministic renderer
    from app.rag.renderer.utils import render_full_report
    return render_full_report(
        structured_data,
        field_confidence=field_confidence,
        include_sources=include_sources,
        sector_profile=sector_profile,
    )


def improve_warning(warning: str) -> str:
    """Convert robotic validation warnings into analyst-grade prose."""
    rewrites = [
        # Revenue/TAM issues
        (r"Revenue \(.*?\) is very low.*?",
         "Reported revenue figures appear unusually low for a growth-stage company — this may indicate that the extracted value represents a subset of actual revenue activity"),
        (r"Revenue \(.*?\) unusually high.*?",
         "Extracted revenue figures are notably high for an early-stage company — the source and composition of this figure should be verified against the original deck data"),
        (r"TAM < Revenue.*?",
         "The extracted market size appears smaller than the company's stated revenue — this may indicate that the market size value was not captured correctly, or the revenue figure represents a broader scope than the defined TAM"),
        (r"TAM < SAM.*?",
         "Market size values appear to be out of hierarchical order — TAM should be the largest market figure, followed by SAM and SOM; the extracted values may have been assigned to the wrong fields"),
        (r"SAM < SOM.*?",
         "Serviceable addressable market is smaller than serviceable obtainable market — these values may be inverted or assigned to incorrect fields"),
        (r"SOM is only.*?of TAM.*?",
         "The obtainable market share relative to total addressable market is notably low — this may reflect a conservative market capture assumption or indicate that unit/scaling assumptions differ between market size estimates"),
        (r"TAM \(.*?\) lacks currency unit.*?",
         "The extracted TAM value does not include an explicit currency or unit label — market size figures without units should be cross-referenced with the original deck to confirm whether they represent monetary value, volume, or another metric"),

        # Unit issues
        (r"TAM \(.*?\) uses 'Mn' unit.*?",
         "The market size value appears to use 'Million' denomination which may not align with the magnitude of the market being described — verify whether this represents a different metric type (e.g., job counts, volumes) rather than currency-denominated market size"),
        (r"Market size unit mismatch.*?",
         "Inconsistent unit usage was detected across TAM, SAM, and SOM values — market size figures should use consistent units for meaningful comparison"),

        # Temporal issues
        (r".*?time_type.*?not a recognized.*?",
         "The temporal classification assigned to this metric does not match expected categories — the metric's time context should be reviewed"),
        (r".*?has no time_type.*?",
         "This financial metric was extracted without temporal classification — adding period context (historical, current, projection) would improve data reliability"),

        # ARPC and ratio issues
        (r"ARPC.*?too low.*?",
         "Revenue per customer is notably low relative to the stated customer count — this may indicate that the customer count includes non-revenue-generating entities or product units rather than paying customers"),
        (r"ARPC.*?too high.*?",
         "Revenue per customer is unusually high — this may indicate enterprise-scale contracts or that the customer count represents a subset of actual customers"),
        (r"Dilution.*?high.*?",
         "The implied dilution from the current raise is elevated — this may suggest the valuation figure is post-money rather than pre-money, or that the raise amount and company stage don't align"),
        (r"Revenue exceeds.*?TAM.*?",
         "Extracted revenue exceeds the total addressable market — this strongly suggests a field mapping error where revenue and market size values may have been swapped"),
        (r"Valuation.*?< Raise.*?",
         "Company valuation is lower than the current raise amount — this is unlikely for a standard priced round and suggests the valuation and raise fields may be swapped or misinterpreted"),

        # General cross-field
        (r"Pipeline value.*?Revenue value.*?",
         "Pipeline value and revenue figures are nearly identical — this likely indicates the same data point was assigned to both fields; the true pipeline value should be reviewed against source context"),
        (r"Orders.*?Customers.*?identical.*?",
         "Order count and customer count are the same — this suggests the same value may have been assigned to both fields, or the company operates in a single-order-per-customer model"),
        (r"Previous round value.*?matches valuation.*?",
         "A previous funding round amount is nearly identical to the current valuation — this may indicate the valuation and previous round fields are swapped"),
    ]

    for pattern, replacement in rewrites:
        if re.search(pattern, warning, re.IGNORECASE):
            return replacement
    return warning
