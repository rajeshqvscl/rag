"""
Chart/Table Extraction with Vision Model
Handles revenue trajectory from charts and tables
"""
import fitz  # PyMuPDF
import base64
import os
import io
from typing import List, Dict, Any, Optional
from PIL import Image


class ChartExtractor:
    """Extract data from charts and tables using vision models"""
    
    def __init__(self):
        self.anthropic_available = False
        
        try:
            from anthropic import Anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self.anthropic_client = Anthropic(api_key=api_key)
                self.anthropic_available = True
                print("Vision model (Claude) available for chart extraction")
            else:
                print("ANTHROPIC_API_KEY not set")
        except ImportError:
            print("anthropic package not installed")
    
    def extract_revenue_from_charts(self, file_path: str) -> List[Dict]:
        """
        Extract revenue data from charts/tables in PDF
        
        Returns:
            List of {year, revenue, source} dicts
            Empty list if no chart data found
        """
        if not self.anthropic_available:
            print("Vision model not available - skipping chart extraction")
            return []
        
        try:
            doc = fitz.open(file_path)
            revenue_data = []
            
            # Process first few pages (usually where financial charts are)
            pages_to_check = min(5, len(doc))
            
            for page_num in range(pages_to_check):
                page = doc[page_num]
                
                # Convert page to image
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scale for better quality
                img_data = pix.tobytes("png")
                
                # Analyze with vision model
                page_data = self._analyze_page_with_vision(img_data, page_num)
                if page_data:
                    revenue_data.extend(page_data)
            
            doc.close()
            
            # Remove duplicates and sort by year
            seen = set()
            unique_data = []
            for item in revenue_data:
                key = (item.get("year"), item.get("revenue"))
                if key not in seen and key[0] and key[1]:
                    seen.add(key)
                    unique_data.append(item)
            
            if unique_data:
                print(f"✓ Extracted {len(unique_data)} revenue data points from charts")
            
            return sorted(unique_data, key=lambda x: str(x.get("year", "")))
            
        except Exception as e:
            print(f"⚠ Chart extraction error: {e}")
            return []
    
    def _analyze_page_with_vision(self, img_data: bytes, page_num: int) -> Optional[List[Dict]]:
        """Analyze a single page image with Claude Vision"""
        try:
            # Convert to base64
            img_base64 = base64.b64encode(img_data).decode("utf-8")
            
            prompt = """You are analyzing a pitch deck page. Look for:

1. REVENUE CHARTS/GRAPHS - Extract year and revenue values
2. FINANCIAL TABLES - Extract revenue data by year
3. PROJECTIONS - Note if data is historical or projected

Return ONLY JSON in this exact format:
{
  "has_financial_data": true/false,
  "revenue_points": [
    {"year": "2021", "revenue": 1000000, "type": "actual/projected"},
    {"year": "2022", "revenue": 1500000, "type": "actual"}
  ],
  "notes": "any observations"
}

If no financial data found, return:
{"has_financial_data": false, "revenue_points": []}

IMPORTANT:
- Revenue should be in actual numbers (e.g., 1000000 for $1M)
- Year should be 4 digits
- Type must be "actual" or "projected"
- Do not guess - only extract what's visible
- Return ONLY JSON, no other text"""

            message = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
            
            response = self.anthropic_client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
                max_tokens=1500,
                temperature=0.2,
                messages=[message]
            )
            
            result_text = response.content[0].text
            
            # Extract JSON
            import json
            import re
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
            
            data = json.loads(result_text)
            
            if data.get("has_financial_data") and data.get("revenue_points"):
                # Add source info
                for point in data["revenue_points"]:
                    point["source"] = f"chart_page_{page_num + 1}"
                return data["revenue_points"]
            
            return None
            
        except Exception as e:
            print(f"⚠ Vision analysis failed for page {page_num + 1}: {e}")
            return None
    
    def format_revenue_for_display(self, value: float) -> str:
        """Format revenue number for display"""
        if value >= 1e9:
            return f"${value/1e9:.1f}B"
        elif value >= 1e6:
            return f"${value/1e6:.1f}M"
        elif value >= 1e3:
            return f"${value/1e3:.0f}K"
        else:
            return f"${value:,.0f}"


# Singleton instance
chart_extractor = ChartExtractor()
