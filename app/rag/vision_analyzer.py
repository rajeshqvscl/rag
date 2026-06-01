import os
import fitz
import io
import base64
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from PIL import Image


@dataclass
class ChartAnalysis:
    page_num: int
    chart_type: str
    title: str
    extracted_metrics: List[Dict]
    raw_description: str
    confidence: float
    image_data: Optional[bytes] = None


class VisionAnalyzer:
    def __init__(self):
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.client = None
        
        if self.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_api_key)
                self.client = genai
                print("[VISION_ANALYZER] Gemini configured successfully")
            except ImportError:
                print("[VISION_ANALYZER] google-generativeai not installed")
    
    def extract_charts_from_pdf(self, file_content: bytes) -> List[Dict]:
        """Extract all chart/image regions from PDF"""
        charts = []
        
        doc = fitz.open(stream=file_content, filetype="pdf")
        
        for page_idx, page in enumerate(doc):
            images = page.get_images(full=True)
            
            for img_idx, img in enumerate(images):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    
                    if width > 100 and height > 100:
                        charts.append({
                            "page": page_idx + 1,
                            "image_index": img_idx,
                            "xref": xref,
                            "width": width,
                            "height": height,
                            "image_bytes": image_bytes,
                            "colorspace": base_image.get("colorspace", ""),
                            "is_chart": self._looks_like_chart(image_bytes)
                        })
                except Exception as e:
                    print(f"[VISION_ANALYZER] Error extracting image page {page_idx+1}: {e}")
        
        doc.close()
        return charts
    
    def _looks_like_chart(self, image_bytes: bytes) -> bool:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            width, height = img.size
            return width > 200 and height > 150
        except:
            return False
    
    def analyze_chart_with_vision(self, image_bytes: bytes, prompt: str = None) -> Optional[Dict]:
        """Use Gemini Vision to analyze a chart image"""
        if not self.client:
            print("[VISION_ANALYZER] No Gemini client configured, skipping vision analysis")
            return None
        
        if prompt is None:
            prompt = """Analyze this chart or image from a startup pitch deck.

Extract ONLY actual business metrics - ignore axis labels and legend entries.

Return a JSON with:
- chart_type: "bar", "line", "pie", "table", or "other"
- title: What the chart shows (or "unknown")
- metrics: Array of {label, value, unit} for key data points
- key_insight: One sentence about what this data means

If this is not a chart (e.g., logo, photo), return:
{"chart_type": "non-chart", "title": "not a chart"}"""
        
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            model = self.client.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content([
                prompt,
                img
            ])
            
            import json
            import re
            
            text = response.text
            json_match = re.search(r'\{[^{}]*"[^"]*"[^{}]*\}', text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = {
                    "chart_type": "analyzed",
                    "title": "chart",
                    "metrics": [],
                    "raw_text": text[:500]
                }
            
            result["raw_response"] = text[:1000]
            return result
            
        except Exception as e:
            print(f"[VISION_ANALYZER] Vision analysis error: {e}")
            return None
    
    def batch_analyze_charts(self, charts: List[Dict], max_charts: int = 10) -> List[Dict]:
        """Analyze multiple charts in parallel"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        chart_slice = [c for c in charts[:max_charts] if c.get("is_chart", False)]

        def analyze_one(chart):
            analysis = self.analyze_chart_with_vision(chart["image_bytes"])
            if analysis:
                return {
                    "page": chart["page"],
                    "image_index": chart["image_index"],
                    "analysis": analysis,
                    "width": chart["width"],
                    "height": chart["height"]
                }
            return None

        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(analyze_one, c): c for c in chart_slice}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        results.sort(key=lambda r: (r["page"], r["image_index"]))
        return results
    
    def extract_metrics_from_all_charts(self, file_content: bytes) -> Dict[str, Any]:
        """Extract and aggregate all chart metrics from a PDF"""
        charts = self.extract_charts_from_pdf(file_content)
        
        if not charts:
            return {"charts_found": 0, "metrics": []}
        
        chart_analyses = self.batch_analyze_charts(charts)
        
        all_metrics = []
        for ca in chart_analyses:
            if ca.get("analysis"):
                analysis = ca["analysis"]
                metrics = analysis.get("metrics", [])
                for m in metrics:
                    m["source_page"] = ca["page"]
                    m["chart_type"] = analysis.get("chart_type", "unknown")
                all_metrics.extend(metrics)
        
        return {
            "charts_found": len(charts),
            "charts_analyzed": len(chart_analyses),
            "metrics": all_metrics,
            "chart_analyses": chart_analyses
        }


def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def decode_base64_to_image(base64_str: str) -> bytes:
    return base64.b64decode(base64_str)


def extract_page_as_image(file_content: bytes, page_num: int, zoom: float = 2.0) -> Optional[bytes]:
    """Extract a single page as an image for vision analysis"""
    doc = fitz.open(stream=file_content, filetype="pdf")
    
    if page_num > len(doc):
        doc.close()
        return None
    
    page = doc.load_page(page_num - 1)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    img_bytes = pix.tobytes("png")
    doc.close()
    
    return img_bytes


def quick_chart_summary(charts: List[Dict]) -> str:
    if not charts:
        return "No charts found in document"
    
    chart_types = {}
    for chart in charts:
        c_type = chart.get("is_chart", False)
        chart_types["chart" if c_type else "image"] = chart_types.get("chart" if c_type else "image", 0) + 1
    
    summary = f"Found {len(charts)} visual elements:\n"
    for ctype, count in chart_types.items():
        summary += f"  - {count} {ctype}(s)\n"
    
    return summary