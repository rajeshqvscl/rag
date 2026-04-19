"""
Chart and Image Extraction Layer for Pitch Decks
Extracts data from charts, graphs, and images using OCR and Vision Models
"""
import os
import re
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import tempfile


class ChartExtractor:
    """Extract data from charts and images in pitch decks"""
    
    def __init__(self):
        self.ocr_available = False
        self.vision_available = False
        self.pymupdf_available = False
        
        # Check for OCR capabilities
        try:
            import pytesseract
            self.ocr_available = True
            print("Tesseract OCR available")
        except ImportError:
            print("Tesseract OCR not installed")
        
        # Check for Vision API (Claude or GPT-4 Vision)
        try:
            from anthropic import Anthropic
            if os.getenv("ANTHROPIC_API_KEY"):
                self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                self.vision_available = True
                print("Claude Vision available for chart extraction")
        except ImportError:
            print("Claude Vision not available")
        
        # Check for PyMuPDF for image extraction
        try:
            import fitz  # PyMuPDF
            self.pymupdf_available = True
            print("PyMuPDF available for image extraction")
        except ImportError:
            print("PyMuPDF not installed")
    
    def extract_charts_from_pdf(self, pdf_path: str) -> List[Dict]:
        """
        Extract all charts and images from PDF and analyze them
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of chart data with extracted metrics
        """
        if not self.pymupdf_available:
            print("PyMuPDF not available, cannot extract images")
            return []
        
        charts = []
        
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                if not image_list:
                    continue
                
                print(f"Found {len(image_list)} images on page {page_num + 1}")
                
                for img_index, img in enumerate(image_list):
                    try:
                        # Extract image
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Save to temp file
                        with tempfile.NamedTemporaryFile(suffix=f".{image_ext}", delete=False) as tmp:
                            tmp.write(image_bytes)
                            tmp_path = tmp.name
                        
                        # Analyze image
                        chart_data = self._analyze_image(tmp_path, page_num + 1, img_index)
                        
                        if chart_data:
                            charts.append(chart_data)
                        
                        # Clean up temp file
                        os.unlink(tmp_path)
                        
                    except Exception as e:
                        print(f"Error processing image {img_index} on page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            print(f"Extracted {len(charts)} charts from PDF")
            
        except Exception as e:
            print(f"Error extracting charts from PDF: {e}")
            import traceback
            print(traceback.format_exc())
        
        return charts
    
    def _analyze_image(self, image_path: str, page_num: int, img_index: int) -> Optional[Dict]:
        """
        Analyze a single image/chart to extract data
        
        Args:
            image_path: Path to image file
            page_num: Page number in PDF
            img_index: Image index on page
            
        Returns:
            Dictionary with chart data or None if analysis fails
        """
        # Try vision model first (best for charts)
        if self.vision_available:
            try:
                return self._analyze_with_vision(image_path, page_num, img_index)
            except Exception as e:
                print(f"Vision analysis failed: {e}, trying OCR")
        
        # Fallback to OCR
        if self.ocr_available:
            try:
                return self._analyze_with_ocr(image_path, page_num, img_index)
            except Exception as e:
                print(f"OCR analysis failed: {e}")
        
        return None
    
    def _analyze_with_vision(self, image_path: str, page_num: int, img_index: int) -> Dict:
        """Analyze image using Claude Vision API"""
        try:
            import base64
            
            # Read image and encode to base64
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            prompt = """You are a financial data extraction specialist. Analyze this chart/image from a pitch deck.

Extract the following information:
1. Chart type (line chart, bar chart, pie chart, table, etc.)
2. Data points (year/value pairs if applicable)
3. Key metrics visible (revenue, growth, users, etc.)
4. Any numerical values with their labels
5. Title or caption if visible

Return ONLY valid JSON in this format:
{
  "chart_type": "string",
  "title": "string or null",
  "data_points": [{"year": "string", "value": number, "label": "string"}],
  "metrics": {"revenue": "string", "growth": "string", "users": "string"},
  "confidence": 0.0 to 1.0,
  "notes": "string"
}

If the image is not a chart (logo, photo, etc.), return {"chart_type": "non-chart", "confidence": 0.0}"""
            
            message = {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
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
                max_tokens=2000,
                temperature=0.3,
                messages=[message]
            )
            
            result_text = response.content[0].text
            
            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
            
            data = json.loads(result_text)
            
            # Add metadata
            data["page"] = page_num
            data["image_index"] = img_index
            data["extraction_method"] = "vision"
            data["timestamp"] = datetime.utcnow().isoformat()
            
            # Filter out non-charts
            if data.get("chart_type") == "non-chart":
                return None
            
            print(f"Vision analysis successful: {data.get('chart_type')} on page {page_num}")
            return data
            
        except Exception as e:
            print(f"Vision analysis error: {e}")
            raise
    
    def _analyze_with_ocr(self, image_path: str, page_num: int, img_index: int) -> Dict:
        """Analyze image using OCR (Tesseract)"""
        try:
            import pytesseract
            from PIL import Image
            
            # Open image and perform OCR
            image = Image.open(image_path)
            ocr_text = pytesseract.image_to_string(image)
            
            # Extract numbers and patterns
            numbers = re.findall(r'\$?[\d,]+\.?\d*\s*(?:[KMB]?)', ocr_text)
            
            # Extract potential years
            years = re.findall(r'\b(20\d{2})\b', ocr_text)
            
            # Extract revenue-related text
            revenue_matches = re.findall(r'(?:revenue|arr|sales|income)[:\s]*\$?([\d,]+\.?\d*\s*[KMB]?)', ocr_text, re.IGNORECASE)
            
            # Extract growth-related text
            growth_matches = re.findall(r'(?:growth|rate|yoY)[:\s]*([\d]+\.?\d*\s*%)', ocr_text, re.IGNORECASE)
            
            # Build result
            result = {
                "chart_type": "unknown",
                "page": page_num,
                "image_index": img_index,
                "extraction_method": "ocr",
                "ocr_text": ocr_text[:500],  # First 500 chars
                "numbers_found": numbers[:10],  # First 10 numbers
                "years_found": years[:5],
                "confidence": 0.4,  # OCR has lower confidence
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if revenue_matches:
                result["metrics"] = {"revenue": revenue_matches[0]}
            
            if growth_matches:
                if "metrics" not in result:
                    result["metrics"] = {}
                result["metrics"]["growth"] = growth_matches[0]
            
            print(f"OCR analysis complete: {len(numbers)} numbers found on page {page_num}")
            return result
            
        except Exception as e:
            print(f"OCR analysis error: {e}")
            raise
    
    def extract_revenue_from_charts(self, charts: List[Dict]) -> List[Dict]:
        """
        Extract revenue trajectory specifically from chart data
        
        Args:
            charts: List of chart data from extract_charts_from_pdf
            
        Returns:
            List of revenue data points
        """
        revenue_data = []
        
        for chart in charts:
            # Check if chart has data points
            if "data_points" in chart and chart["data_points"]:
                for point in chart["data_points"]:
                    # Look for revenue-related data
                    label = point.get("label", "").lower()
                    value = point.get("value")
                    year = point.get("year")
                    
                    if value and ("revenue" in label or "sales" in label or "income" in label or not label):
                        try:
                            revenue_data.append({
                                "year": year,
                                "revenue": float(value),
                                "source": f"chart_page_{chart['page']}",
                                "confidence": chart.get("confidence", 0.5)
                            })
                        except (ValueError, TypeError):
                            continue
            
            # Check if chart has metrics with revenue
            if "metrics" in chart and chart["metrics"].get("revenue"):
                revenue_str = chart["metrics"]["revenue"]
                revenue_value = self._parse_currency(revenue_str)
                if revenue_value:
                    revenue_data.append({
                        "year": "current",
                        "revenue": revenue_value,
                        "source": f"chart_page_{chart['page']}",
                        "confidence": chart.get("confidence", 0.5)
                    })
        
        # Remove duplicates and sort by year
        seen = set()
        unique_data = []
        for item in revenue_data:
            key = (item["year"], item["revenue"])
            if key not in seen:
                seen.add(key)
                unique_data.append(item)
        
        return sorted(unique_data, key=lambda x: str(x["year"]))
    
    def _parse_currency(self, value: str) -> Optional[float]:
        """Parse currency string to float"""
        if not value:
            return None
        value = str(value).upper().replace('$', '').replace(',', '').strip()
        multiplier = 1
        if value.endswith('B'):
            multiplier = 1e9
            value = value[:-1]
        elif value.endswith('M'):
            multiplier = 1e6
            value = value[:-1]
        elif value.endswith('K'):
            multiplier = 1e3
            value = value[:-1]
        try:
            return float(value) * multiplier
        except (ValueError, TypeError):
            return None


# Singleton instance
chart_extractor = ChartExtractor()
