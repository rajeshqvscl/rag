"""
Vision Analyzer - Chart and image extraction using Vision LLM
Extracts business metrics from charts/graphs that text extraction misses
"""
import base64
import io
from typing import Dict, List, Any, Optional
from PIL import Image
import fitz


class VisionAnalyzer:
    """
    Analyzes charts and images using vision-capable LLM
    """
    
    def __init__(self, llm_client=None):
        self.llm = llm_client
    
    def extract_from_image_bytes(self, image_bytes: bytes, query: str = "Extract all business metrics") -> Optional[Dict]:
        """
        Extract metrics from image bytes
        
        Args:
            image_bytes: Raw image data
            query: Specific extraction query
        
        Returns:
            Dict with extracted metrics
        """
        if not self.llm:
            return None
        
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            base64_img = base64.b64encode(image_bytes).decode('utf-8')
            
            prompt = f"""Analyze this image/chart. Extract ONLY actual business metrics.
            Do NOT read axis labels as data values.
            Look for: revenue figures, growth rates, percentages, customer counts.
            
            Return JSON:
            {{
                "metrics": [
                    {{"name": "metric_name", "value": "X", "context": "what this represents"}}
                ],
                "chart_type": "bar/line/pie/etc",
                "title": "chart title if visible"
            }}
            
            Query: {query}
            """
            
            response = self.llm.chat_completion(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_img}"}}
                    ]
                }],
                model="gpt-4o-mini"
            )
            
            if response and "{" in response:
                import json
                start = response.find("{")
                end = response.rfind("}") + 1
                return json.loads(response[start:end])
            
        except Exception as e:
            print(f"[VISION ANALYZER] Error: {e}")
        
        return None
    
    def extract_chart_page(self, pdf_bytes: bytes, page_num: int, llm_client=None) -> Optional[Dict]:
        """
        Extract embedded chart from specific PDF page
        
        Args:
            pdf_bytes: PDF file bytes
            page_num: 1-indexed page number
            llm_client: LLM client for vision analysis
        
        Returns:
            Dict with chart data
        """
        if llm_client:
            self.llm = llm_client
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            if page_num > len(doc):
                return None
            
            page = doc[page_num - 1]  # 0-indexed
            
            images = page.get_images(full=True)
            
            if not images:
                return None
            
            for img_index, img in enumerate(images):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                result = self.extract_from_image_bytes(image_bytes)
                if result:
                    return result
            
            doc.close()
            
        except Exception as e:
            print(f"[VISION ANALYZER] PDF page error: {e}")
        
        return None
    
    def analyze_chart_for_revenue(self, pdf_bytes: bytes, page_num: int) -> Optional[Dict]:
        """Specialized revenue extraction from charts"""
        return self.extract_chart_page(
            pdf_bytes, 
            page_num,
            query="Extract revenue figures, growth rates, YoY comparison"
        )
    
    def _is_likely_chart(self, image_bytes: bytes) -> bool:
        """Heuristic check if image is likely a chart vs logo/icon/decorative"""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size

            if w < 150 or h < 150:
                return False

            if w * h < 20000:
                return False

            if img.mode != 'RGB':
                img = img.convert('RGB')

            quantized = img.quantize(colors=16)
            palette = quantized.getpalette()
            if not palette:
                return True
            used_colors = set()
            for i in range(quantized.palette_size()):
                offset = i * 3
                r, g, b = palette[offset:offset+3]
                used_colors.add((r >> 5, g >> 5, b >> 5))
            unique = len(used_colors)

            if unique <= 2:
                return False

            pixels = list(img.getdata())
            r_vals = [p[0] for p in pixels]
            g_vals = [p[1] for p in pixels]
            b_vals = [p[2] for p in pixels]

            def variance(vals):
                mean = sum(vals) / len(vals)
                return sum((x - mean) ** 2 for x in vals) / len(vals)

            var_r = variance(r_vals)
            var_g = variance(g_vals)
            var_b = variance(b_vals)
            avg_variance = (var_r + var_g + var_b) / 3

            if avg_variance < 500:
                return False

            return True

        except Exception as e:
            print(f"[VISION ANALYZER] Chart classification error: {e}")
            return True

    def get_all_chart_pages(self, pdf_bytes: bytes) -> List[int]:
        """Find all pages with actual charts (not logos/icons)"""
        chart_pages = []
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            for i, page in enumerate(doc):
                images = page.get_images(full=True)
                if not images:
                    continue
                page_text = page.get_text()
                for img in images:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    if self._is_likely_chart(image_bytes):
                        chart_pages.append(i + 1)
                        break
            
            doc.close()
        except Exception as e:
            print(f"[VISION ANALYZER] Chart detection error: {e}")
        
        return chart_pages


class LayoutAnalyzer:
    """
    Analyzes PDF layout for section detection
    """
    
    SECTION_HEADERS = {
        "traction": ["TRACTION", "MILESTONES", "CUSTOMERS", "CLIENTS", "ADOPTION", "USAGE", "ORDERS", "BOOKINGS", "REVENUE GROWTH"],
        "financials": ["FINANCIAL", "REVENUE", "PROFIT", "EBITDA", "MARGIN", "UNIT ECONOMICS", "PRICING", "BURN RATE", "RUNWAY", "CASH FLOW"],
        "market": ["MARKET", "TAM", "SAM", "SOM", "OPPORTUNITY", "INDUSTRY", "SIZE", "GROWTH RATE", "ADDRESSABLE"],
        "competition": ["COMPETITION", "COMPETITOR", "DIFFERENTIATION", "ADVANTAGE", "COMPETITIVE", "UNIQUE", "MOAT", "BARRIERS"],
        "team": ["TEAM", "FOUNDER", "CO-FOUNDER", "CEO", "CTO", "ADVISOR", "BOARD", "EXPERIENCE", "BACKGROUND", "LEADERSHIP"],
        "funding": ["FUNDING", "RAISING", "INVESTMENT", "CAPITAL", "VALUATION", "SERIES", "ROUND", "USE OF FUNDS", "RUNWAY"],
        "product": ["PRODUCT", "TECHNOLOGY", "PLATFORM", "SOLUTION", "SERVICE", "FEATURE", "IP", "PATENT", "DEVELOPMENT"],
        "awards": ["AWARD", "RECOGNITION", "ACHIEVEMENT", "CERTIFICATION", "PARTNER", "ECOSYSTEM", "CLIENTELE"],
        "impact": ["IMPACT", "SUSTAINABILITY", "ESG", "SOCIAL", "ENVIRONMENTAL", "CARBON", "OUTCOME"]
    }
    
    def detect_section(self, text: str, page_num: int = 1) -> str:
        """Detect section from text content"""
        text_upper = text.upper()
        
        max_score = 0
        detected_section = "general"
        
        for section, keywords in self.SECTION_HEADERS.items():
            score = sum(1 for kw in keywords if kw in text_upper)
            if score > max_score:
                max_score = score
                detected_section = section
        
        if max_score < 2:
            return "general"
        
        return detected_section
    
    def is_heading(self, line: str) -> bool:
        """Check if line is a heading"""
        line = line.strip()
        
        if not line or len(line) > 100:
            return False
        
        if line.isupper() and len(line) > 3:
            return True
        
        if any(line.startswith(h) for h in ["TRACTION", "TEAM", "FUNDING", "MARKET", "COMPETITION", "USE OF FUNDS"]):
            return True
        
        return False
    
    def extract_page_layout(self, page_text: str) -> Dict:
        """Extract layout structure from page"""
        lines = page_text.split('\n')
        
        headings = [l for l in lines if self.is_heading(l)]
        
        return {
            "heading_count": len(headings),
            "headings": headings,
            "section": self.detect_section(page_text),
            "text_density": len(page_text) / max(len(lines), 1)
        }