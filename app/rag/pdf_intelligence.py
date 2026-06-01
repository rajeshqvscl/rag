import fitz
import pdfplumber
import io
import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from PIL import Image
import numpy as np
from app.rag.visual_parser import extract_visual_metrics


@dataclass
class PageData:
    page_num: int
    raw_text: str
    cleaned_text: str
    tables: List[Dict]
    images: List[Dict]
    fonts: List[Dict]
    layout_blocks: List[Dict]
    detected_sections: List[str]
    heading_candidates: List[str]


class PDFIntelligence:
    def __init__(self):
        self.section_keywords = {
            "traction": ["traction", "milestones", "customers", "adoption", "revenue growth", "orders", "bookings"],
            "financials": ["financial", "revenue", "profit", "ebitda", "margin", "unit economics", "pricing", "burn rate", "runway"],
            "market": ["market", "tam", "sam", "som", "opportunity", "industry", "size"],
            "competition": ["competition", "competitor", "differentiation", "advantage", "moat"],
            "team": ["team", "founder", "ceo", "cto", "advisor", "experience", "background"],
            "funding": ["funding", "raising", "investment", "capital", "valuation", "series", "round"],
            "product": ["product", "technology", "platform", "solution", "feature", "ip"],
            "awards": ["award", "recognition", "achievement", "certification"],
            "impact": ["impact", "sustainability", "esg", "social", "environmental"]
        }
        
        self.heading_patterns = [
            r"^(?:TRACTION|TEAM|FUNDING|MARKET|COMPETITION|USE OF FUNDS|TECHNOLOGY|PRODUCT|SOLUTION|BUSINESS MODEL| financials?|REVENUE|CUSTOMERS|PARTNERS|INVESTMENT|MILESTONES)",
            r"^[A-Z][A-Z\s]{5,30}$",
            r"^\d+\.\s*[A-Z]",
            r"^\d+\s*\.\s*[A-Z]"
        ]
    
    def extract_page_by_page(self, file_content: bytes) -> List[PageData]:
        pages = []
        
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_data = self._extract_pdfplumber_page(page, i + 1)
                    pages.append(page_data)
        except Exception as e:
            print(f"[PDF_INTEL] pdfplumber failed: {e}, falling back to PyMuPDF")
            pages = self._extract_pymupdf_pages(file_content)
        
        return pages
    
    def _extract_pdfplumber_page(self, page, page_num: int) -> PageData:
        text = page.extract_text() or ""
        
        # --- SMART PAGE SKIPPING ---
        text_lower = text.lower().strip()
        if len(text_lower) < 15 or ("thank you" in text_lower and len(text_lower) < 50):
            return PageData(
                page_num=page_num, raw_text=text, cleaned_text=text_lower,
                tables=[], images=[], fonts=[], layout_blocks=[],
                detected_sections=[], heading_candidates=[]
            )
        # ---------------------------
        
        tables = []
        try:
            extracted_tables = page.extract_tables()
            if extracted_tables:
                for table_idx, table in enumerate(extracted_tables):
                    if table and len(table) > 1:
                        tables.append({
                            "index": table_idx,
                            "data": table,
                            "rows": len(table),
                            "cols": len(table[0]) if table else 0
                        })
        except Exception as e:
            print(f"[PDF_INTEL] Table extraction error: {e}")
        
        fonts = self._extract_fonts_from_page(page)
        layout_blocks = self._extract_layout_blocks(page)
        headings = self._detect_headings(text, fonts)
        sections = self._detect_sections(text)
        
        return PageData(
            page_num=page_num,
            raw_text=text,
            cleaned_text=self._clean_text(text),
            tables=tables,
            images=[],
            fonts=fonts,
            layout_blocks=layout_blocks,
            detected_sections=sections,
            heading_candidates=headings
        )
    
    def _extract_pymupdf_pages(self, file_content: bytes) -> List[PageData]:
        pages = []
        doc = fitz.open(stream=file_content, filetype="pdf")
        
        for i, page in enumerate(doc):
            text = page.get_text("text")
            
            images = self._extract_images_from_page(page, i + 1)
            headings = self._detect_headings(text, [])
            sections = self._detect_sections(text)
            
            pages.append(PageData(
                page_num=i + 1,
                raw_text=text,
                cleaned_text=self._clean_text(text),
                tables=[],
                images=images,
                fonts=[],
                layout_blocks=[],
                detected_sections=sections,
                heading_candidates=headings
            ))
        
        doc.close()
        return pages
    
    def _extract_fonts_from_page(self, page) -> List[Dict]:
        fonts = []
        try:
            chars = page.chars
            current_font = None
            for char in chars:
                font = char.get("font", "unknown")
                size = char.get("size", 0)
                if font != current_font:
                    fonts.append({"font": font, "size": size})
                    current_font = font
        except Exception:
            pass
        return fonts[:20]
    
    def _extract_layout_blocks(self, page) -> List[Dict]:
        blocks = []
        try:
            words = page.extract_words()
            if words:
                y_positions = sorted(set(w["top"] for w in words))
                for y in y_positions[:15]:
                    block_words = [w for w in words if abs(w["top"] - y) < 5]
                    if block_words:
                        block_text = " ".join([w["text"] for w in block_words])
                        blocks.append({
                            "y": y,
                            "text": block_text,
                            "char_count": len(block_text)
                        })
        except Exception:
            pass
        return blocks
    
    def _detect_headings(self, text: str, fonts: List[Dict]) -> List[str]:
        headings = []
        lines = text.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            is_heading = False
            
            if re.match(r"^[A-Z][A-Z\s]{5,40}$", line):
                is_heading = True
            
            if re.search(r"^(?:TRACTION|TEAM|FUNDING|MARKET|COMPETITION)", line, re.IGNORECASE):
                is_heading = True
            
            if len(line) < 60 and line[0].isupper() and ":" not in line:
                words = line.split()
                if len(words) <= 5:
                    is_heading = True
            
            if is_heading:
                headings.append(line)
        
        return list(set(headings))[:10]
    
    def _detect_sections(self, text: str) -> List[str]:
        text_lower = text.lower()
        detected = []
        
        for section, keywords in self.section_keywords.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches >= 2 or (matches >= 1 and any(kw.upper() in text for kw in keywords)):
                detected.append(section)
        
        return detected
    
    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", text)
        return text.strip()
    
    def _extract_images_from_page(self, page, page_num: int) -> List[Dict]:
        images = []
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            images.append({
                "index": img_index,
                "xref": xref,
                "page": page_num
            })
        
        return images
    
    def extract_charts_with_pymupdf(self, file_content: bytes, output_dir: str = None) -> List[Dict]:
        charts = []
        doc = fitz.open(stream=file_content, filetype="pdf")
        
        for i, page in enumerate(doc):
            images = page.get_images(full=True)
            if images:
                for img_index, img in enumerate(images):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        
                        if output_dir:
                            from pathlib import Path
                            img_path = Path(output_dir) / f"page_{i+1}_img_{img_index}.png"
                            with open(img_path, "wb") as f:
                                f.write(image_bytes)
                        
                        charts.append({
                            "page": i + 1,
                            "image_index": img_index,
                            "width": base_image.get("width", 0),
                            "height": base_image.get("height", 0),
                            "colorspace": base_image.get("colorspace", ""),
                            "bpc": base_image.get("bpc", 0)
                        })
                    except Exception as e:
                        print(f"[PDF_INTEL] Image extraction error page {i+1}: {e}")
        
        doc.close()
        return charts
    
    def analyze_layout(self, file_content: bytes) -> Dict[str, Any]:
        doc = fitz.open(stream=file_content, filetype="pdf")
        
        layout_stats = {
            "total_pages": len(doc),
            "pages_with_tables": 0,
            "pages_with_images": 0,
            "pages_with_charts": 0,
            "average_text_length": 0,
            "sections_detected": {}
        }
        
        total_text_len = 0
        
        for page in doc:
            text = page.get_text()
            total_text_len += len(text)
            
            images = page.get_images()
            if images:
                layout_stats["pages_with_images"] += 1
            
            if len(text) > 200:
                layout_stats["pages_with_tables"] += 1
            
            if any(word in text.lower() for word in ["chart", "graph", "figure", "fig"]):
                layout_stats["pages_with_charts"] += 1
            
            for section, keywords in self.section_keywords.items():
                if any(kw in text.lower() for kw in keywords):
                    layout_stats["sections_detected"][section] = layout_stats["sections_detected"].get(section, 0) + 1
        
        layout_stats["average_text_length"] = total_text_len / len(doc) if doc else 0
        doc.close()
        
        return layout_stats


def _run_paddleocr_fallback(file_content: bytes) -> str:
    """OCR fallback for image-heavy or scanned PDFs."""
    try:
        from paddleocr import PaddleOCR
        import logging
        import hashlib
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from pathlib import Path
        logging.getLogger("ppocr").setLevel(logging.WARNING)

        file_hash = hashlib.md5(file_content).hexdigest()
        ocr_cache_dir = Path("cache/ocr")
        ocr_cache_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(stream=file_content, filetype="pdf")

        def ocr_page(page_num):
            cache_path = ocr_cache_dir / f"{file_hash}_{page_num}.txt"
            if cache_path.exists():
                cached = cache_path.read_text(encoding="utf-8")
                if cached.strip():
                    print(f"[OCR] Cache hit Page {page_num + 1}: {len(cached)} chars")
                    return cached

            page = doc[page_num]
            mat = fitz.Matrix(200 / 72, 200 / 72)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")

            ocr = PaddleOCR(use_angle_cls=True, lang="en")
            result = ocr.ocr(img_bytes)

            if result and result[0]:
                page_text = "\n".join(
                    line[1][0] for line in result[0]
                    if line and len(line) > 1 and line[1]
                )
                if page_text.strip():
                    result_text = f"[Page {page_num + 1}]\n{page_text}"
                    cache_path.write_text(result_text, encoding="utf-8")
                    print(f"[OCR] Page {page_num + 1}: {len(page_text)} chars")
                    return result_text
            return None

        all_text = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(ocr_page, i): i for i in range(len(doc))}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    all_text.append(result)

        doc.close()
        all_text.sort(key=lambda t: int(t.split("[Page ")[1].split("]")[0]))
        merged = "\n\n".join(all_text)
        print(f"[OCR] Complete - {len(merged)} total chars via PaddleOCR")
        return merged

    except ImportError:
        print("[OCR] PaddleOCR not installed. Run: pip install paddlepaddle paddleocr")
        return ""
    except Exception as e:
        print(f"[OCR] PaddleOCR failed: {e}")
        return ""


def _run_tesseract_fallback(file_content: bytes) -> str:
    """Backup OCR using Tesseract when PaddleOCR fails."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes

        print("[OCR] Trying Tesseract fallback...")
        images = convert_from_bytes(file_content)
        all_text = []

        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img)
            if text.strip():
                all_text.append(f"[Page {i+1}]\n{text}")
                print(f"[OCR] Tesseract Page {i+1}: {len(text)} chars")

        print(f"[OCR] Tesseract complete - {len(all_text)} pages with text")
        return "\n\n".join(all_text)
    except ImportError:
        print("[OCR] Tesseract not installed. Run: pip install pytesseract")
        return ""
    except Exception as e:
        print(f"[OCR] Tesseract failed: {e}")
        return ""


def load_pdf_intelligent(file_content: bytes, extract_images: bool = True) -> Tuple[str, List[Dict]]:
    """
    Enhanced PDF loading with page-by-page extraction, layout analysis, 
    table extraction, and optional vision chart analysis.
    Returns: (full_text, pages_data)
    """
    import fitz
    pdf_intel = PDFIntelligence()
    
    # Check if PDF has text content (might be scanned)
    doc = fitz.open(stream=file_content, filetype="pdf")
    has_text = any(page.get_text().strip() for page in doc)
    doc.close()
    
    if not has_text:
        print("[PDF_INTEL] WARNING: PDF appears to be scanned/image-based with no extractable text")
    
    pages = pdf_intel.extract_page_by_page(file_content)

    image_analysis = {}
    visual_graph = {}
    if extract_images:
        try:
            from app.rag.visual_intelligence import analyze_pdf_charts
            chart_analyses, visual_graph, _ = analyze_pdf_charts(file_content, pages)
            image_analysis = {
                "charts_found": len(chart_analyses),
                "charts_analyzed": len(chart_analyses),
                "metrics": [],
                "chart_analyses": [
                    {"page": ca.page, "chart_type": ca.chart_type,
                     "title": ca.title, "metrics": ca.metrics,
                     "confidence": ca.confidence, "source": ca.source}
                    for ca in chart_analyses
                ],
            }
            for ca in chart_analyses:
                for m in ca.metrics:
                    m["source_page"] = ca.page
                    m["chart_type"] = ca.chart_type
                    image_analysis["metrics"].append(m)
            vg_count = sum(len(v) for v in visual_graph.values()) if visual_graph else 0
            print(f"[PDF_INTEL] Visual intelligence: {len(chart_analyses)} charts analyzed, "
                  f"{vg_count} metric evidences across {len(visual_graph)} fields")
        except Exception as e:
            print(f"[PDF_INTEL] Visual intelligence skipped: {e}")
            import traceback
            traceback.print_exc()

    # Phase 1B: Advanced table extraction via TableExtractor
    advanced_tables = []
    try:
        from app.rag.table_extractor import extract_all_tables
        advanced_tables = extract_all_tables(file_content=file_content)
        if advanced_tables:
            print(f"[PDF_INTEL] TableExtractor found {len(advanced_tables)} tables")
    except Exception as e:
        print(f"[PDF_INTEL] TableExtractor skipped: {e}")

    full_text = ""
    pages_output = []

    for page in pages:
        full_text += page.cleaned_text + "\n\n"

        for table in page.tables:
            table_text = ""
            for row in table.get("data", []):
                row_str = " | ".join([str(cell) if cell else "" for cell in row])
                table_text += row_str + "\n"
            full_text += f"\n[TABLE]\n{table_text}[/TABLE]\n"

        # Phase 1A: Inject layout metadata per page
        headings = page.heading_candidates
        sections = page.detected_sections
        blocks = page.layout_blocks
        fonts = page.fonts
        font_summary = ""
        if fonts:
            unique_fonts = set(f.get("font", "") for f in fonts)
            font_sizes = [f.get("size", 0) for f in fonts if f.get("size", 0) > 0]
            size_range = f"{min(font_sizes):.0f}-{max(font_sizes):.0f}pt" if font_sizes else ""
            font_summary = f" | fonts: {len(unique_fonts)} variants ({size_range})"
        
        layout_info_parts = []
        if headings:
            layout_info_parts.append(f"headings: {' | '.join(headings[:4])}")
        if sections:
            layout_info_parts.append(f"sections: {', '.join(sections)}")
        if font_summary:
            layout_info_parts.append(font_summary)
        if len(blocks) > 5:
            layout_info_parts.append(f"layout_blocks: {len(blocks)} blocks detected")
        
        if layout_info_parts:
            full_text += f"\n[LAYOUT: Page {page.page_num} — {'; '.join(layout_info_parts)}]\n"

        page_dict = {
            "page": page.page_num,
            "text": page.cleaned_text,
            "tables": [t["data"] for t in page.tables],
            "sections": page.detected_sections,
            "headings": page.heading_candidates,
            "layout_blocks": page.layout_blocks,
            "fonts": page.fonts,
            "images": page.images
        }

        # Phase 3: Visual financial metric extraction (layout-aware TAM/SAM/SOM, etc.)
        visual_metrics = extract_visual_metrics(page_dict)
        if visual_metrics:
            page_dict["_visual_metrics"] = [
                {
                    "label": m.label,
                    "value": m.value,
                    "field": m.semantic_field,
                    "confidence": m.confidence,
                    "source": m.source,
                }
                for m in visual_metrics
            ]
            metrics_text = "; ".join(
                f"{m.semantic_field.upper()}={m.value}"
                for m in visual_metrics
            )
            full_text += f"\n[VISUAL_FINANCIALS: Page {page.page_num} — {metrics_text}]\n"

        pages_output.append(page_dict)

    # Inject advanced table classifications
    if advanced_tables:
        full_text += "\n[STRUCTURED_TABLES]\n"
        for tbl in advanced_tables[:10]:
            headers = tbl.get("headers", [])
            row_count = tbl.get("row_count", 0)
            classification = tbl.get("classification", "unknown")
            page_num = tbl.get("page", 0)
            full_text += f"Table (p{page_num}, {row_count} rows, {classification}): "
            full_text += f"headers={' | '.join(str(h) for h in headers[:5])}\n"
            for row in tbl.get("rows", [])[:5]:
                full_text += "  " + " | ".join(str(c) for c in row[:6]) + "\n"
        full_text += "[/STRUCTURED_TABLES]\n"

    OCR_THRESHOLD = 1000
    if len(full_text.strip()) < OCR_THRESHOLD:
        print(f"[PDF_INTEL] Only {len(full_text.strip())} chars extracted - triggering OCR fallback")
        ocr_text = _run_paddleocr_fallback(file_content)
        if not ocr_text or not ocr_text.strip():
            print("[PDF_INTEL] PaddleOCR returned empty - trying Tesseract fallback")
            ocr_text = _run_tesseract_fallback(file_content)
        if ocr_text and len(ocr_text.strip()) > 50:
            full_text = ocr_text + "\n\n" + full_text
            print(f"[PDF_INTEL] Post-OCR total: {len(full_text)} chars")
        else:
            print("[PDF_INTEL] OCR fallbacks failed to extract meaningful text")

    if image_analysis and image_analysis.get("metrics"):
        metrics_text = "\n[VISUAL_METRICS]\n"
        for metric in image_analysis["metrics"]:
            metrics_text += f"- {metric.get('label', 'Metric')}: {metric.get('value', '')} {metric.get('unit', '')}\n"
        full_text += metrics_text
        pages_output.append({"_image_metrics": image_analysis.get("metrics", [])})

    # Store structured visual metric graph — both in pages_output and full_text
    if visual_graph:
        pages_output.append({"_visual_metric_graph": visual_graph})
        import json as _json
        graph_json = _json.dumps(visual_graph, default=str)
        full_text += f"\n[VISUAL_GRAPH]\n{graph_json}\n[/VISUAL_GRAPH]\n"
        print(f"[PDF_INTEL] Stored visual metric graph with {len(visual_graph)} fields")

    # Aggregate all layout-based visual metrics across pages
    all_visual = []
    for p in pages_output:
        for vm in p.get("_visual_metrics", []):
            all_visual.append(vm)
    if all_visual:
        pages_output.append({"_visual_metrics_summary": all_visual})
        print(f"[PDF_INTEL] Visual financial parser extracted {len(all_visual)} layout-aware metrics across {len(pages_output)} pages")

    return (full_text, pages_output)


def quick_pdf_analysis(file_path: str) -> Dict:
    """Quick analysis of PDF structure"""
    with open(file_path, "rb") as f:
        content = f.read()
    
    pdf_intel = PDFIntelligence()
    return pdf_intel.analyze_layout(content)