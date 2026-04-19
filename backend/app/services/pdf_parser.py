"""
Robust PDF Parser with PyMuPDF
Hard validation to stop fake outputs
"""
import fitz  # PyMuPDF
from typing import Tuple, Dict, Any


def extract_text_from_pdf(file_path: str) -> Tuple[str, int, Dict]:
    """
    Extract text from PDF using PyMuPDF with hard validation
    
    Args:
        file_path: Path to PDF file
        
    Returns:
        Tuple of (text, page_count, metadata)
        
    Raises:
        ValueError: If PDF parsing fails
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")
    
    # HARD CHECK: Document must have pages
    page_count = len(doc)
    if page_count == 0:
        raise ValueError("PDF has 0 pages or failed to load")
    
    # Extract text from all pages
    full_text = ""
    for page_num in range(page_count):
        page = doc[page_num]
        text = page.get_text()
        if text:
            full_text += text + "\n"
    
    doc.close()
    
    # HARD CHECK: Text must not be empty
    if not full_text.strip():
        raise ValueError("Text extraction failed - no text found in PDF. Document may be scanned images or corrupted.")
    
    # HARD CHECK: Minimum text length
    if len(full_text.strip()) < 100:
        raise ValueError(f"Extracted text too short ({len(full_text)} chars). Document may be empty or image-based.")
    
    metadata = {
        "total_pages": page_count,
        "extracted_chars": len(full_text),
        "parser": "pymupdf"
    }
    
    return full_text, page_count, metadata


def validate_pdf_content(text: str, min_chars: int = 200) -> bool:
    """
    Validate that extracted content is meaningful
    
    Args:
        text: Extracted text
        min_chars: Minimum required characters
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not text:
        return False
    
    if len(text.strip()) < min_chars:
        return False
    
    # Check for common pitch deck keywords
    pitch_keywords = [
        'revenue', 'market', 'funding', 'investment', 'startup',
        'business', 'product', 'team', 'financial', 'growth',
        'traction', 'customers', 'users', 'sales', 'opportunity'
    ]
    
    text_lower = text.lower()
    keyword_matches = sum(1 for kw in pitch_keywords if kw in text_lower)
    
    if keyword_matches < 2:  # At least 2 pitch-related keywords
        return False
    
    return True
