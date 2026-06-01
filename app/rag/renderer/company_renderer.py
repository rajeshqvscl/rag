"""
Company brief and business overview deterministic renderer.
"""

import re
from typing import Optional

from .utils import safe, join_clauses, completeness_score, get_val



def render_company_brief(brief: dict, sector_profile: Optional[dict] = None) -> str:
    """Generate 2-3 line investor-grade company description from brief data."""
    name = str(brief.get("name", "") or "").strip()
    tagline = str(brief.get("tagline", "") or "").strip()
    one_liner = str(brief.get("one_liner", "") or "").strip()
    stage = str(brief.get("stage", "") or "").strip()
    sector = str(brief.get("sector", "") or "").strip()

    parts = []
    if name:
        line = name
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
        if sector:
            line += f" | {sector.title()}"
        parts.append(line)

    # Thematic description
    theme = (sector_profile or {}).get("narrative_theme",
                                        "technology-enabled platform with early commercial traction")
    desc_parts = []
    if tagline:
        desc_parts.append(tagline.rstrip("."))
    if one_liner and one_liner not in tagline:
        desc_parts.append(one_liner.rstrip("."))
    if not desc_parts:
        biz_model = str(brief.get("business_model", "") or brief.get("model", "") or "").strip()
        if biz_model:
            desc_parts.append(f"A {sector or 'technology'} company operating a {biz_model} model")
        else:
            desc_parts.append(f"A {sector or 'technology'} company building {theme}")

    revenue_model = str(brief.get("revenue_model", "") or "").strip()
    if revenue_model:
        desc_parts.append(f"generating revenue through {revenue_model}")

    combined = ". ".join(p.capitalize() for p in desc_parts if p)
    if combined:
        combined = combined[0].upper() + combined[1:]
        if not combined.endswith("."):
            combined += "."
    parts.append(combined)

    return " — ".join(parts)


def render_business_overview(biz: dict,
                              field_confidence: Optional[dict] = None,
                              sector_profile: Optional[dict] = None) -> str:
    """Render business overview section."""
    if completeness_score(biz, ["model", "revenue_model", "target_customers", "gtm", "differentiator"]) < 0.2:
        return ""

    def _g(key):
        return get_val(biz.get(key, ""))

    b_clauses = []
    if _g("model"):
        b_clauses.append(f"{_g('model')}")
    if _g("revenue_model"):
        b_clauses.append(f"revenue through {_g('revenue_model')}")
    if _g("target_customers"):
        b_clauses.append(f"serving {_g('target_customers')}")
    if _g("gtm"):
        b_clauses.append(f"via {_g('gtm')}")
    if _g("differentiator"):
        b_clauses.append(f"differentiated by {_g('differentiator')}")


    if b_clauses:
        return join_clauses(b_clauses) + "."

    if sector_profile:
        from app.rag.semantic_narrative import _missing_data_msg
        return _missing_data_msg("business_overview", sector_profile, "low")
    return ""
