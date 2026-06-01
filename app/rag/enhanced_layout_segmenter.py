"""
Enhanced Layout Segmentation
============================
Improved layout segmentation for pitch deck pages with:
- Better block detection with spatial coordinates
- Visual element classification (KPIs, headings, data, tables)
- Multi-column detection
- Page structure analysis
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class BlockType(Enum):
    """Types of layout blocks"""
    HEADING = "heading"
    SUBHEADING = "subheading"
    KPI_CARD = "kpi_card"
    BODY_TEXT = "body_text"
    TABLE = "table"
    CHART = "chart"
    LIST_ITEM = "list_item"
    CAPTION = "caption"
    FOOTER = "footer"
    UNKNOWN = "unknown"


@dataclass
class LayoutSegment:
    """A segment of the page with semantic classification"""
    x: float
    y: float
    width: float
    height: float
    text: str
    block_type: BlockType = BlockType.UNKNOWN
    font_size: Optional[float] = None
    font_weight: Optional[str] = None
    is_bold: bool = False
    is_italic: bool = False
    confidence: float = 0.5
    metadata: Dict = field(default_factory=dict)


@dataclass 
class PageLayout:
    """Complete page layout structure"""
    page_num: int
    width: float = 0.0
    height: float = 0.0
    segments: List[LayoutSegment] = field(default_factory=list)
    columns: int = 1
    has_kpi_cards: bool = False
    has_tables: bool = False
    has_charts: bool = False
    heading_regions: List[Tuple[float, float]] = field(default_factory=list)  # y-ranges
    data_regions: List[Tuple[float, float]] = field(default_factory=list)


class EnhancedLayoutSegmenter:
    """
    Enhanced layout segmentation with improved visual element detection.
    """
    
    # Heading patterns
    HEADING_PATTERNS = [
        re.compile(r'^(?:TRACTION|TEAM|FUNDING|MARKET|COMPETITION|FINANCIALS|'
                   r'USE OF FUNDS|TECHNOLOGY|PRODUCT|SOLUTION|BUSINESS MODEL|'
                   r'REVENUE|CUSTOMERS|PARTNERS|INVESTMENT|MILESTONES|PROBLEM|'
                   r'RECOGNITION|AWARDS|PIPELINE|ROADMAP|GO TO MARKET)$', re.IGNORECASE),
        re.compile(r'^[A-Z][A-Z\s]{5,60}$'),
        re.compile(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s*$'),  # Title Case headings
    ]
    
    # KPI indicators
    KPI_INDICATORS = [
        "revenue", "arr", "mrr", "customers", "users", "growth", "margin",
        "valuation", "tam", "sam", "som", "market", "orders", "bookings",
        "pipeline", "burn", "runway", "cac", "ltv", "churn", "retention"
    ]
    
    # Large number pattern (KPI values)
    LARGE_NUMBER_PATTERN = re.compile(
        r'(?:₹|\$|Rs\.?)?\s*[\d,]+(?:\.\d+)?\s*(?:Cr|Mn|Bn|Lakh|Lakhs?|K|M)?',
        re.IGNORECASE
    )
    
    def segment_page(self, page_text: str, page_num: int = 0, 
                     raw_words: List[Dict] = None) -> PageLayout:
        """
        Segment a page into semantic regions.
        
        Args:
            page_text: Raw text from the page
            page_num: Page number
            raw_words: Word-level extraction with coordinates (if available)
            
        Returns:
            PageLayout with segmented regions
        """
        layout = PageLayout(page_num=page_num)
        
        if raw_words:
            layout = self._segment_with_coordinates(raw_words)
        else:
            layout = self._segment_text_only(page_text)
        
        # Analyze the layout
        layout = self._analyze_layout_structure(layout, page_text)
        
        return layout
    
    def _segment_with_coordinates(self, words: List[Dict]) -> PageLayout:
        """Segment page using coordinate information from words"""
        if not words:
            return PageLayout(page_num=0)
        
        # Get page dimensions
        max_x = max(w.get("x1", w.get("x", 0)) for w in words)
        max_y = max(w.get("y1", w.get("y", 0)) for w in words)
        
        layout = PageLayout(page_num=0, width=max_x, height=max_y)
        
        # Group words into blocks by Y position (with tolerance)
        y_tolerance = 8
        y_groups = {}
        for word in words:
            y = word.get("top", word.get("y", 0))
            y_rounded = round(y / y_tolerance) * y_tolerance
            if y_rounded not in y_groups:
                y_groups[y_rounded] = []
            y_groups[y_rounded].append(word)
        
        # Create segments from groups
        for y_pos, group in sorted(y_groups.items()):
            # Get all text in this line
            line_text = " ".join(w.get("text", "") for w in group)
            if not line_text.strip():
                continue
            
            # Get coordinates
            min_x = min(w.get("left", w.get("x", 0)) for w in group)
            max_x = max(w.get("x1", w.get("right", w.get("x", 0) + 50)) for w in group)
            min_y = min(w.get("top", w.get("y", 0)) for w in group)
            max_y = max(w.get("y1", w.get("bottom", min_y + 20)) for w in group)
            
            # Determine block type
            block_type = self._classify_block(line_text, group)
            
            # Get font info if available
            font_size = None
            is_bold = False
            for w in group:
                if "size" in w and w["size"]:
                    font_size = w["size"]
                if "fontname" in w and w["fontname"]:
                    is_bold = "Bold" in str(w["fontname"])
            
            segment = LayoutSegment(
                x=min_x,
                y=min_y,
                width=max_x - min_x,
                height=max_y - min_y,
                text=line_text,
                block_type=block_type,
                font_size=font_size,
                is_bold=is_bold,
                confidence=self._calculate_segment_confidence(line_text, block_type)
            )
            layout.segments.append(segment)
        
        # Determine column count
        layout.columns = self._detect_columns(layout.segments)
        
        return layout
    
    def _segment_text_only(self, text: str) -> PageLayout:
        """Segment page from text only (fallback)"""
        layout = PageLayout(page_num=0)
        lines = text.split("\n")
        
        current_y = 0
        line_height = 15
        
        for line in lines:
            line = line.strip()
            if not line:
                current_y += line_height
                continue
            
            block_type = self._classify_block_text_only(line)
            
            segment = LayoutSegment(
                x=0,
                y=current_y,
                width=500,
                height=line_height,
                text=line,
                block_type=block_type,
                confidence=self._calculate_segment_confidence(line, block_type)
            )
            layout.segments.append(segment)
            
            current_y += line_height
        
        return layout
    
    def _classify_block(self, text: str, word_group: List[Dict]) -> BlockType:
        """Classify a block based on text and word properties"""
        text_lower = text.lower()
        
        # Check if it's a heading
        for pattern in self.HEADING_PATTERNS:
            if pattern.match(text.strip()):
                return BlockType.HEADING
        
        # Check if it's a KPI card (large number + keyword)
        has_large_number = self.LARGE_NUMBER_PATTERN.search(text)
        has_kpi_keyword = any(kw in text_lower for kw in self.KPI_INDICATORS)
        
        if has_large_number and has_kpi_keyword:
            return BlockType.KPI_CARD
        
        # Check if it's a list item
        if text.strip().startswith(('•', '-', '*', '1.', '2.', '3.')):
            return BlockType.LIST_ITEM
        
        # Check if it might be a table row
        if '|' in text or '\t' in text:
            return BlockType.TABLE
        
        # Check for chart-related text
        if any(kw in text_lower for kw in ["chart", "graph", "figure", "axis", "%"]):
            return BlockType.CHART
        
        return BlockType.BODY_TEXT
    
    def _classify_block_text_only(self, text: str) -> BlockType:
        """Classify block from text only"""
        # Check heading patterns
        for pattern in self.HEADING_PATTERNS:
            if pattern.match(text.strip()):
                return BlockType.HEADING
        
        # Check for KPI
        if self.LARGE_NUMBER_PATTERN.search(text):
            text_lower = text.lower()
            if any(kw in text_lower for kw in self.KPI_INDICATORS):
                return BlockType.KPI_CARD
        
        # List item
        if text.strip().startswith(('•', '-', '*')):
            return BlockType.LIST_ITEM
        
        # Check for table indicators
        if '|' in text:
            return BlockType.TABLE
        
        return BlockType.BODY_TEXT
    
    def _detect_columns(self, segments: List[LayoutSegment]) -> int:
        """Detect number of columns based on X position distribution"""
        if len(segments) < 3:
            return 1
        
        # Get X positions
        x_positions = [s.x for s in segments if s.x > 0]
        if not x_positions:
            return 1
        
        # Simple heuristic: if there are distinct clusters, multiple columns
        x_set = sorted(set(x_positions))
        if len(x_set) > 2:
            return 2
        
        return 1
    
    def _analyze_layout_structure(self, layout: PageLayout, page_text: str) -> PageLayout:
        """Analyze the overall layout structure"""
        # Find heading regions
        heading_regions = []
        for seg in layout.segments:
            if seg.block_type == BlockType.HEADING:
                heading_regions.append((seg.y, seg.y + seg.height))
        layout.heading_regions = heading_regions
        
        # Find data regions (between headings)
        data_regions = []
        for i in range(len(heading_regions) - 1):
            start = heading_regions[i][1]
            end = heading_regions[i + 1][0]
            if end - start > 50:  # Minimum height for data region
                data_regions.append((start, end))
        layout.data_regions = data_regions
        
        # Check for specific elements
        layout.has_kpi_cards = any(s.block_type == BlockType.KPI_CARD for s in layout.segments)
        layout.has_tables = any(s.block_type == BlockType.TABLE for s in layout.segments)
        layout.has_charts = any(s.block_type == BlockType.CHART for s in layout.segments)
        
        return layout
    
    def _calculate_segment_confidence(self, text: str, block_type: BlockType) -> float:
        """Calculate confidence score for a segment"""
        confidence = 0.5
        
        if block_type == BlockType.HEADING:
            confidence = 0.85
        elif block_type == BlockType.KPI_CARD:
            confidence = 0.9
        elif block_type == BlockType.LIST_ITEM:
            confidence = 0.7
        elif block_type == BlockType.TABLE:
            confidence = 0.8
        
        return confidence
    
    def extract_kpis_from_layout(self, layout: PageLayout) -> List[Dict]:
        """Extract KPI cards from layout segments"""
        kpis = []
        
        for seg in layout.segments:
            if seg.block_type == BlockType.KPI_CARD:
                # Try to extract label and value
                match = self.LARGE_NUMBER_PATTERN.search(seg.text)
                if match:
                    value = match.group(0)
                    label = seg.text.replace(value, "").strip()
                    
                    kpis.append({
                        "label": label,
                        "value": value,
                        "y_position": seg.y,
                        "confidence": seg.confidence
                    })
        
        return kpis
    
    def extract_sections_from_layout(self, layout: PageLayout) -> Dict[str, List[LayoutSegment]]:
        """Group segments into sections based on headings"""
        sections = {}
        current_section = "unknown"
        
        for seg in layout.segments:
            if seg.block_type == BlockType.HEADING:
                # Normalize heading to section name
                heading = seg.text.strip().upper()
                current_section = heading
                
                if current_section not in sections:
                    sections[current_section] = []
            else:
                if current_section not in sections:
                    sections[current_section] = []
                sections[current_section].append(seg)
        
        return sections


# Singleton instance
_segmenter = EnhancedLayoutSegmenter()


def segment_page(page_text: str, page_num: int = 0, 
                 raw_words: List[Dict] = None) -> PageLayout:
    """Convenience function to segment a page"""
    return _segmenter.segment_page(page_text, page_num, raw_words)


def extract_kpis(layout: PageLayout) -> List[Dict]:
    """Convenience function to extract KPIs from layout"""
    return _segmenter.extract_kpis_from_layout(layout)


def extract_sections(layout: PageLayout) -> Dict[str, List[LayoutSegment]]:
    """Convenience function to extract sections from layout"""
    return _segmenter.extract_sections_from_layout(layout)