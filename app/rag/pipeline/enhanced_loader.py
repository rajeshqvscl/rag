"""
Enhanced PDF Loader - Multi-layer extraction pipeline
Page-by-page processing with section detection and fact extraction
"""
from typing import Tuple, List, Dict, Any, Optional
import fitz
import pdfplumber
import io
from dataclasses import dataclass

from app.utils.text_utils import clean_text, safe_lower
from app.rag.pipeline.fact_registry import FactRegistry, Fact, extract_revenue_facts
from app.rag.pipeline.table_extractor import TableExtractor
from app.rag.pipeline.vision_analyzer import LayoutAnalyzer, VisionAnalyzer
from app.rag.pipeline.validation_engine import ValidationEngine


@dataclass
class PageData:
    """Structured page data"""
    page: int
    title: str
    content: str
    tables: List[Dict]
    images: List[bytes]
    sections: List[str]
    layout: Dict
    facts: List[Fact]
    raw_text: str


class EnhancedPDFLoader:
    """
    Multi-layer PDF extraction with:
    - Page-by-page processing
    - Section detection
    - Table extraction
    - Chart/image analysis
    - Fact extraction
    - Validation
    """
    
    SECTION_HEADERS = {
        "traction": ["traction", "milestones", "customers", "clients", "adoption", "usage", "orders", "bookings", "revenue growth"],
        "financials": ["financial", "revenue", "profit", "ebitda", "margin", "unit economics", "pricing", "burn rate", "runway", "cash flow"],
        "market": ["market", "tam", "sam", "som", "opportunity", "industry", "size", "growth rate", "addressable"],
        "competition": ["competition", "competitor", "differentiation", "advantage", "competitive", "unique", "moat", "barriers"],
        "team": ["team", "founder", "co-founder", "ceo", "cto", "advisor", "board", "experience", "background", "leadership"],
        "funding": ["funding", "raising", "investment", "capital", "valuation", "series", "round", "use of funds", "runway"],
        "product": ["product", "technology", "platform", "solution", "service", "feature", "ip", "patent", "development"],
        "awards": ["award", "recognition", "achievement", "certification", "partner", "ecosystem", "clientele"],
        "impact": ["impact", "sustainability", "esg", "social", "environmental", "carbon", "outcome"]
    }
    
    def __init__(self):
        self.table_extractor = TableExtractor()
        self.vision_analyzer = VisionAnalyzer()
        self.layout_analyzer = LayoutAnalyzer()
        self.validation_engine = ValidationEngine()
        self.fact_registry = FactRegistry()
    
    def load(self, file_content: bytes) -> Tuple[str, List[Dict], FactRegistry]:
        """
        Load PDF with full pipeline processing
        
        Returns:
            Tuple of (full_text, pages_data, fact_registry)
        """
        print("[ENHANCED LOADER] Starting multi-layer PDF extraction...")
        
        pages_data = []
        full_text = ""
        self.fact_registry = FactRegistry()
        
        file_content.seek(0) if hasattr(file_content, 'seek') else None
        content = file_content.read() if hasattr(file_content, 'read') else file_content
        
        if len(content) < 100:
            return ("", [], self.fact_registry)
        
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                total_pages = len(pdf.pages)
                print(f"[ENHANCED LOADER] Processing {total_pages} pages...")
                
                for i, page in enumerate(pdf.pages):
                    print(f"[ENHANCED LOADER] Processing page {i+1}/{total_pages}")
                    
                    page_result = self._process_page(page, i + 1)
                    
                    if page_result:
                        pages_data.append(page_result)
                        full_text += page_result.content + "\n"
                        
                        # Add facts to registry
                        for fact in page_result.facts:
                            self.fact_registry.add(fact)
                
        except Exception as e:
            print(f"[ENHANCED LOADER] pdfplumber error: {e}")
            # Fallback to PyMuPDF
            self._fallback_pymupdf(content, pages_data, full_text)
        
        print(f"[ENHANCED LOADER] Extracted {len(self.fact_registry.facts)} facts from {len(pages_data)} pages")
        
        return (full_text, [self._page_to_dict(p) for p in pages_data], self.fact_registry)
    
    def _process_page(self, page, page_num: int) -> Optional[PageData]:
        """Process a single page with all extractors"""
        try:
            text = page.extract_text() or ""
            
            if not text.strip():
                return None
            
            cleaned = clean_text(text)
            
            sections = self._detect_sections(cleaned)
            layout = self.layout_analyzer.extract_page_layout(cleaned)
            title = self._extract_title(cleaned)
            
            tables = self.table_extractor._extract_page_tables(page, page_num)
            
            facts = self._extract_facts(cleaned, page_num, sections)
            
            page_data = PageData(
                page=page_num,
                title=title,
                content=cleaned,
                tables=tables,
                images=[],
                sections=sections,
                layout=layout,
                facts=facts,
                raw_text=text
            )
            
            return page_data
            
        except Exception as e:
            print(f"[ENHANCED LOADER] Page {page_num} error: {e}")
            return None
    
    def _detect_sections(self, text: str) -> List[str]:
        """Detect sections present in text"""
        text_lower = safe_lower(text)
        sections = []
        
        for section, keywords in self.SECTION_HEADERS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score >= 2:
                sections.append(section)
        
        return sections
    
    def _extract_title(self, text: str) -> str:
        """Extract page title from text"""
        lines = text.split('\n')
        
        for line in lines[:5]:
            line = line.strip()
            if line and len(line) < 100:
                if line.isupper() and len(line) > 3:
                    return line
        
        return ""
    
    def _extract_facts(self, text: str, page_num: int, sections: List[str]) -> List[Fact]:
        """Extract facts from text using regex patterns"""
        facts = []
        
        primary_section = sections[0] if sections else "general"
        
        revenue_facts = extract_revenue_facts(text, page_num, primary_section)
        facts.extend(revenue_facts)
        
        return facts
    
    def _page_to_dict(self, page_data: PageData) -> Dict:
        """Convert PageData to dictionary for compatibility"""
        return {
            "page": page_data.page,
            "title": page_data.title,
            "text": page_data.content,
            "tables": page_data.tables,
            "sections": page_data.sections,
            "layout": page_data.layout,
            "facts": [f.to_dict() for f in page_data.facts]
        }
    
    def _fallback_pymupdf(self, content: bytes, pages_data: List, full_text: str):
        """Fallback using PyMuPDF when pdfplumber fails"""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            
            for i, page in enumerate(doc):
                text = page.get_text()
                if text and text.strip():
                    cleaned = clean_text(text)
                    sections = self._detect_sections(cleaned)
                    
                    pages_data.append({
                        "page": i + 1,
                        "title": self._extract_title(cleaned),
                        "text": cleaned,
                        "tables": [],
                        "sections": sections,
                        "layout": {},
                        "facts": []
                    })
                    full_text += cleaned + "\n"
            
            doc.close()
        except Exception as e:
            print(f"[ENHANCED LOADER] PyMuPDF fallback failed: {e}")


def load_pdf(file) -> Tuple[str, List[Dict]]:
    """
    Backward-compatible wrapper for existing code
    Returns full_text and pages list
    """
    loader = EnhancedPDFLoader()
    full_text, pages, registry = loader.load(file)
    return (full_text, pages)