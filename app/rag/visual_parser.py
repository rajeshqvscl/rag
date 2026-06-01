"""
Visual Financial Parser — Spatial layout-aware extraction for:
  - Concentric circle TAM/SAM/SOM diagrams
  - Funnel TAM/SAM/SOM diagrams
  - Bar/line charts with axis labels
  - Infographic financial metrics

Uses layout blocks with (x, y, width, height) coordinates to map
visual elements to semantic financial fields.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from app.rag.page_adapter import PageAdapter


@dataclass
class LayoutBlock:
    x: float
    y: float
    width: float
    height: float
    text: str
    font_size: Optional[float] = None


@dataclass
class VisualMetric:
    label: str
    value: str
    semantic_field: str  # "tam", "sam", "som", "revenue", etc.
    confidence: float
    source: str  # "concentric", "funnel", "chart", "infographic"
    page: int = 0


class ConcentricCircleParser:
    """
    Parses concentric circle diagrams common in pitch deck market slides.
    
    Circle layout (center → outward):
      innermost  = SOM (smallest, highest concentration)
      middle     = SAM
      outermost  = TAM (largest)
    
    Detection heuristic:
      Blocks with large font / center-like position → inner rings
      Blocks with small font / wide position → outer rings
    """

    # Keywords that indicate each ring
    RING_LABELS = {
        "tam": ["total addressable market", "tam", "total market", "addressable market"],
        "sam": ["serviceable addressable market", "sam", "serviceable market", "addressable"],
        "som": ["serviceable obtainable market", "som", "obtainable market", "serviceable obtainable"],
    }

    @classmethod
    def parse(cls, blocks: List[LayoutBlock], page_text: str = "") -> List[VisualMetric]:
        if not blocks or len(blocks) < 3:
            return cls._fallback_text_parse(page_text)

        # Cluster blocks by vertical position (different circles are at different y-levels)
        y_clusters = cls._cluster_by_y(blocks, tolerance=15)

        if len(y_clusters) < 2:
            return cls._fallback_text_parse(page_text)

        # Sort clusters top-to-bottom (concentric circles are often stacked)
        y_clusters.sort(key=lambda c: sum(b.y for b in c) / len(c))

        results = []
        # Map clusters to TAM/SAM/SOM by label detection
        assigned = set()
        for cluster in y_clusters:
            cluster_text = " ".join(b.text for b in cluster).lower()
            label, field = cls._detect_ring_label(cluster_text)
            if label and field not in assigned:
                values = cls._extract_values(cluster)
                for v in values:
                    results.append(VisualMetric(
                        label=label,
                        value=v,
                        semantic_field=field,
                        confidence=0.85 if cls._has_currency(v) else 0.7,
                        source="concentric",
                    ))
                assigned.add(field)

        # If some rings have explicit labels, do value-only assignment
        if len(results) < 3:
            return cls._fallback_text_parse(page_text)

        return results

    @classmethod
    def _cluster_by_y(cls, blocks: List[LayoutBlock], tolerance: float = 15) -> List[List[LayoutBlock]]:
        sorted_blocks = sorted(blocks, key=lambda b: b.y)
        clusters = []
        current = [sorted_blocks[0]]
        for b in sorted_blocks[1:]:
            if abs(b.y - current[-1].y) <= tolerance:
                current.append(b)
            else:
                clusters.append(current)
                current = [b]
        if current:
            clusters.append(current)
        return clusters

    @classmethod
    def _detect_ring_label(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        for field, keywords in cls.RING_LABELS.items():
            for kw in keywords:
                if kw in text:
                    return kw.upper(), field
        return None, None

    @classmethod
    def _extract_values(cls, blocks: List[LayoutBlock]) -> List[str]:
        vals = []
        for b in blocks:
            numbers = re.findall(r'[₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|Crore|Lakh|Mn|Bn|Billion|Million|Thousand|K)?', b.text, re.IGNORECASE)
            vals.extend(n.strip() for n in numbers)
        return vals

    @classmethod
    def _has_currency(cls, text: str) -> bool:
        return bool(re.search(r'[₹$€]', text))

    @classmethod
    def _fallback_text_parse(cls, page_text: str) -> List[VisualMetric]:
        """Fallback: parse TAM/SAM/SOM from plain text when blocks aren't available."""
        results = []
        text_lower = page_text.lower()

        # Common currency prefixes (optional group — ? inside the group)
        _CURR_OPT = r'(?:INR|USD|Rs\.?)?'
        _WS = r'\s*'
        _NUM = r'(\d[\d,]*\.?\d*)\s*(Cr|Crore|Lakh|Lac|Mn|Bn|B|M|T|Thousand|K|Billion|Million)?'

        # Patterns must be mutually exclusive to prevent false matches.
        # Order matters: more specific patterns first.
        patterns = [
            # Explicit "total addressable market" → TAM
            (r'\btotal\s+addressable\s+market\b.*?' + _CURR_OPT + _WS + _NUM, "tam"),
            # Explicit "serviceable obtainable market" → SOM
            (r'\bserviceable\s+obtainable\s+market\b.*?' + _CURR_OPT + _WS + _NUM, "som"),
            # Explicit "serviceable addressable market" → SAM
            (r'\bserviceable\s+addressable\s+market\b.*?' + _CURR_OPT + _WS + _NUM, "sam"),
            # Acronyms with word boundaries (match whole line up to value)
            (r'\btam\b[:\s]*' + _CURR_OPT + _WS + _NUM, "tam"),
            (r'\bsam\b[:\s]*' + _CURR_OPT + _WS + _NUM, "sam"),
            (r'\bsom\b[:\s]*' + _CURR_OPT + _WS + _NUM, "som"),
        ]

        for pattern, field in patterns:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m:
                existing = [r for r in results if r.semantic_field == field]
                if not existing:
                    num = m.group(1).strip()
                    unit = (m.group(2) or "").strip()
                    val = f"{num} {unit}" if unit else num
                    results.append(VisualMetric(
                        label=field.upper(),
                        value=val,
                        semantic_field=field,
                        confidence=0.75,
                        source="text_fallback",
                    ))

        return results


class FunnelParser:
    """
    Parses funnel diagrams for TAM/SAM/SOM.
    Top of funnel = TAM (widest)
    Middle = SAM
    Bottom = SOM (narrowest)
    
    Detection: blocks with decreasing width from top to bottom.
    """

    @classmethod
    def parse(cls, blocks: List[LayoutBlock]) -> List[VisualMetric]:
        if not blocks or len(blocks) < 3:
            return []

        width_scored = sorted(blocks, key=lambda b: b.width, reverse=True)

        # Assume 3 levels: widest = TAM, middle = SAM, narrowest = SOM
        if len(width_scored) >= 3:
            return [
                cls._block_to_metric(width_scored[0], "tam"),
                cls._block_to_metric(width_scored[1], "sam"),
                cls._block_to_metric(width_scored[2], "som"),
            ]

        return []

    @classmethod
    def _block_to_metric(cls, block: LayoutBlock, field: str) -> VisualMetric:
        values = ConcentricCircleParser._extract_values([block])
        return VisualMetric(
            label=field.upper(),
            value=values[0] if values else "",
            semantic_field=field,
            confidence=0.8 if ConcentricCircleParser._has_currency(block.text) else 0.65,
            source="funnel",
        )


class ChartLabelParser:
    """
    Parses charts by detecting axis labels, legends, and data points.
    """

    AXIS_PATTERNS = [
        (r'(?:revenue|sales|income).*?(?:₹?\s*[\d,]+\.?\d*\s*(?:Cr|Lakh|Mn|Bn|K)?)', "revenue"),
        (r'(?:customers|users).*?([\d,]+\.?\d*\s*(?:K|M|Bn|Thousand|Million|Billion)?)', "customers"),
        (r'(?:growth|yoy|cagr).*?([\d.]+%)', "growth"),
        (r'(?:margin|profit).*?([\d.]+%)', "margin"),
        (r'(?:orders|units).*?([\d,]+\.?\d*)', "orders"),
    ]

    @classmethod
    def parse(cls, blocks: List[LayoutBlock]) -> List[VisualMetric]:
        results = []
        text = " ".join(b.text for b in blocks)
        text_lower = text.lower()

        for pattern, field in cls.AXIS_PATTERNS:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m:
                results.append(VisualMetric(
                    label=field.replace("_", " ").title(),
                    value=m.group(0) if m.group(0) else m.group(1),
                    semantic_field=field,
                    confidence=0.7,
                    source="chart_label",
                ))

        return results


def extract_visual_metrics(page_data: Dict) -> List[VisualMetric]:
    """
    Main entry point: extract visual financial metrics from a page.
    Tries concentric, funnel, then chart label parsing.
    """
    blocks = []
    layout_blocks = PageAdapter.layout_blocks(page_data)
    for lb in layout_blocks:
        blocks.append(LayoutBlock(
            x=lb.get("x0", lb.get("x", 0)),
            y=lb.get("top", lb.get("y", 0)),
            width=lb.get("width", abs(lb.get("x1", 0) - lb.get("x0", 0))),
            height=lb.get("height", abs(lb.get("top", 0) - lb.get("bottom", 0))),
            text=lb.get("text", ""),
            font_size=lb.get("font_size"),
        ))

    page_text = PageAdapter.cleaned_text(page_data)

    results = []

    # 1. Try concentric circle parsing
    concentric = ConcentricCircleParser.parse(blocks, page_text)
    results.extend(concentric)

    # 2. Try funnel parsing (only if concentric didn't get 3)
    if len(concentric) < 3:
        funnel = FunnelParser.parse(blocks)
        results.extend(funnel)

    # 3. Chart label parsing for remaining fields
    chart = ChartLabelParser.parse(blocks)
    existing_fields = {r.semantic_field for r in results}
    for c in chart:
        if c.semantic_field not in existing_fields:
            results.append(c)
            existing_fields.add(c.semantic_field)

    return results


def merge_visual_into_structured(pages: List[Dict], structured_data: Dict) -> Dict:
    """
    Extract visual metrics from all pages and merge into structured_data.
    Only fills in missing fields (does not overwrite LLM-extracted values).
    """
    industry = structured_data.get("industry_overview", {})
    if not isinstance(industry, dict):
        industry = {}
        structured_data["industry_overview"] = industry

    for page in pages:
        page_dict = PageAdapter.to_dict(page)
        metrics = extract_visual_metrics(page_dict)
        for m in metrics:
            if m.semantic_field in ("tam", "sam", "som"):
                if not industry.get(m.semantic_field):
                    industry[m.semantic_field] = m.value
                    confidence_key = f"_{m.semantic_field}_confidence"
                    industry[confidence_key] = m.confidence
                    industry[f"_{m.semantic_field}_source"] = m.source

    return structured_data
