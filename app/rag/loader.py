import fitz  # PyMuPDF
import pdfplumber
from app.utils.text_utils import clean_text, safe_lower
from typing import List, Dict, Any, Tuple
import io
import re




# ============ SECTION-AWARE PARSING ============
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

def identify_section(text):
    """Enhanced section detection based on multiple keywords"""
    text_lower = safe_lower(text)
    
    # Check each section
    for section, keywords in SECTION_HEADERS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score >= 2:  # At least 2 keyword matches
            return section
    
    # Fallback to original logic
    if any(k in text_lower for k in ["revenue", "financial", "growth", "profit", "pipeline", "order", "contract"]):
        return "financials"
    if any(k in text_lower for k in ["tech", "product", "platform", "engineered", "software", "hardware", "ip", "patent"]):
        return "product"
    if any(k in text_lower for k in ["team", "founder", "experience", "background", "ceo", "cto"]):
        return "team"
    return "general"


def extract_tables_from_page(page):
    """Extract tables from a PDF page"""
    tables = []
    try:
        extracted_tables = page.extract_tables()
        if extracted_tables:
            for table in extracted_tables:
                if table and len(table) > 1:  # Valid table has >1 row
                    # Clean table data
                    table_text = ""
                    for row in table[:10]:  # Limit rows
                        if row:
                            row_str = " | ".join([str(cell) if cell else "" for cell in row])
                            table_text += row_str + "\n"
                    if table_text.strip():
                        tables.append(table_text)
    except Exception as e:
        pass  # Silently skip table extraction errors
    return tables


def load_pdf(file) -> Tuple[str, List[Dict]]:
    """
    Load PDF with section-aware parsing, layout analysis, table extraction, 
    and optional vision chart analysis.
    
    Returns:
        Tuple of (full_text: str, pages: List[Dict])
        where each page dict contains:
        - page: int
        - text: str
        - tables: List[str] (extracted tables)
        - sections: List[str] (detected sections)
        - headings: List[str] (heading candidates)
        - layout_blocks: List[Dict] (text block positions)
        - fonts: List[Dict] (font metadata)
        - images: int (image count on page)
    """
    print(f"[LOADER] load_pdf called with file type: {type(file)}")
    
    import hashlib
    import json
    import os
    
    if isinstance(file, bytes):
        file_content = file
    else:
        file.seek(0)
        file_content = file.read()
    
    if len(file_content) < 100:
        return ("", [])
        
    # --- CACHING LAYER ---
    file_hash = hashlib.md5(file_content).hexdigest()
    cache_dir = os.path.join(os.getcwd(), ".cache", "pdf_extractions")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{file_hash}.json")
    
    if os.path.exists(cache_path):
        try:
            print(f"[LOADER] Cache hit for PDF (hash: {file_hash}). Loading from cache...")
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            return cached_data["full_text"], cached_data["pages"]
        except Exception as e:
            print(f"[LOADER] Cache read failed: {e}")
    # ---------------------
    
    try:
        from .pdf_intelligence import load_pdf_intelligent
        print("[LOADER] Using new PDF intelligence pipeline")
        try:
            from app.rag.pipeline_orchestrator import is_fast_mode
            extract_images = not is_fast_mode()
        except Exception:
            extract_images = True
        full_text, pages = load_pdf_intelligent(file_content, extract_images=extract_images)
        print(f"[LOADER] New pipeline returned {len(pages)} pages, text length: {len(full_text)}")
        
        if full_text.strip():
            # Save to cache
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    # pages contains custom classes sometimes, try converting to dict
                    json.dump({"full_text": full_text, "pages": [p if isinstance(p, dict) else vars(p) for p in pages]}, f)
            except Exception as e:
                print(f"[LOADER] Failed to write cache: {e}")
                
            return full_text, pages
        print("[LOADER] New pipeline returned empty text, trying legacy...")
    except Exception as e:
        print(f"[LOADER] New pipeline failed, falling back to legacy: {e}")
    
    # Legacy / fallback implementation
    print("[LOADER] Using legacy PDF loader")
    pages = []
    full_text = ""
    
    # Try pdfplumber first
    try:
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                
                # Extract tables from this page
                tables = extract_tables_from_page(page)
                
                if text and text.strip():
                    cleaned = clean_text(text)
                    
                    # Detect sections on this page
                    sections = []
                    for section, keywords in SECTION_HEADERS.items():
                        if any(kw in safe_lower(cleaned) for kw in keywords):
                            sections.append(section)
                    
                    page_data = {
                        "page": i + 1,
                        "text": cleaned,
                        "tables": tables,
                        "sections": sections
                    }
                    
                    pages.append(page_data)
                    full_text += cleaned + "\n"
                    
                    # Add table content to full_text if present
                    for table in tables:
                        full_text += "\n[TABLE]\n" + table + "\n[/TABLE]\n"
    except Exception as pdfplumber_err:
        print(f"[LOADER] pdfplumber failed: {pdfplumber_err}")
        # Fallback to fitz (PyMuPDF) if pdfplumber fails
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            for page_num, page in enumerate(doc):
                text = page.get_text()
                if text and text.strip():
                    cleaned = clean_text(text)
                    full_text += cleaned + "\n"
                    pages.append({
                        "page": page_num + 1,
                        "text": cleaned,
                        "tables": [],
                        "sections": []
                    })
            doc.close()
            print(f"[LOADER] fitz fallback recovered {len(pages)} pages")
        except Exception as fitz_err:
            print(f"[LOADER] fitz fallback also failed: {fitz_err}")
    
    # OCR retry if legacy also returns empty (per-document, no global state)
    if not full_text or not full_text.strip():
        print("[LOADER] Legacy pipeline also empty - attempting standalone OCR...")
        try:
            from app.rag.pdf_intelligence import _run_paddleocr_fallback, _run_tesseract_fallback
            ocr_text = _run_paddleocr_fallback(file_content)
            if not ocr_text or len(ocr_text.strip()) <= 50:
                print("[LOADER] PaddleOCR gave little or nothing - trying Tesseract...")
                ocr_text = _run_tesseract_fallback(file_content)
            if ocr_text and len(ocr_text.strip()) > 50:
                full_text = ocr_text
                print(f"[LOADER] OCR recovered {len(full_text)} chars")
        except Exception as ocr_err:
            print(f"[LOADER] OCR recovery failed: {ocr_err}")
    
    result = (full_text, pages)
    print(f"[LOADER] About to return: type={type(result)}, len={len(result)}")
    return result


def chunk_text(pages: List[Dict], chunk_size: int = 600, overlap: int = 100) -> List[Dict]:
    """
    Section-aware chunking with semantic boundaries and rich metadata
    Uses semantic chunking for better context preservation

    Args:
        pages: List of {"page": num, "text": str, "tables": [], "sections": []} dicts
        chunk_size: Max chars per chunk (for fallback)
        overlap: Overlap between chunks (for fallback)

    Returns:
        List of {"content": str, "metadata": dict} with enhanced metadata
    """
    from app.rag.chunker import chunk_text as semantic_chunk_text
    return semantic_chunk_text(pages, chunk_size=chunk_size, overlap=overlap)