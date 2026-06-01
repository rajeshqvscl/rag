"""
Canonical Evidence Registry

A single source of truth for all extracted metrics.
Ensures consistent metrics across extraction, validation, generation, and frontend.

Data Structure:
    class MetricEvidence:
        - metric_name: str (e.g., "revenue", "tam", "arr")
        - value: str (e.g., "₹9 Cr", "65 Cr")
        - normalized_value: float (e.g., 90000000.0)
        - metric_type: str (e.g., "revenue_actual", "revenue_projected")
        - source_slide: int
        - evidence_text: str
        - confidence: float (0.0-1.0)
        - ontology_class: str
        - temporal_class: str (e.g., "historical", "current", "projected")
        - currency: str
        - unit: str

Flow:
    Retrieval
    ↓
    Evidence extraction (from chunks)
    ↓
    Registry (stores all evidence)
    ↓
    Validation (resolves conflicts)
    ↓
    Generator (consumes registry)
    ↓
    Frontend (consumes registry)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
import re
from app.rag.financial_ontology import classify_metric, normalize_metric_value


@dataclass
class MetricEvidence:
    """Single piece of evidence for a metric."""
    metric_name: str
    value: str
    normalized_value: float = 0.0
    metric_type: str = ""
    source_slide: int = 0
    evidence_text: str = ""
    confidence: float = 0.0
    ontology_class: str = ""
    temporal_class: str = ""
    currency: str = "INR"
    unit: str = ""
    raw_context: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CanonicalEvidenceRegistry:
    """
    Single source of truth for all extracted metrics.
    Prevents inconsistent metrics, hallucinations, and frontend corruption.
    """

    def __init__(self):
        self._evidence: Dict[str, List[MetricEvidence]] = {}
        self._resolved: Dict[str, MetricEvidence] = {}

    def add_evidence(
        self,
        metric_name: str,
        value: str,
        source_slide: int = 0,
        evidence_text: str = "",
        context: str = ""
    ) -> None:
        """Add a piece of evidence for a metric."""
        normalized = normalize_metric_value(value)
        ontology_class, conf = classify_metric(value, value, context)

        temporal_class = self._detect_temporal(context, value)

        evidence = MetricEvidence(
            metric_name=metric_name,
            value=value,
            normalized_value=normalized.get("normalized", 0.0),
            metric_type=ontology_class,
            source_slide=source_slide,
            evidence_text=evidence_text[:200] if evidence_text else "",
            confidence=conf,
            ontology_class=ontology_class,
            temporal_class=temporal_class,
            currency=normalized.get("currency", "INR"),
            unit=normalized.get("unit", ""),
            raw_context=context[:300] if context else ""
        )

        if metric_name not in self._evidence:
            self._evidence[metric_name] = []
        self._evidence[metric_name].append(evidence)

    def _detect_temporal(self, context: str, value: str) -> str:
        """Detect if metric is historical, current, or projected."""
        text = f"{context} {value}".lower()

        projected_kw = ["projected", "forecast", "target", "expected", "vision", "aim", "next FY", "fy2"]
        historical_kw = ["fy21", "fy22", "fy23", "fy24", "previous", "last year", "historical"]
        current_kw = ["current", "this year", "fy25", "invoiced", "booked"]

        for kw in projected_kw:
            if kw in text:
                return "projected"
        for kw in historical_kw:
            if kw in text:
                return "historical"
        for kw in current_kw:
            if kw in text:
                return "current"

        return "unknown"

    def resolve(self) -> Dict[str, MetricEvidence]:
        """
        Resolve conflicts and return best evidence per metric.
        Uses confidence and temporal priority.
        """
        self._resolved = {}

        for metric_name, evidences in self._evidence.items():
            if not evidences:
                continue

            temporal_priority = {"current": 3, "unknown": 2, "projected": 1, "historical": 1}

            def score_evidence(e: MetricEvidence) -> float:
                base = e.confidence
                temporal = temporal_priority.get(e.temporal_class, 1)
                return base * 0.6 + (temporal / 3.0) * 0.4

            best = max(evidences, key=score_evidence)
            self._resolved[metric_name] = best

        return self._resolved

    def get_metric(self, metric_name: str) -> Optional[MetricEvidence]:
        """Get resolved evidence for a specific metric."""
        if metric_name not in self._resolved:
            self.resolve()
        return self._resolved.get(metric_name)

    def get_all_metrics(self) -> Dict[str, MetricEvidence]:
        """Get all resolved metrics."""
        if not self._resolved:
            self.resolve()
        return self._resolved

    def to_canonical_dict(self) -> Dict[str, Any]:
        """Export as frontend-safe dictionary."""
        if not self._resolved:
            self.resolve()

        result = {}
        for metric_name, evidence in self._resolved.items():
            result[metric_name] = {
                "value": evidence.value,
                "normalized_value": evidence.normalized_value,
                "confidence": evidence.confidence,
                "source_slide": evidence.source_slide,
                "metric_type": evidence.metric_type,
                "temporal_class": evidence.temporal_class,
                "currency": evidence.currency,
                "unit": evidence.unit,
            }
        return result

    def to_chart_data(self) -> Dict[str, List[Dict]]:
        """Export as chart-ready data."""
        if not self._resolved:
            self.resolve()

        chart_data = {
            "revenue": {"title": "Revenue", "data": []},
            "growth": {"title": "Growth", "data": []},
            "orders": {"title": "Orders", "data": []},
            "market": {"title": "Market Size", "data": []},
            "kpi_summary": {"title": "Key Metrics", "data": []},
        }

        for metric_name, evidence in self._resolved.items():
            if evidence.metric_type in ("revenue_actual", "revenue_projected"):
                chart_data["revenue"]["data"].append({
                    "period": evidence.temporal_class,
                    "value": evidence.normalized_value,
                    "display": evidence.value,
                    "label": metric_name,
                    "confidence": evidence.confidence,
                })
            elif evidence.metric_type in ("purchase_order", "pipeline"):
                chart_data["orders"]["data"].append({
                    "period": evidence.temporal_class,
                    "value": evidence.normalized_value,
                    "display": evidence.value,
                    "label": metric_name,
                    "confidence": evidence.confidence,
                })
            elif metric_name in ("tam", "sam", "som"):
                chart_data["market"]["data"].append({
                    "period": "current",
                    "value": evidence.normalized_value,
                    "display": evidence.value,
                    "label": metric_name.upper(),
                    "confidence": evidence.confidence,
                })

            chart_data["kpi_summary"]["data"].append({
                "label": metric_name.replace("_", " ").title(),
                "value": evidence.normalized_value,
                "display": evidence.value,
                "confidence": evidence.confidence,
            })

        return {k: v for k, v in chart_data.items() if v["data"]}

    def add_from_extraction(self, extraction_result: Dict) -> None:
        """Add evidence from LLM extraction results."""
        canonical = extraction_result.get("canonical_metrics", {})

        for metric_name, metric_data in canonical.items():
            if isinstance(metric_data, dict):
                value = metric_data.get("value", "")
                context = metric_data.get("evidence_text", "")
                source_slide = metric_data.get("source_slide", 0)

                if value:
                    self.add_evidence(
                        metric_name=metric_name,
                        value=value,
                        source_slide=source_slide,
                        evidence_text=context,
                        context=context
                    )


def create_registry_from_chunks(chunks: List[Dict], sections_config: Dict[str, str]) -> CanonicalEvidenceRegistry:
    """
    Create registry by extracting evidence from retrieval chunks.
    This ensures no evidence is lost during generation.
    """
    registry = CanonicalEvidenceRegistry()

    financial_pattern = r"(?:₹|Rs\.?|INR|\$|USD)\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:cr|lakh|lakhs?|mn|million|bn|billion|k|thousand)?"
    metric_keywords = ["revenue", "arr", "tam", "sam", "som", "orders", "customers", "pipeline", "valuation", "funding", "grant", "growth"]

    for chunk in chunks:
        content = chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
        section = chunk.get("metadata", {}).get("section", "general") if isinstance(chunk, dict) else ""

        matches = re.finditer(financial_pattern, content, re.IGNORECASE)
        for match in matches:
            value_str = match.group(0)
            context_start = max(0, match.start() - 100)
            context_end = min(len(content), match.end() + 100)
            context = content[context_start:context_end]

            for metric_kw in metric_keywords:
                if metric_kw in context.lower():
                    registry.add_evidence(
                        metric_name=metric_kw,
                        value=value_str,
                        source_slide=0,
                        evidence_text=context[:150],
                        context=context
                    )
                    break

    return registry