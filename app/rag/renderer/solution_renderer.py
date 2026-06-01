"""
Problem and Solution deterministic renderer.
"""

import re
from typing import Optional

from .utils import safe, join_clauses, completeness_score, get_val


def render_problem(prob: dict) -> str:
    """Render problem statement section."""
    if completeness_score(prob, ["statement", "pain_points"]) < 0.2:
        return ""

    def _g(key):
        return get_val(prob.get(key, ""))

    p_clauses = []
    if _g("statement"):
        p_clauses.append(_g("statement"))
    pain = prob.get("pain_points", [])
    if pain:
        p_clauses.append(f"pain points include {', '.join(get_val(p) for p in pain[:3])}")
    return join_clauses(p_clauses) + "." if p_clauses else ""


def render_solution(sol: dict) -> str:
    """Render solution section."""
    if completeness_score(sol, ["description", "key_features", "technology", "usp"]) < 0.2:
        return ""

    def _g(key):
        return get_val(sol.get(key, ""))

    from .utils import _filter_empty_clause_parts

    s_clauses = []
    if _g("description"):
        s_clauses.append(_g("description"))
    features = sol.get("key_features", [])
    if features:
        from .utils import safe_join
        s_clauses.append(f"key features include {safe_join([get_val(f) for f in features[:4]], ', ')}")
    if _g("technology"):
        s_clauses.append(f"powered by {_g('technology')}")
    if _g("usp"):
        s_clauses.append(f"with USP of {_g('usp')}")

    s_clauses = _filter_empty_clause_parts(s_clauses)

    return join_clauses(s_clauses) + "." if s_clauses else ""
