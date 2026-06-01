"""
Financial Candidate Ranking Engine — scores and ranks every extracted financial value
by context proximity, temporal priority, multi-occurrence, and table awareness.

Phase 2 of the accuracy improvement plan.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import re
from enum import Enum


class MetricType(str, Enum):
    REVENUE = "revenue"
    ORDERS = "orders"
    CUSTOMERS = "customers"
    FUNDING_RAISE = "funding_raise"
    VALUATION = "valuation"
    PIPELINE = "pipeline"
    TAM = "tam"
    SAM = "sam"
    SOM = "som"
    MARGIN = "margin"
    PROJECTION = "projection"


# Context proximity scores — how strongly nearby keywords signal metric type
CONTEXT_SCORES = {
    # Revenue signals
    "revenue": 40,
    "arr": 35,
    "income": 35,
    "invoiced": 40,
    "earned": 30,
    "sales": 30,
    "turnover": 30,
    "topline": 30,
    # Order/booking signals
    "purchase order": 40,
    "po": 35,
    "booking": 35,
    "order value": 40,
    "orders": 30,
    "contract value": 30,
    # Funding signals
    "funding": 40,
    "raise": 40,
    "investment": 35,
    "capital": 30,
    "series": 30,
    "valuation": 35,
    "pre-money": 35,
    "post-money": 35,
    # Pipeline signals
    "pipeline": 40,
    "expected": 25,
    "prospect": 35,
    "loi": 35,
    "letter of intent": 35,
    # Market signals
    "tam": 40,
    "market size": 40,
    "addressable market": 40,
    "sam": 40,
    "som": 40,
    # Negative signals (reduce score for wrong match)
    "use of funds": -20,
    "allocation": -15,
    "headcount": -20,
    "team size": -20,
    "employee": -20,
    "margin": -15,
    "gross margin": -15,
    "ebitda": -10,
    # Temporal signals
    "fy": 5,
    "quarter": 5,
    "annual": 5,
    # Table signals (bonus for table-like context)
    "table": 15,
    "kpi": 15,
    "metrics": 10,
}


TEMPORAL_PRIORITY = {
    "actual": 5,
    "historical": 4,
    "current": 4,
    "fy": 4,
    "projected": 3,
    "forecast": 2,
    "target": 2,
    "pipeline": 1,
    "unknown": 0,
}


@dataclass
class FinancialCandidate:
    value_str: str
    metric_type: MetricType
    source_section: str = ""
    source_field: str = ""
    nearby_text: str = ""
    context_score: int = 0
    temporal_score: int = 0
    multi_occurrence_score: int = 0
    table_score: int = 0
    confidence: float = 0.0
    normalized_value: float = 0.0
    fiscal_year: Optional[str] = None


class FinancialCandidateRanker:
    """Score and rank financial candidates per metric type."""

    @staticmethod
    def _compute_context_score(value_str: str, nearby_text: str) -> int:
        """Score based on keywords in nearby context."""
        score = 0
        if nearby_text:
            text_lower = nearby_text.lower()
            for keyword, points in CONTEXT_SCORES.items():
                if keyword in text_lower:
                    score += points
        # Bonus for value strings that explicitly name their type
        vlow = value_str.lower()
        if "revenue" in vlow:
            score += 20
        if "arr" in vlow:
            score += 20
        if "po" in vlow or "purchase order" in vlow:
            score += 25
        if "funding" in vlow or "raise" in vlow:
            score += 20
        if "tam" in vlow or "sam" in vlow or "som" in vlow:
            score += 20
        return score

    @staticmethod
    def _compute_temporal_score(value_str: str) -> int:
        """Score based on temporal specificity and priority."""
        vlow = value_str.lower()
        score = 0
        for keyword, priority in TEMPORAL_PRIORITY.items():
            if keyword in vlow:
                score = max(score, priority * 10)
        if re.search(r'FY\d{2,4}', value_str):
            score += 15
        if re.search(r'Q[1-4]', value_str, re.IGNORECASE):
            score += 10
        return score

    @staticmethod
    def _compute_table_score(source_section: str, source_field: str) -> int:
        """Score bonus for values from table-like sources."""
        table_keywords = ["table", "kpi", "dashboard", "metrics", "snapshot", "overview"]
        section_lower = source_section.lower()
        field_lower = source_field.lower()
        for kw in table_keywords:
            if kw in section_lower or kw in field_lower:
                return 15
        return 0

    @staticmethod
    def _extract_normalized(value_str: str) -> float:
        """Extract normalized numeric value from value string."""
        if not value_str:
            return 0.0
        try:
            from app.rag.number_utils import parse_indian_number
            return parse_indian_number(value_str)
        except Exception:
            nums = re.findall(r'[\d,]+\.?\d*', value_str.replace(",", ""))
            if nums:
                try:
                    return float(nums[0])
                except ValueError:
                    pass
        return 0.0

    @staticmethod
    def _extract_fiscal_year(value_str: str) -> Optional[str]:
        """Extract fiscal year from value string."""
        if not value_str:
            return None
        m = re.search(r'FY\d{2}-\d{2}|FY\d{4}', value_str)
        return m.group(0) if m else None

    @classmethod
    def build_candidates(cls, structured_data: dict, context_text: str = "") -> Dict[MetricType, List[FinancialCandidate]]:
        """Scan structured_data and build ranked candidates per metric type."""
        from app.rag.number_utils import parse_indian_number

        candidates: Dict[MetricType, List[FinancialCandidate]] = {}

        def _add(metric_type: MetricType, value_str: str, section: str, field: str, nearby: str = ""):
            if isinstance(value_str, dict):
                value_str = value_str.get("value", "")
            if not value_str or str(value_str).strip() in ("", "null", "none", "n/a"):
                return
            nearby = nearby or context_text[:200]
            cand = FinancialCandidate(
                value_str=str(value_str),
                metric_type=metric_type,
                source_section=section,
                source_field=field,
                nearby_text=nearby[:500],
                context_score=cls._compute_context_score(str(value_str), nearby),
                temporal_score=cls._compute_temporal_score(str(value_str)),
                table_score=cls._compute_table_score(section, field),
                normalized_value=parse_indian_number(str(value_str)),
                fiscal_year=cls._extract_fiscal_year(str(value_str)),
            )
            if metric_type not in candidates:
                candidates[metric_type] = []
            candidates[metric_type].append(cand)

        # Scan all sections for financial values
        # Traction section
        tr = structured_data.get("traction", {}) or {}
        if isinstance(tr, dict):
            _add(MetricType.REVENUE, tr.get("revenue", ""), "traction", "revenue", context_text)
            _add(MetricType.ORDERS, tr.get("orders", ""), "traction", "orders", context_text)
            _add(MetricType.CUSTOMERS, tr.get("customers", ""), "traction", "customers", context_text)

        # Revenue details
        rd = structured_data.get("revenue_details", {}) or {}
        if isinstance(rd, dict):
            _add(MetricType.REVENUE, rd.get("current_revenue", ""), "revenue_details", "current_revenue", context_text)
            projs = rd.get("projections", [])
            if isinstance(projs, list):
                for i, p in enumerate(projs):
                    if isinstance(p, dict) and p.get("value"):
                        _add(MetricType.PROJECTION, p["value"], "revenue_details", f"projections[{i}]", context_text)

        # Funding section
        fund = structured_data.get("funding", {}) or {}
        if isinstance(fund, dict):
            _add(MetricType.FUNDING_RAISE, fund.get("current_raise", ""), "funding", "current_raise", context_text)
            _add(MetricType.VALUATION, fund.get("valuation", ""), "funding", "valuation", context_text)

        # Pipeline section
        pipe = structured_data.get("pipeline", {}) or {}
        if isinstance(pipe, dict):
            _add(MetricType.PIPELINE, pipe.get("pipeline_value", ""), "pipeline", "pipeline_value", context_text)
            _add(MetricType.PIPELINE, pipe.get("lois", ""), "pipeline", "lois", context_text)

        # Industry overview
        ind = structured_data.get("industry_overview", {}) or {}
        if isinstance(ind, dict):
            _add(MetricType.TAM, ind.get("tam", ""), "industry_overview", "tam", context_text)
            _add(MetricType.SAM, ind.get("sam", ""), "industry_overview", "sam", context_text)
            _add(MetricType.SOM, ind.get("som", ""), "industry_overview", "som", context_text)

        # Canonical registry (most authoritative — already classified)
        canonical = structured_data.get("_canonical", {}) or {}
        if isinstance(canonical, dict):
            metric_map = {
                "total_revenue": MetricType.REVENUE,
                "current_period_revenue": MetricType.REVENUE,
                "historical_revenue": MetricType.REVENUE,
                "invoiced_amount": MetricType.REVENUE,
                "purchase_order_value": MetricType.REVENUE,
                "orders": MetricType.ORDERS,
                "expected_units": MetricType.ORDERS,
                "customers": MetricType.CUSTOMERS,
                "funding_raise": MetricType.FUNDING_RAISE,
                "valuation": MetricType.VALUATION,
                "pipeline_value": MetricType.PIPELINE,
                "tam": MetricType.TAM,
                "sam": MetricType.SAM,
                "som": MetricType.SOM,
            }
            for cname, entry in canonical.items():
                if not isinstance(entry, dict):
                    continue
                mt = metric_map.get(cname)
                if mt:
                    _add(mt, entry.get("value", ""), "canonical", cname, context_text)

        return candidates

    @classmethod
    def rank_candidates(cls, candidates: Dict[MetricType, List[FinancialCandidate]]) -> Dict[MetricType, FinancialCandidate]:
        """Rank candidates per metric type, return the best for each."""
        ranked: Dict[MetricType, FinancialCandidate] = {}

        for metric_type, cands in candidates.items():
            if not cands:
                continue

            # Compute multi-occurrence score: same normalized value appearing multiple times
            value_counts: Dict[float, int] = {}
            for c in cands:
                value_counts[c.normalized_value] = value_counts.get(c.normalized_value, 0) + 1

            for c in cands:
                count = value_counts.get(c.normalized_value, 0)
                if count >= 3:
                    c.multi_occurrence_score = 20
                elif count >= 2:
                    c.multi_occurrence_score = 10

                # Compute final confidence
                base = 0.30
                context_pct = min(c.context_score / 100.0, 0.35)
                temporal_pct = min(c.temporal_score / 100.0, 0.15)
                multi_pct = c.multi_occurrence_score / 100.0
                table_pct = c.table_score / 100.0
                c.confidence = round(min(base + context_pct + temporal_pct + multi_pct + table_pct, 0.95), 2)

            # Sort by confidence (primary), temporal_score (secondary), multi_occurrence (tertiary)
            cands.sort(key=lambda c: (c.confidence, c.temporal_score, c.multi_occurrence_score), reverse=True)
            ranked[metric_type] = cands[0]

        return ranked

    @classmethod
    def get_scoring_summary(cls, structured_data: dict, context_text: str = "") -> Dict[str, Any]:
        """Build a scoring summary that can be used for logging or debugging."""
        candidates = cls.build_candidates(structured_data, context_text)
        ranked = cls.rank_candidates(candidates)
        summary = {}
        for mt, cand in ranked.items():
            summary[mt.value] = {
                "value": cand.value_str,
                "normalized": cand.normalized_value,
                "confidence": cand.confidence,
                "source": f"{cand.source_section}.{cand.source_field}",
                "temporal": cand.fiscal_year or "unknown",
                "scores": {
                    "context": cand.context_score,
                    "temporal": cand.temporal_score,
                    "multi_occurrence": cand.multi_occurrence_score,
                    "table": cand.table_score,
                },
            }
        return summary
