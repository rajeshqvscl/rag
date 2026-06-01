"""
Market sections deterministic renderer: industry overview, competitive landscape, recognition.
"""

import re
from typing import Optional

from .utils import safe, join_clauses, completeness_score, filter_competitors, _filter_empty_clause_parts, get_val


def render_industry_overview(ind: dict,
                             field_confidence: Optional[dict] = None,
                             sector_profile: Optional[dict] = None) -> str:
    """Render industry overview with TAM/SAM/SOM."""
    if completeness_score(ind, ["tam", "sam", "som", "market_context"]) < 0.2:
        return ""

    def _g(key):
        return get_val(ind.get(key, ""))

    m_clauses = []
    if _g("tam"):
        m_clauses.append(f"TAM of {_g('tam')}")
    if _g("sam"):
        m_clauses.append(f"SAM of {_g('sam')}")
    if _g("som"):
        m_clauses.append(f"SOM of {_g('som')}")
    if _g("market_context"):
        m_clauses.append(f"in {_g('market_context')}")


    trends = ind.get("key_trends", [])
    if trends:
        m_clauses.append(f"with trends including {', '.join(trends[:2])}")

    if m_clauses:
        text = join_clauses(m_clauses) + "."
        if sector_profile and sector_profile.get("market_frame"):
            text += f" {sector_profile['market_frame'].capitalize()}."
        return text
    return ""


def render_competitive_landscape(comp: dict,
                                 sector_profile: Optional[dict] = None) -> str:
    """Render competitive landscape section."""
    if completeness_score(comp, ["competitors", "differentiation", "moat", "market_position"]) < 0.2:
        return ""

    cc_clauses = []

    def _g(key):
        v = comp.get(key, "")
        return str(v).strip() if v else ""

    competitors = comp.get("competitors", [])
    if isinstance(competitors, list) and competitors:
        valid = filter_competitors(competitors)
        if valid:
            cc_clauses.append(f"key players: {', '.join(valid)}")

    if _g("differentiation"):
        d = comp['differentiation'].strip().rstrip(",")
        if d and len(d) > 2:
            cc_clauses.append(f"differentiated by {d}")
    if _g("moat"):
        m = comp['moat'].strip().rstrip(",")
        if m and len(m) > 2:
            cc_clauses.append(f"moat: {m}")
    if _g("market_position"):
        mp = comp['market_position'].strip().rstrip(",")
        if mp and len(mp) > 2:
            cc_clauses.append(f"position: {mp}")

    cc_clauses = _filter_empty_clause_parts(cc_clauses)
    return join_clauses(cc_clauses) + "." if cc_clauses else ""


def render_recognition(rec: dict) -> str:
    """Render awards & recognition section."""
    if completeness_score(rec, ["awards", "certifications", "media_coverage"]) < 0.2:
        return ""

    a_clauses = []

    def _list_or_str(key):
        val = rec.get(key, [])
        if isinstance(val, list) and val:
            return val
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    awards = _list_or_str("awards")
    if awards:
        a_clauses.append(f"awards: {', '.join(str(a) for a in awards[:3])}")
    certs = _list_or_str("certifications")
    if certs:
        a_clauses.append(f"certifications: {', '.join(str(c) for c in certs[:3])}")
    media = _list_or_str("media_coverage")
    if media:
        a_clauses.append(f"featured in {', '.join(str(m) for m in media[:2])}")

    return join_clauses(a_clauses) + "." if a_clauses else ""
