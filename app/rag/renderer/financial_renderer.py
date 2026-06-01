"""
Financial sections deterministic renderer: traction, funding, pipeline, revenue details.
"""

import re
from typing import Optional

from .utils import safe, join_clauses, completeness_score, fmt_period_short, get_val



def render_traction(tr: dict, canonical: dict,
                    field_confidence: Optional[dict] = None,
                    sector_profile: Optional[dict] = None) -> str:
    """Render traction & validation section with ontological awareness."""
    if completeness_score(tr, ["revenue", "orders", "customers"]) < 0.2:
        return ""

    def _g(key):
        return get_val(tr.get(key, ""))


    t_clauses = []

    rev_val = get_val(canonical.get("total_revenue")) or _g("revenue") or ""
    if rev_val:
        rev_onto = canonical.get("total_revenue", {}).get("ontological_type", "")
        if rev_onto == "purchase_order_value":
            t_clauses.append(f"purchase order value of {rev_val}")
        elif rev_onto == "invoiced_amount":
            t_clauses.append(f"invoiced amount of {rev_val}")
        elif rev_onto == "government_grants":
            t_clauses.append(f"government grants of {rev_val}")
        else:
            t_clauses.append(f"revenue of {rev_val}")

    ord_val = get_val(canonical.get("orders")) or _g("orders") or ""
    if ord_val:
        ord_onto = canonical.get("orders", {}).get("ontological_type", "")
        if ord_onto == "expected_units":
            t_clauses.append(f"with {ord_val} expected units")
        else:
            t_clauses.append(f"with {ord_val} orders")

    cust_val = get_val(canonical.get("customers")) or _g("customers") or ""
    if cust_val:
        cust_canon = canonical.get("customers", {})
        if isinstance(cust_canon, dict) and cust_canon.get("entity_type") and cust_canon.get("value"):
            cust_val = get_val(cust_canon["value"]) or cust_canon["value"]
        t_clauses.append(f"across {cust_val}")


    milestones = tr.get("key_milestones", [])
    milestone_text = ""
    if milestones:
        milestone_text = f" Milestones include {', '.join(milestones[:2])}."

    if t_clauses:
        return join_clauses(t_clauses) + "." + milestone_text
    return ""


def render_funding(fund: dict,
                   field_confidence: Optional[dict] = None,
                   sector_profile: Optional[dict] = None) -> str:
    """Render funding & investment history section."""
    if completeness_score(fund, ["current_raise", "valuation"]) < 0.2 and not fund.get("previous_rounds") and not fund.get("investors"):
        return ""

    def _g(key):
        return get_val(fund.get(key, ""))


    f_clauses = []
    if _g("current_raise"):
        f_clauses.append(f"raising {fund['current_raise']}")
    if _g("valuation"):
        f_clauses.append(f"at {fund['valuation']} valuation")

    prev = fund.get("previous_rounds", [])
    if prev:
        prev_strs = []
        for r in prev[:3]:
            if isinstance(r, dict):
                amt = r.get("amount", "")
                dt = r.get("date", r.get("year", ""))
                prev_strs.append(f"{amt} ({dt})" if dt else amt)
            else:
                prev_strs.append(str(r))
        if prev_strs:
            f_clauses.append(f"with prior rounds: {' | '.join(prev_strs)}")

    investors = fund.get("investors", [])
    if investors:
        f_clauses.append(f"backed by {', '.join(investors[:3])}")

    uof = fund.get("use_of_funds", [])
    if uof:
        if isinstance(uof, str) and uof.strip():
            f_clauses.append(f"for {uof[:200]}")
        elif isinstance(uof, list):
            items = [str(f).strip() for f in uof[:2] if str(f).strip()]
            if items:
                f_clauses.append(f"for {', '.join(items)}")

    return join_clauses(f_clauses) + "." if f_clauses else ""


def render_pipeline(pipe: dict,
                    field_confidence: Optional[dict] = None,
                    sector_profile: Optional[dict] = None) -> str:
    """Render pipeline section."""
    if completeness_score(pipe, ["pipeline_value", "lois"]) < 0.2 and not pipe.get("prospects"):
        return ""

    def _g(key):
        return get_val(pipe.get(key, ""))


    pl_clauses = []
    if _g("pipeline_value"):
        pl_clauses.append(f"pipeline value of {pipe['pipeline_value']}")
    if _g("lois"):
        pl_clauses.append(f"with {pipe['lois']} LOIs")
    if _g("expected_close"):
        pl_clauses.append(f"expected close by {pipe['expected_close']}")

    prospects = pipe.get("prospects", [])
    if isinstance(prospects, list) and prospects:
        pl_clauses.append(f"prospects include {', '.join(str(p) for p in prospects[:3])}")
    elif isinstance(prospects, str) and prospects.strip():
        pl_clauses.append(f"prospects: {prospects[:100]}")

    return join_clauses(pl_clauses) + "." if pl_clauses else ""


def render_revenue_details(rd: dict, canonical: dict) -> str:
    """Render revenue details section. Returns empty string if no data."""
    r_clauses = []

    if canonical:
        total_rev = get_val(canonical.get("total_revenue"))
        period_rev = get_val(canonical.get("current_period_revenue"))
        if total_rev and (not period_rev or total_rev != period_rev):
            r_clauses.append(f"cumulative: {total_rev}")
        elif total_rev:
            r_clauses.append(f"current revenue: {total_rev}")
        if period_rev and period_rev != total_rev:
            r_clauses.append(f"period revenue: {period_rev}")

        booking_keys = sorted(k for k in canonical if k.startswith("projected_booking_"))
        if booking_keys:
            booking_strs = []
            for bk in booking_keys[:3]:
                bm = canonical.get(bk, {})
                bv = get_val(bm)
                period = ""
                if isinstance(bm, dict) and bm.get("display_name"):
                    pm = re.search(r'\((.*?)\)', str(bm["display_name"]))
                    if pm:
                        period = pm.group(1)
                booking_strs.append(f"{period} {bv}".strip() if period else bv)
            if booking_strs:
                r_clauses.append(f"booking forecast: {' | '.join(booking_strs)}")

        po_keys = sorted(k for k in canonical if k.startswith("projected_po_"))
        if po_keys and not (booking_keys and [k for k in booking_keys if k]):
            po_strs = []
            for pk in po_keys[:2]:
                pm = canonical.get(pk, {})
                po_strs.append(get_val(pm))
            if po_strs:
                r_clauses.append(f"expected PO: {' | '.join(po_strs)}")


    # Fallback to raw revenue_details fields if canonical not available
    if not r_clauses:
        current = ""
        if isinstance(rd, dict):
            current = str(rd.get("current_revenue", "") or "").strip()
        if current:
            r_clauses.append(f"current revenue of {current}")

    projs = rd.get("projections", []) if isinstance(rd, dict) else []
    if isinstance(projs, list) and projs:
        p_strs = []
        for p in projs[:2]:
            if isinstance(p, dict) and p.get("value"):
                period = fmt_period_short(p.get("period", ""))
                val = p["value"]
                p_strs.append(f"{period} {val}".strip() if period else val)
        if p_strs:
            r_clauses.append(f"projecting {' | '.join(p_strs)}")

    return join_clauses(r_clauses) + "." if r_clauses else ""
