"""
Visual Intelligence Layer — Phase 1 of the accuracy improvement plan.

Detects slide regions (charts, tables, KPIs, titles), classifies chart types,
extracts structured metrics from visual elements, and builds a visual metric
graph that feeds into the canonical registry.

Compared to vision_analyzer.py (which only extracts images and calls Gemini):
  - SlideRegionDetector: bbox-aware page segmentation
  - ChartAnalyzer: heuristic chart type detection + Gemini hybrid
  - VisualMetricGraph: structured evidence linking regions to metrics
  - merge_chart_metrics: populates _chart_metrics in structured_data
"""

import io
import re
import os
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict

from PIL import Image


# ── Data types ──────────────────────────────────────────────────────────

@dataclass
class SlideRegion:
    type: str  # "title", "chart", "table", "kpi_card", "text_body", "footer", "image"
    page: int
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1 (PDF coords, top-down)
    confidence: float
    text: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class ChartAnalysis:
    page: int
    chart_type: str  # "bar", "line", "pie", "area", "funnel", "table", "other"
    title: str
    metrics: List[Dict]  # [{"label": ..., "value": ..., "unit": ..., "confidence": ...}]
    confidence: float
    source: str  # "vision_api", "heuristic", "layout"
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    raw_description: str = ""


@dataclass
class VisualMetricEvidence:
    """A metric extracted from a visual element, with provenance."""
    field: str  # canonical field name, e.g. "total_revenue", "tam"
    value: str
    normalized_value: float = 0.0
    unit: str = ""
    confidence: float = 0.0
    source: str = ""  # "vision_api", "heuristic", "layout"
    chart_type: str = ""
    slide: int = 0
    region_type: str = ""
    raw_text: str = ""


# ── Slide Region Detector ───────────────────────────────────────────────

class SlideRegionDetector:
    """Detects semantic regions on each slide using layout coordinates."""

    MIN_CHART_AREA = 150 * 150       # minimum pixels for a chart region
    MAX_CHART_AREA_RATIO = 0.85      # chart can't fill >85% of page
    KPI_FONT_SIZE_THRESHOLD = 18     # large text is likely a KPI value
    TITLE_FONT_SIZE_THRESHOLD = 16

    @classmethod
    def detect_regions(cls, page_data: dict) -> List[SlideRegion]:
        """Detect regions on a single page from pdfplumber/PyMuPDF data."""
        regions = []
        if isinstance(page_data, dict):
            page_num = page_data.get("page", page_data.get("page_num", 0))
            page_width = page_data.get("width", 612)   # default US Letter
            page_height = page_data.get("height", 792)
            raw_images = page_data.get("images", [])
            # handle both list and integer (intelligent pipeline stores int)
            images = raw_images if isinstance(raw_images, list) else []
            tables = page_data.get("tables", [])
            # Allow empty list for non-existent keys
            if not isinstance(tables, list):
                tables = []
            layout_blocks = page_data.get("layout_blocks", [])
            if not isinstance(layout_blocks, list):
                layout_blocks = []
            fonts = page_data.get("fonts", [])
            if not isinstance(fonts, list):
                fonts = []
        else:
            page_num = getattr(page_data, "page_num", getattr(page_data, "page", 0))
            page_width = getattr(page_data, "width", 612)
            page_height = getattr(page_data, "height", 792)
            images = getattr(page_data, "images", [])
            tables = getattr(page_data, "tables", [])
            layout_blocks = getattr(page_data, "layout_blocks", [])
            fonts = getattr(page_data, "fonts", [])

        for img in images:
            if isinstance(img, dict):
                bbox = cls._get_image_bbox(img, page_width, page_height)
                if bbox:
                    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                    if area >= cls.MIN_CHART_AREA:
                        regions.append(SlideRegion(
                             type="chart",
                             page=page_num,
                             bbox=bbox,
                             confidence=0.6,
                             metadata={"xref": img.get("xref"), "width": img.get("width"), "height": img.get("height")}
                        ))

        # 2. Detect table regions from pdfplumber
        if isinstance(tables, list):
            for tbl in tables:
                if isinstance(tbl, dict) and "bbox" in tbl:
                    bbox = tuple(tbl["bbox"])
                    regions.append(SlideRegion(
                        type="table",
                        page=page_num,
                        bbox=bbox,
                        confidence=0.8,
                        text=str(tbl.get("data", ""))[:200]
                    ))

        # 3. Detect KPI card regions from layout blocks (large isolated numbers)
        if layout_blocks:
            kpi_regions = cls._detect_kpi_regions(layout_blocks, page_num)
            regions.extend(kpi_regions)

        # 4. Detect title region from font analysis
        if fonts:
            title_region = cls._detect_title(layout_blocks, fonts, page_num, page_width)
            if title_region:
                regions.append(title_region)

        # Merge overlapping regions (keep higher-confidence type)
        regions = cls._merge_overlapping(regions)
        return regions

    @classmethod
    def _get_image_bbox(cls, img: dict, page_w: float, page_h: float) -> Optional[Tuple]:
        xref = img.get("xref")
        if xref is not None:
            return (0, 0, page_w, page_h)
        return None

    @classmethod
    def _detect_kpi_regions(cls, blocks: List[Dict], page_num: int) -> List[SlideRegion]:
        regions = []
        for block in blocks:
            text = block.get("text", "").strip()
            if not text:
                continue
            numbers = re.findall(r'[₹$€]?\s*[\d,]+\.?\d*\s*(?:Cr|Lakh|Mn|Bn|%|K|M|B|T)?', text)
            font_size = block.get("font_size", 0)
            is_large = font_size >= cls.KPI_FONT_SIZE_THRESHOLD
            has_large_number = any(len(n) >= 4 for n in numbers)
            if is_large and has_large_number:
                x0 = block.get("x0", block.get("x", 0))
                y0 = block.get("top", block.get("y", 0))
                x1 = block.get("x1", x0 + block.get("width", 100))
                y1 = block.get("bottom", block.get("height", 30) + y0)
                regions.append(SlideRegion(
                    type="kpi_card",
                    page=page_num,
                    bbox=(x0, y0, x1, y1),
                    confidence=0.7,
                    text=text
                ))
        return regions

    @classmethod
    def _detect_title(cls, blocks: List[Dict], fonts: List[Dict],
                      page_num: int, page_w: float) -> Optional[SlideRegion]:
        if blocks:
            top_blocks = sorted(blocks, key=lambda b: b.get("top", b.get("y", 0)))[:3]
            title_text = " ".join(b.get("text", "") for b in top_blocks if b.get("text"))
            if title_text and len(title_text) < 80:
                b = top_blocks[0]
                x0 = b.get("x0", b.get("x", 0))
                y0 = b.get("top", b.get("y", 0))
                return SlideRegion(
                    type="title",
                    page=page_num,
                    bbox=(x0, y0, page_w, y0 + 40),
                    confidence=0.6,
                    text=title_text
                )
        if fonts:
            title_sizes = [f["size"] for f in fonts if f.get("size", 0) >= cls.TITLE_FONT_SIZE_THRESHOLD]
            if title_sizes:
                return SlideRegion(
                    type="title",
                    page=page_num,
                    bbox=(0, 0, page_w, 60),
                    confidence=0.4,
                    text=""
                )
        return None

    @classmethod
    def _merge_overlapping(cls, regions: List[SlideRegion]) -> List[SlideRegion]:
        if not regions:
            return []
        sorted_regs = sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))
        merged = [sorted_regs[0]]
        TYPE_PRIORITY = {"chart": 5, "table": 4, "kpi_card": 3, "title": 2, "text_body": 1}
        for r in sorted_regs[1:]:
            last = merged[-1]
            if cls._boxes_overlap(r.bbox, last.bbox, threshold=0.3):
                if TYPE_PRIORITY.get(r.type, 0) > TYPE_PRIORITY.get(last.type, 0):
                    merged[-1] = r
            else:
                merged.append(r)
        return merged

    @staticmethod
    def _boxes_overlap(a: Tuple, b: Tuple, threshold: float = 0.3) -> bool:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ix0 = max(ax0, bx0)
        iy0 = max(ay0, by0)
        ix1 = min(ax1, bx1)
        iy1 = min(ay1, by1)
        if ix1 <= ix0 or iy1 <= iy0:
            return False
        intersection = (ix1 - ix0) * (iy1 - iy0)
        min_area = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
        return min_area > 0 and intersection / min_area >= threshold


# ── Chart Analyzer (Heuristic + Vision API hybrid) ──────────────────────

class ChartAnalyzer:
    """
    Analyzes chart images using a hybrid approach:
    1. Heuristic pre-filter (cheap, fast) to classify chart vs non-chart
    2. Heuristic chart type detection (bar/line/pie)
    3. Gemini Vision API for structured metric extraction (expensive)
    4. Heuristic fallback when API unavailable
    """

    # Chart type signatures: (aspect_ratio_min, aspect_ratio_max, color_count_range)
    CHART_SIGNATURES = {
        "pie":     (0.8, 1.2, (4, 20)),
        "bar":     (1.2, 2.5, (2, 12)),
        "line":    (1.5, 3.0, (2, 8)),
        "area":    (1.5, 3.0, (2, 8)),
        "funnel":  (0.5, 0.9, (3, 10)),
    }

    def __init__(self):
        self._vision_client = None
        self._init_vision()

    def _init_vision(self):
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._vision_client = genai
            except ImportError:
                pass

    # ── Heuristic analysis ──────────────────────────────────────────

    @staticmethod
    def _analyze_colors(img: Image.Image) -> Dict:
        """Analyze color properties of an image."""
        try:
            reduced = img.convert("P", palette=Image.Palette.WEB) if img.mode != "P" else img
            palette = reduced.getpalette()
            if not palette:
                return {"unique_colors": 1, "entropy": 0.0, "dominant_ratio": 1.0}

            import numpy as np
            arr = np.array(reduced)
            counts = np.bincount(arr.flatten(), minlength=256)
            nonzero = counts[counts > 0]
            unique = len(nonzero)

            probs = nonzero / nonzero.sum()
            entropy = -np.sum(probs * np.log2(probs + 1e-10))

            dominant = counts.max() / counts.sum() if counts.sum() > 0 else 1.0

            return {"unique_colors": int(unique), "entropy": float(entropy), "dominant_ratio": float(dominant)}
        except Exception:
            return {"unique_colors": 1, "entropy": 0.0, "dominant_ratio": 1.0}

    def is_actual_chart(self, image_bytes: bytes, page_text: str = "") -> Tuple[bool, float]:
        """
        Improved chart detection using image properties and structural heuristics.
        Returns (is_chart, confidence).
        """
        try:
            # 1. Structural keyword/currency pre-filter (skip OCR on non-financial elements)
            if page_text:
                page_text_lower = page_text.lower()
                has_currency = any(sym in page_text for sym in ["₹", "$", "€", "£"])
                has_financial = any(kw in page_text_lower for kw in [
                    "revenue", "arr", "growth", "margin", "ebitda", "pipeline", 
                    "funding", "valuation", "tam", "sam", "som"
                ])
                if not (has_currency or has_financial):
                    return False, 0.0

            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            aspect = w / h if h > 0 else 1.0

            # Size filter
            if w < 150 or h < 100:
                return False, 0.0
            area = w * h
            if area < 150 * 150:
                return False, 0.0

            # Color analysis
            colors = self._analyze_colors(img)
            unique_colors = colors["unique_colors"]
            entropy = colors["entropy"]
            dominant_ratio = colors["dominant_ratio"]

            # Pre-filter threshold financial_threshold = 0.25 in color analysis
            color_score = 1.0 - dominant_ratio
            if color_score < 0.25:  # i.e., dominant_ratio > 0.75 (solid layout blocks)
                return False, 0.0

            score = 0.0

            if 1.0 <= aspect <= 3.0:
                score += 0.2
            if 3 <= unique_colors <= 25:
                score += 0.3
            elif unique_colors > 25:
                score -= 0.2
            if dominant_ratio < 0.6:
                score += 0.2
            else:
                score -= 0.1
            if 3.0 <= entropy <= 7.5:
                score += 0.2
            elif entropy < 2.0:
                score -= 0.2

            return score >= 0.5, round(min(score + 0.2, 0.95), 2)

        except Exception:
            return False, 0.0

    def classify_chart_type_heuristic(self, image_bytes: bytes) -> Tuple[str, float]:
        """
        Heuristic chart type detection without vision API.
        Returns (chart_type, confidence).
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            aspect = w / h if h > 0 else 1.0

            colors = self._analyze_colors(img)
            uc = colors["unique_colors"]

            best_type = "other"
            best_score = 0.0

            for ctype, (amin, amax, (cmin, cmax)) in self.CHART_SIGNATURES.items():
                score = 0.0
                if amin <= aspect <= amax:
                    score += 0.4
                if cmin <= uc <= cmax:
                    score += 0.3
                if score > best_score:
                    best_score = score
                    best_type = ctype

            # Edge detection for bar vs line
            if best_type in ("bar", "line") and best_score < 0.6:
                try:
                    gray = img.convert("L")
                    import numpy as np
                    arr = np.array(gray)
                    dx = np.abs(np.diff(arr.astype(float), axis=1)).mean()
                    dy = np.abs(np.diff(arr.astype(float), axis=0)).mean()
                    if dy > dx * 1.5:
                        best_type = "bar"
                    else:
                        best_type = "line"
                except Exception:
                    pass

            return best_type, round(min(best_score + 0.3, 0.85), 2)

        except Exception:
            return "other", 0.0

    # ── Vision API analysis ─────────────────────────────────────────

    def analyze_with_vision(self, image_bytes: bytes) -> Optional[Dict]:
        """Use Gemini Vision API to extract structured chart data."""
        if not self._vision_client:
            return None
        try:
            img = Image.open(io.BytesIO(image_bytes))
            prompt = """Analyze this chart or diagram from a startup pitch deck.

Return ONLY valid JSON with these fields:
- chart_type: "bar" | "line" | "pie" | "area" | "funnel" | "table" | "kpi_card" | "other"
- title: chart title or "unknown"
- metrics: array of {label, value, unit} for key data points shown
  * For bar/line: extract ALL visible data points with their labels
  * For pie: extract all slices
  * For KPI cards: extract the metric name and value
- key_insight: one sentence about what this data shows
- confidence: 0.0-1.0 how confident you are in the extraction

If this is NOT a chart/diagram (logo, photo, icon), return:
{"chart_type": "non_chart", "title": "", "metrics": [], "key_insight": "", "confidence": 0.0}"""

            model = self._vision_client.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content([prompt, img])
            text = response.text

            json_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if json_match:
                import json as _json
                result = _json.loads(json_match.group())
                result["raw_response"] = text[:500]
                return result
            return {"chart_type": "analyzed", "title": "chart", "metrics": [], "raw_response": text[:300]}
        except Exception as e:
            print(f"[CHART_ANALYZER] Vision API error: {e}")
            return None

    # ── Combined analysis ───────────────────────────────────────────

    def analyze_chart(self, image_bytes: bytes, page_num: int = 0) -> Optional[ChartAnalysis]:
        """Hybrid chart analysis: try Vision API first, fallback to heuristic."""
        vision_result = self.analyze_with_vision(image_bytes)

        if vision_result and vision_result.get("chart_type") != "non_chart":
            ct = vision_result.get("chart_type", "other")
            metrics = vision_result.get("metrics", [])
            title = vision_result.get("title", "")
            conf = vision_result.get("confidence", 0.5)
            return ChartAnalysis(
                page=page_num,
                chart_type=ct,
                title=title,
                metrics=[
                    {"label": m.get("label", ""), "value": m.get("value", ""),
                     "unit": m.get("unit", ""), "confidence": m.get("confidence", 0.5)}
                    for m in metrics
                ] if metrics else [],
                confidence=conf,
                source="vision_api",
                raw_description=vision_result.get("key_insight", ""),
            )

        ct, conf = self.classify_chart_type_heuristic(image_bytes)
        if ct != "other":
            return ChartAnalysis(
                page=page_num,
                chart_type=ct,
                title="",
                metrics=[],
                confidence=conf * 0.7,
                source="heuristic",
            )

        return None


# ── Visual Metric Graph ──────────────────────────────────────────────────

def build_visual_metric_graph(chart_analyses: List[ChartAnalysis],
                              page_regions: List[SlideRegion]) -> Dict[str, List[VisualMetricEvidence]]:
    """
    Build a structured graph of all visual metric evidence.
    Groups by canonical field name for downstream use.
    """
    graph: Dict[str, List[VisualMetricEvidence]] = defaultdict(list)

    for ca in chart_analyses:
        for m in ca.metrics:
            label = m.get("label", "").lower().strip()
            value = m.get("value", "")
            unit = m.get("unit", "")

            if not value:
                continue

            # Map chart label to canonical field
            field = _map_label_to_field(label, ca.chart_type)

            if field:
                try:
                    from app.rag.number_utils import parse_indian_number
                    norm_val = parse_indian_number(value)
                except Exception:
                    norm_val = 0.0

                evidence = VisualMetricEvidence(
                    field=field,
                    value=f"{value} {unit}".strip(),
                    normalized_value=norm_val,
                    unit=unit,
                    confidence=m.get("confidence", ca.confidence),
                    source=ca.source,
                    chart_type=ca.chart_type,
                    slide=ca.page,
                    region_type="chart",
                    raw_text=label,
                )
                graph[field].append(evidence)

    return dict(graph)


# ── Field mapping ────────────────────────────────────────────────────────

_FIELD_KEYWORDS = [
    # (keywords, canonical_field)
    (["total revenue", "revenue", "total income", "sales", "topline", "turnover", "arr", "annual recurring"],
     "total_revenue"),
    (["current revenue", "period revenue", "current period", "this period"], "current_period_revenue"),
    (["historical revenue", "previous revenue", "last year revenue", "fy"], "historical_revenue"),
    (["invoiced", "invoice amount", "billed"], "invoiced_amount"),
    (["purchase order", "po value", "expected po"], "purchase_order_value"),
    (["tam", "total addressable market", "addressable market"], "tam"),
    (["sam", "serviceable addressable market"], "sam"),
    (["som", "serviceable obtainable market", "obtainable market"], "som"),
    (["funding", "fundraise", "current raise", "raising", "investment"], "funding_raise"),
    (["valuation", "pre-money", "post-money", "company valuation"], "valuation"),
    (["pipeline", "pipeline value", "expected value"], "pipeline_value"),
    (["orders", "bookings", "order book", "expected units"], "orders"),
    (["customers", "clients", "users", "active users"], "customers"),
    (["growth", "yoy", "cagr", "growth rate"], "growth_rate"),
    (["margin", "gross margin", "profit margin"], "gross_margin"),
    (["grant", "government grant", "grant received"], "government_grants"),
]

# Chart-type-specific field hints
_CHART_TYPE_FIELD_HINTS = {
    "pie": {"tam", "sam", "som", "funding_raise", "valuation"},
    "funnel": {"tam", "sam", "som"},
    "bar": {"total_revenue", "current_period_revenue", "historical_revenue",
            "orders", "customers", "growth_rate"},
    "line": {"total_revenue", "current_period_revenue", "historical_revenue",
             "growth_rate", "margin"},
    "area": {"total_revenue", "current_period_revenue", "historical_revenue"},
}


def _map_label_to_field(label: str, chart_type: str = "") -> Optional[str]:
    """Map a chart label or metric name to a canonical field name."""
    if not label:
        return None

    label_lower = label.lower().strip()

    # Check chart-type hints first (narrows the search space)
    if chart_type in _CHART_TYPE_FIELD_HINTS:
        hint_fields = _CHART_TYPE_FIELD_HINTS[chart_type]
        for keywords, field in _FIELD_KEYWORDS:
            if field in hint_fields:
                for kw in keywords:
                    if kw in label_lower or label_lower in kw:
                        return field

    # Full keyword search
    best_match = None
    best_score = 0
    for keywords, field in _FIELD_KEYWORDS:
        for kw in keywords:
            if kw in label_lower:
                score = len(kw) / max(len(label_lower), 1)
                if score > best_score:
                    best_score = score
                    best_match = field

    return best_match


def _find_slide_title(regions: List[SlideRegion], chart_page: int) -> str:
    """Find the slide title for a given page."""
    for r in regions:
        if r.type == "title" and r.page == chart_page:
            return r.text
    return ""


# ── Financial chart classification (reduces non-financial chart noise) ──

_FINANCIAL_CHART_TITLES = [
    "revenue", "growth", "market size", "tam", "sam", "som", "funding",
    "valuation", "projection", "forecast", "p&l", "profit", "margin",
    "customers", "traction", "milestone", "unit economics", "cac",
    "ltv", "burn", "runway", "arr", "cost", "revenue breakdown",
    "business model", "pipeline", "orders", "sales",
]

_FINANCIAL_PAGE_TITLES = [
    "financial", "metrics", "kpi", "revenue", "funding",
    "market size", "growth", "traction", "unit economics",
]

_NON_FINANCIAL_CHART_CLUES = [
    "roadmap", "architecture", "flowchart", "diagram", "timeline",
    "org chart", "organization", "process flow", "how it works",
    "team photo", "logo", "screenshot", "ui mockup",
]


def _is_financial_chart(chart: ChartAnalysis, slide_title: str = "") -> bool:
    """Determine if a chart is financially relevant (revenue, market, funding, etc.)."""
    title_lower = (chart.title or "").lower()
    slide_lower = (slide_title or "").lower()
    combined = f"{title_lower} {slide_lower}"

    # Reject clearly non-financial charts
    for clue in _NON_FINANCIAL_CHART_CLUES:
        if clue in combined:
            return False

    # Accept charts with financial keywords
    for kw in _FINANCIAL_CHART_TITLES:
        if kw in combined:
            return True

    # Accept bar/line/pie charts (likely data, not decorative)
    if chart.chart_type in ("bar", "line", "pie", "area"):
        return True
    if chart.chart_type == "table" and any(c.isdigit() for c in combined[:100]):
        return True

    return False


# ── Integration point ────────────────────────────────────────────────────

def _estimate_total_charts(file_content: bytes) -> int:
    """Quick estimate of chart count without full analysis (for lightweight mode decision)."""
    try:
        import fitz
        doc = fitz.open(stream=file_content, filetype="pdf")
        total = sum(len(page.get_images(full=True)) for page in doc)
        doc.close()
        return total
    except Exception:
        return 0


def analyze_pdf_charts(file_content: bytes,
                       pdf_pages: List[Dict],
                       max_charts: int = 30,
                       is_lightweight: bool = False) -> Tuple[List[ChartAnalysis], Dict[str, List[VisualMetricEvidence]], List[SlideRegion]]:
    """
    Full visual intelligence pipeline for a PDF.
    Applies financial chart filtering and large-deck lightweight mode.

    Args:
        file_content: PDF bytes
        pdf_pages: list of page dicts
        max_charts: maximum charts to analyze (budget from complexity scorer)
        is_lightweight: if True, only do region detection, skip Vision API analysis

    Returns (chart_analyses, visual_metric_graph, all_regions).
    """
    import fitz

    analyzer = ChartAnalyzer()
    all_charts: List[ChartAnalysis] = []
    all_regions: List[SlideRegion] = []

    if is_lightweight:
        print(f"[VISUAL_INTEL] Lightweight mode — region detection only, no chart analysis")
        for page_data in pdf_pages:
            regions = SlideRegionDetector.detect_regions(page_data)
            all_regions.extend(regions)
        # Build empty graph
        visual_graph: Dict[str, List[VisualMetricEvidence]] = {}
        print(f"[VISUAL_INTEL] Detected {len(all_regions)} page regions (lightweight)")
        return all_charts, visual_graph, all_regions

    def _safe_get_text(pd):
        if isinstance(pd, dict):
            return pd.get("text", pd.get("content", ""))
        return getattr(pd, "content", getattr(pd, "text", ""))

    # Weighted page scoring for financial content detection
    financial_weights = {
        # Core Financials
        "revenue": 3, "arr": 3, "invoiced": 3, "billing": 3,
        "profit": 3, "ebitda": 3, "margin": 2, "burn rate": 2, "cash flow": 2,
        # Market Sizing
        "tam": 4, "sam": 4, "som": 4, "market size": 4, "market opportunity": 3,
        # Funding & Valuation
        "funding": 3, "valuation": 4, "investment": 3, "series a": 3, "seed": 2,
        "pre-money": 3, "post-money": 3, "term sheet": 3, "raise": 2, "ask": 3,
        # Operational Traction & Pipeline
        "customers": 2, "orders": 3, "bookings": 3, "pipeline": 3, "growth": 2,
        "projection": 3, "forecast": 3, "target": 2, "vision": 2,
        "loi": 3, "mou": 2, "contracts": 3, "pilot": 2, "deployment": 2,
        "franchise": 3, "expansion": 2, "advance purchase": 3, "advance order": 3,
        # Government & Grants
        "grant": 3, "subsidy": 3, "government": 2,
        "po": 3, "purchase order": 4,
        # Domain Specific (Defense, Climate, Agri)
        "defence": 2, "defense": 2, "army": 2, "bel": 2, "drdo": 2,
        "climate": 2, "renewable": 3, "solar": 2, "infra": 2, "infrastructure": 2,
        "agri": 2, "rural": 2, "farmer": 2, "healthcare": 2, "diagnostic": 2,
        # Currency Identifiers
        "crore": 2, "lakh": 2, "₹": 2, "inr": 2, "usd": 2, "$": 2, "mn": 2, "million": 2,
    }

    page_texts = []
    page_scores = []
    for page_data in pdf_pages:
        page_text = _safe_get_text(page_data)
        page_texts.append(page_text.lower())

        score = 0
        text_lower = page_text.lower()
        for keyword, weight in financial_weights.items():
            if keyword in text_lower:
                score += weight

        page_scores.append(score)

    FINANCIAL_SCORE_THRESHOLD = 2
    financial_pages = set()
    for idx, score in enumerate(page_scores):
        if score >= FINANCIAL_SCORE_THRESHOLD:
            financial_pages.add(idx + 1)

    avg_score = sum(page_scores) / len(page_scores) if page_scores else 0
    max_score = max(page_scores) if page_scores else 0
    print(f"[VISUAL_INTEL] Page scores: avg={avg_score:.1f}, max={max_score}, threshold={FINANCIAL_SCORE_THRESHOLD}")
    print(f"[VISUAL_INTEL] Fast pre-filter: {len(financial_pages)}/{len(pdf_pages)} pages likely contain financial content")
    
    # 1. Detect regions on every page (but only for financial pages)
    for page_data in pdf_pages:
        page_num = page_data.get("page", 0) if isinstance(page_data, dict) else getattr(page_data, "page", 0)
        # Skip expensive region detection for non-financial pages
        if page_num not in financial_pages and len(pdf_pages) > 10:
            continue
        regions = SlideRegionDetector.detect_regions(page_data)
        all_regions.extend(regions)
    print(f"[VISUAL_INTEL] Detected {len(all_regions)} page regions from {len(pdf_pages)} pages")

    # Hard cap on regions to prevent explosion
    MAX_REGIONS = 50
    if len(all_regions) > MAX_REGIONS:
        print(f"[VISUAL_INTEL] Capping regions from {len(all_regions)} to {MAX_REGIONS}")
        all_regions = all_regions[:MAX_REGIONS]

    # 2. First pass: scan all images with cheap filters, collect candidates with relevance scores
    doc = fitz.open(stream=file_content, filetype="pdf")
    candidates = []  # (relevance_score, page_num, image_bytes, slide_title)

    for page_idx, page in enumerate(doc):
        images = page.get_images(full=True)
        page_num = page_idx + 1
        slide_title = _find_slide_title(all_regions, page_num) or ""

        for img in images:
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                w, h = base_image.get("width", 0), base_image.get("height", 0)

                if w < 100 or h < 100:
                    continue
                
                # Pass page text to skip non-financial elements
                current_page_text = page_texts[page_idx] if page_idx < len(page_texts) else ""
                is_chart, chart_conf = analyzer.is_actual_chart(image_bytes, page_text=current_page_text)
                if not is_chart:
                    continue

                # Relevance score based on slide title + image size
                relevance = chart_conf
                title_lower = slide_title.lower()
                for kw in _FINANCIAL_CHART_TITLES:
                    if kw in title_lower:
                        relevance += 0.3
                for kw in _NON_FINANCIAL_CHART_CLUES:
                    if kw in title_lower:
                        relevance -= 0.5
                # Larger images get priority (likely more important charts)
                relevance += min(w * h / (500 * 300), 0.15)
                # Prefer later pages (data sections are usually at the end of pitch decks)
                relevance += min((page_num / 30) * 0.1, 0.1)

                candidates.append((relevance, page_num, image_bytes, slide_title))
            except Exception as e:
                print(f"[VISUAL_INTEL] Scan error page {page_num}: {e}")

    # Sort by relevance descending, take top max_charts
    candidates.sort(key=lambda x: -x[0])
    selected = candidates[:max_charts]
    if len(candidates) > max_charts:
        dropped = len(candidates) - max_charts
        avg_relevance_top = sum(c[0] for c in selected) / max(len(selected), 1)
        avg_relevance_dropped = sum(c[0] for c in candidates[max_charts:]) / max(dropped, 1)
        print(f"[VISUAL_INTEL] Ranked {len(candidates)} chart candidates, kept top {max_charts} "
              f"(avg relevance kept={avg_relevance_top:.2f}, dropped={avg_relevance_dropped:.2f})")

    # 3. Second pass: full analysis on top-ranked candidates
    analyzed_charts = 0
    for relevance, page_num, image_bytes, slide_title in selected:
        if analyzed_charts >= max_charts:
            print(f"[VISUAL_INTEL] Budget limit reached: analyzed {analyzed_charts} charts. Stopping pass 2.")
            break
        try:
            analysis = analyzer.analyze_chart(image_bytes, page_num)
            if analysis:
                if not analysis.title:
                    analysis.title = slide_title
                all_charts.append(analysis)
                analyzed_charts += 1
            else:
                # Heuristic fallback for candidates that failed vision analysis
                ct, conf = analyzer.classify_chart_type_heuristic(image_bytes)
                if ct != "other":
                    all_charts.append(ChartAnalysis(
                        page=page_num, chart_type=ct, title=slide_title,
                        metrics=[], confidence=conf * 0.6, source="heuristic"
                    ))
                    analyzed_charts += 1
        except Exception as e:
            print(f"[VISUAL_INTEL] Analysis error page {page_num}: {e}")

    doc.close()

    # 4. Build visual metric graph
    visual_graph = build_visual_metric_graph(all_charts, all_regions)

    print(f"[VISUAL_INTEL] Analyzed {len(all_charts)} charts (max={max_charts}), "
          f"mapped {sum(len(v) for v in visual_graph.values())} metric evidences "
          f"across {len(visual_graph)} fields")

    return all_charts, visual_graph, all_regions


def merge_chart_metrics(structured_data: dict,
                        visual_graph: Dict[str, List[VisualMetricEvidence]]) -> dict:
    """
    Merge visual metric evidence into structured_data as _chart_metrics.
    Does NOT overwrite existing LLM-extracted values — only adds evidence
    for downstream (canonical builder, validation engine) to use.
    """
    chart_metrics = {}
    for field, evidences in visual_graph.items():
        best = max(evidences, key=lambda e: e.confidence)
        chart_metrics[field] = {
            "value": best.value,
            "normalized_value": best.normalized_value,
            "confidence": best.confidence,
            "source": best.source,
            "chart_type": best.chart_type,
            "slide": best.slide,
            "all_evidences": [
                {"value": e.value, "confidence": e.confidence, "source": e.source, "slide": e.slide}
                for e in evidences
            ],
        }

    structured_data["_chart_metrics"] = chart_metrics
    if chart_metrics:
        print(f"[CHART_MERGE] Injected {len(chart_metrics)} chart-derived metrics: "
              f"{', '.join(chart_metrics.keys())}")
    return structured_data
