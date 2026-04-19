"""
Multi-modal analysis service for pitch deck processing
"""
import os
import json
import cv2
import numpy as np
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import fitz  # PyMuPDF
from datetime import datetime
import io
import base64

class MultiModalService:
    def __init__(self):
        self.supported_formats = ['.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        
    def extract_images_from_pdf(self, pdf_path: str) -> List[Dict]:
        """Extract images from PDF file"""
        try:
            doc = fitz.open(pdf_path)
            images = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Get image list
                image_list = page.get_images(full=True)
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    # Convert to PIL Image
                    image = Image.open(io.BytesIO(image_bytes))
                    
                    # Store image info
                    images.append({
                        "page": page_num + 1,
                        "image_index": img_index,
                        "image": image,
                        "width": base_image["width"],
                        "height": base_image["height"],
                        "format": base_image["ext"]
                    })
            
            doc.close()
            return images
            
        except Exception as e:
            print(f"Error extracting images from PDF: {e}")
            return []
    
    def analyze_image_content(self, image: Image.Image) -> Dict:
        """Analyze image content using computer vision"""
        try:
            # Convert PIL to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            analysis = {
                "text_content": "",
                "charts_detected": [],
                "tables_detected": [],
                "logos_detected": [],
                "color_analysis": {},
                "layout_analysis": {}
            }
            
            # Extract text using OCR
            try:
                text = pytesseract.image_to_string(image)
                analysis["text_content"] = text.strip()
            except:
                analysis["text_content"] = ""
            
            # Detect charts (simplified)
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter potential chart areas
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 10000:  # Large areas might be charts
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h
                    
                    # Check if it looks like a chart (common aspect ratios)
                    if 0.5 < aspect_ratio < 3.0:
                        analysis["charts_detected"].append({
                            "type": "potential_chart",
                            "position": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                            "area": int(area),
                            "aspect_ratio": round(aspect_ratio, 2)
                        })
            
            # Color analysis
            try:
                # Convert to numpy array for color analysis
                img_array = np.array(image)
                
                # Get dominant colors
                pixels = img_array.reshape(-1, 3)
                unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
                
                # Get top 5 most common colors
                top_colors_idx = np.argsort(counts)[-5:][::-1]
                dominant_colors = []
                
                for idx in top_colors_idx:
                    color = unique_colors[idx]
                    dominant_colors.append({
                        "rgb": color.tolist(),
                        "hex": '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2]),
                        "percentage": round(counts[idx] / len(pixels) * 100, 2)
                    })
                
                analysis["color_analysis"] = {
                    "dominant_colors": dominant_colors,
                    "total_colors": len(unique_colors)
                }
            except:
                analysis["color_analysis"] = {"dominant_colors": [], "total_colors": 0}
            
            # Layout analysis
            try:
                height, width = cv_image.shape[:2]
                
                # Analyze text blocks
                text_blocks = []
                try:
                    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                    
                    for i in range(len(data['text'])):
                        if int(data['conf'][i]) > 60:  # Confidence threshold
                            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                            text_blocks.append({
                                "text": data['text'][i].strip(),
                                "position": {"x": x, "y": y, "width": w, "height": h},
                                "confidence": data['conf'][i]
                            })
                except:
                    pass
                
                analysis["layout_analysis"] = {
                    "image_size": {"width": width, "height": height},
                    "text_blocks": text_blocks,
                    "text_density": len(text_blocks) / (width * height) * 10000 if width * height > 0 else 0
                }
            except:
                analysis["layout_analysis"] = {"image_size": {"width": 0, "height": 0}, "text_blocks": [], "text_density": 0}
            
            return analysis
            
        except Exception as e:
            print(f"Error analyzing image content: {e}")
            return {"error": str(e)}
    
    def extract_financial_data_from_image(self, image: Image.Image) -> Dict:
        """Extract financial data from images (charts, tables, etc.)"""
        try:
            analysis = self.analyze_image_content(image)
            
            financial_data = {
                "charts": [],
                "tables": [],
                "numbers": [],
                "financial_terms": [],
                "revenue_trajectory": []  # Extracted revenue data from graphs
            }
            
            # Extract financial terms from text content
            text = analysis.get("text_content", "").lower()
            financial_terms = [
                "revenue", "profit", "loss", "income", "expense", "cash flow",
                "ebitda", "gross margin", "net margin", "operating margin",
                "roi", "npv", "irr", "capex", "opex", "cagr", "eps",
                "pe ratio", "market cap", "debt", "equity", "assets", "liabilities"
            ]
            
            found_terms = []
            for term in financial_terms:
                if term in text:
                    found_terms.append(term)
            
            financial_data["financial_terms"] = found_terms
            
            # Extract numbers from text
            import re
            numbers = re.findall(r'\$?\d+(?:,\d{3})*(?:\.\d+)?(?:[KMB]?)?', text)
            financial_data["numbers"] = numbers[:20]  # Limit to first 20 numbers
            
            # Extract revenue trajectory from charts
            financial_data["revenue_trajectory"] = self.extract_revenue_trajectory_from_image(image, analysis)
            
            # Analyze detected charts
            for chart in analysis.get("charts_detected", []):
                chart_data = {
                    "type": "chart",
                    "position": chart["position"],
                    "area": chart["area"],
                    "aspect_ratio": chart["aspect_ratio"],
                    "potential_chart_type": self.classify_chart_type(chart)
                }
                financial_data["charts"].append(chart_data)
            
            return financial_data
            
        except Exception as e:
            print(f"Error extracting financial data from image: {e}")
            return {"error": str(e)}
    
    def extract_revenue_trajectory_from_image(self, image: Image.Image, analysis: Dict) -> List[Dict]:
        """Extract revenue trajectory data from chart images"""
        try:
            import re
            
            text = analysis.get("text_content", "")
            revenue_data = []
            
            # Pattern to match year-revenue pairs from OCR text
            # Looks for patterns like "2024 $10M", "2025: $15M", "2024 - 10,000,000", etc.
            year_revenue_patterns = [
                r'(\d{4})\s*[:\-\s]\s*\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)',
                r'(\d{4})\s*\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)',
                r'\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)\s*[:\-\s]\s*(\d{4})',
            ]
            
            for pattern in year_revenue_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    try:
                        # Determine which group is year and which is revenue
                        if len(match) == 3:
                            if match[0].isdigit() and len(match[0]) == 4:
                                year = match[0]
                                revenue_str = match[1]
                                unit = match[2].upper()
                            else:
                                year = match[2]
                                revenue_str = match[0]
                                unit = match[1].upper()
                            
                            # Parse revenue value
                            revenue_num = float(revenue_str.replace(',', ''))
                            
                            # Convert to actual number based on unit
                            if unit == 'B':
                                revenue_num *= 1000000000
                            elif unit == 'M':
                                revenue_num *= 1000000
                            elif unit == 'K':
                                revenue_num *= 1000
                            
                            # Only add if year is reasonable (2000-2100) and revenue is positive
                            if 2000 <= int(year) <= 2100 and revenue_num > 0:
                                revenue_data.append({
                                    "year": year,
                                    "revenue": int(revenue_num)
                                })
                    except (ValueError, IndexError) as e:
                        continue
            
            # If no year-revenue pairs found, try to extract just revenue numbers with context
            if not revenue_data:
                # Look for revenue-like numbers in the text
                revenue_numbers = re.findall(r'\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)\s*(?:million|billion|thousand)?', text, re.IGNORECASE)
                
                # If we found numbers but no years, we can't create a trajectory
                # Just return empty list - we need explicit year-revenue pairs from the graph
            
            # Sort by year and remove duplicates
            if revenue_data:
                revenue_data = sorted(revenue_data, key=lambda x: int(x['year']))
                # Remove duplicates (keep first occurrence)
                seen_years = set()
                unique_data = []
                for item in revenue_data:
                    if item['year'] not in seen_years:
                        seen_years.add(item['year'])
                        unique_data.append(item)
                revenue_data = unique_data
            
            print(f"Extracted revenue trajectory from image: {revenue_data}")
            return revenue_data
            
        except Exception as e:
            print(f"Error extracting revenue trajectory: {e}")
            return []
    
    def classify_chart_type(self, chart_info: Dict) -> str:
        """Classify chart type based on aspect ratio and other features"""
        aspect_ratio = chart_info.get("aspect_ratio", 1.0)
        area = chart_info.get("area", 0)
        
        # Simple heuristic classification
        if aspect_ratio > 2.0:
            return "horizontal_bar_chart"
        elif aspect_ratio < 0.5:
            return "vertical_bar_chart"
        elif 0.8 < aspect_ratio < 1.2:
            if area > 50000:
                return "pie_chart"
            else:
                return "square_chart"
        else:
            return "line_chart"
    
    def process_pitch_deck_multimodal(self, file_path: str, company: str) -> Dict:
        """Process pitch deck with multi-modal analysis"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.pdf':
                return self.process_pdf_multimodal(file_path, company)
            elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
                return self.process_image_multimodal(file_path, company)
            else:
                return {"error": f"Unsupported file format: {file_ext}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def process_pdf_multimodal(self, pdf_path: str, company: str) -> Dict:
        """Process PDF with multi-modal analysis"""
        try:
            # Extract images from PDF
            images = self.extract_images_from_pdf(pdf_path)
            
            multimodal_analysis = {
                "company": company,
                "file_path": pdf_path,
                "total_pages": len(fitz.open(pdf_path)),
                "images_extracted": len(images),
                "image_analysis": [],
                "financial_data": [],
                "summary": {
                    "charts_found": 0,
                    "tables_found": 0,
                    "financial_terms_found": [],
                    "text_extracted": ""
                }
            }
            
            all_financial_terms = set()
            all_text = []
            
            for i, img_info in enumerate(images):
                # Analyze image content
                image_analysis = self.analyze_image_content(img_info["image"])
                
                # Extract financial data
                financial_data = self.extract_financial_data_from_image(img_info["image"])
                
                multimodal_analysis["image_analysis"].append({
                    "page": img_info["page"],
                    "image_index": img_info["image_index"],
                    "size": {"width": img_info["width"], "height": img_info["height"]},
                    "analysis": image_analysis,
                    "financial_data": financial_data
                })
                
                # Collect summary data
                multimodal_analysis["summary"]["charts_found"] += len(financial_data.get("charts", []))
                multimodal_analysis["summary"]["tables_found"] += len(financial_data.get("tables", []))
                
                for term in financial_data.get("financial_terms", []):
                    all_financial_terms.add(term)
                
                if image_analysis.get("text_content"):
                    all_text.append(image_analysis["text_content"])
            
            multimodal_analysis["summary"]["financial_terms_found"] = list(all_financial_terms)
            multimodal_analysis["summary"]["text_extracted"] = "\n".join(all_text)
            
            return multimodal_analysis
            
        except Exception as e:
            return {"error": str(e)}
    
    def process_image_multimodal(self, image_path: str, company: str) -> Dict:
        """Process single image with multi-modal analysis"""
        try:
            # Open image
            image = Image.open(image_path)
            
            # Analyze image content
            image_analysis = self.analyze_image_content(image)
            
            # Extract financial data
            financial_data = self.extract_financial_data_from_image(image)
            
            multimodal_analysis = {
                "company": company,
                "file_path": image_path,
                "image_analysis": image_analysis,
                "financial_data": financial_data,
                "summary": {
                    "charts_found": len(financial_data.get("charts", [])),
                    "tables_found": len(financial_data.get("tables", [])),
                    "financial_terms_found": financial_data.get("financial_terms", []),
                    "text_extracted": image_analysis.get("text_content", "")
                }
            }
            
            return multimodal_analysis
            
        except Exception as e:
            return {"error": str(e)}
    
    def generate_insights_from_multimodal(self, multimodal_data: Dict) -> Dict:
        """Generate insights from multi-modal analysis"""
        try:
            insights = {
                "visual_elements": [],
                "financial_indicators": [],
                "content_quality": {},
                "recommendations": []
            }
            
            if "error" in multimodal_data:
                return insights
            
            # Analyze visual elements
            if "image_analysis" in multimodal_data:
                for img_data in multimodal_data["image_analysis"]:
                    analysis = img_data.get("analysis", {})
                    
                    # Color insights
                    color_analysis = analysis.get("color_analysis", {})
                    if color_analysis.get("dominant_colors"):
                        top_color = color_analysis["dominant_colors"][0]
                        insights["visual_elements"].append({
                            "type": "brand_color",
                            "color": top_color["hex"],
                            "percentage": top_color["percentage"],
                            "page": img_data.get("page", 1)
                        })
                    
                    # Layout insights
                    layout = analysis.get("layout_analysis", {})
                    text_density = layout.get("text_density", 0)
                    
                    if text_density > 5:
                        insights["content_quality"]["text_density"] = "High - may be cluttered"
                    elif text_density < 1:
                        insights["content_quality"]["text_density"] = "Low - may lack detail"
                    else:
                        insights["content_quality"]["text_density"] = "Balanced"
            
            # Financial insights
            if "summary" in multimodal_data:
                summary = multimodal_data["summary"]
                
                if summary.get("charts_found", 0) > 0:
                    insights["visual_elements"].append({
                        "type": "data_visualization",
                        "count": summary["charts_found"],
                        "message": f"Found {summary['charts_found']} potential charts"
                    })
                
                financial_terms = summary.get("financial_terms_found", [])
                if financial_terms:
                    insights["financial_indicators"] = [
                        {"term": term, "type": "financial_metric"} 
                        for term in financial_terms
                    ]
                
                # Generate recommendations
                if len(financial_terms) > 10:
                    insights["recommendations"].append("Strong financial data presentation")
                elif len(financial_terms) < 3:
                    insights["recommendations"].append("Consider adding more financial metrics")
                
                if summary.get("charts_found", 0) > 5:
                    insights["recommendations"].append("Good use of data visualization")
                elif summary.get("charts_found", 0) == 0:
                    insights["recommendations"].append("Consider adding charts to illustrate key points")
            
            return insights
            
        except Exception as e:
            return {"error": str(e)}

# Global multi-modal service instance
multimodal_service = MultiModalService()
