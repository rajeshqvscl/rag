"""
Structured PDF Extraction Service using PyMuPDF (fitz)
Provides slide-based extraction with structure preservation and number normalization.
"""
import os
import re
import fitz  # PyMuPDF
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import tiktoken


@dataclass
class TextChunk:
    """Structured chunk with metadata for RAG"""
    text: str
    slide_number: int
    chunk_type: str  # 'financials', 'team', 'market', 'product', 'general'
    page_number: int
    normalized_text: str = ""  # Numbers expanded (K/M/B -> full numbers)


class PDFExtractor:
    """Extract structured content from PDFs using PyMuPDF"""
    
    # Token limits for chunking
    TARGET_TOKENS = 250  # Sweet spot for pitch deck chunks
    MAX_TOKENS = 300
    MIN_TOKENS = 150
    
    def __init__(self):
        self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))
    
    def _clean_numbers(self, text: str) -> str:
        """Normalize financial numbers: $25K -> $25000, $5M -> $5000000"""
        # Pattern: $NUMBER K/M/B with optional space
        def replace_unit(match):
            num_str = match.group(1).replace(',', '')
            unit = match.group(2).upper()
            try:
                num = float(num_str)
                if unit == 'K':
                    return f"${int(num * 1000):,}"
                elif unit == 'M':
                    return f"${int(num * 1000000):,}"
                elif unit == 'B':
                    return f"${int(num * 1000000000):,}"
                elif unit == 'CR' or unit == 'CRORE':
                    return f"₹{int(num * 10000000):,}"
                elif unit == 'L' or unit == 'LAKH':
                    return f"₹{int(num * 100000):,}"
            except ValueError:
                pass
            return match.group(0)
        
        # Handle $ patterns
        text = re.sub(r'\$([\d,.]+)\s*([KMB])\b', replace_unit, text, flags=re.IGNORECASE)
        # Handle rupee patterns
        text = re.sub(r'₹([\d,.]+)\s*(?:Cr|Crore)\b', replace_unit, text, flags=re.IGNORECASE)
        text = re.sub(r'₹([\d,.]+)\s*(?:L|Lakh)\b', replace_unit, text, flags=re.IGNORECASE)
        # Handle standalone K/M/B after numbers
        text = re.sub(r'([\d,.]+)\s*([KMB])\b', replace_unit, text, flags=re.IGNORECASE)
        
        return text
    
    def _detect_chunk_type(self, text: str) -> str:
        """Detect the type of content in a chunk"""
        text_lower = text.lower()
        
        # Financial indicators
        financial_keywords = ['revenue', 'arr', 'mrr', 'burn', 'runway', 'funding', 
                              'valuation', 'ebitda', 'margin', 'profit', 'loss',
                              'financial', 'unit economics', 'cagr', 'growth rate',
                              '$', 'million', 'billion', 'k', 'crore', 'lakh']
        
        # Team indicators
        team_keywords = ['founder', 'ceo', 'cto', 'cfo', 'team', 'founding', 'background',
                         'experience', 'worked at', 'former', 'led', 'managed', 'team size',
                         'employees', 'headcount', 'hiring']
        
        # Market indicators
        market_keywords = ['tam', 'sam', 'som', 'market size', 'industry', 'sector',
                           'competitor', 'competition', 'landscape', 'trends',
                           'addressable market', 'target market', 'customer']
        
        # Product indicators  
        product_keywords = ['product', 'solution', 'platform', 'feature', 'technology',
                           'patent', 'ip', 'prototype', 'mvp', 'demo', 'launch',
                           'use case', 'workflow', 'integration', 'api']
        
        scores = {
            'financials': sum(1 for kw in financial_keywords if kw in text_lower),
            'team': sum(1 for kw in team_keywords if kw in text_lower),
            'market': sum(1 for kw in market_keywords if kw in text_lower),
            'product': sum(1 for kw in product_keywords if kw in text_lower),
        }
        
        if max(scores.values()) == 0:
            return 'general'
        
        return max(scores, key=scores.get)
    
    def _split_into_chunks(self, text: str, slide_num: int, page_num: int) -> List[TextChunk]:
        """Split text into token-sized chunks with metadata"""
        chunks = []
        
        # Clean the text first
        normalized = self._clean_numbers(text)
        
        # If it's already small enough, keep as single chunk
        tokens = self._count_tokens(text)
        if tokens <= self.MAX_TOKENS:
            chunk_type = self._detect_chunk_type(text)
            return [TextChunk(
                text=text.strip(),
                slide_number=slide_num,
                chunk_type=chunk_type,
                page_number=page_num,
                normalized_text=normalized.strip()
            )]
        
        # Split by natural boundaries (paragraphs, bullets)
        # Try to split on: double newlines, bullets, or periods followed by newlines
        boundaries = r'(?:\n\n+|\n[•\-\*]|[.!?]\s+\n)'
        segments = re.split(boundaries, text)
        segments = [s.strip() for s in segments if s.strip()]
        
        current_chunk = ""
        current_normalized = ""
        
        for i, segment in enumerate(segments):
            segment_normalized = self._clean_numbers(segment)
            segment_tokens = self._count_tokens(segment)
            
            # If single segment is too big, split on sentence boundaries
            if segment_tokens > self.MAX_TOKENS:
                sentences = re.split(r'(?<=[.!?])\s+', segment)
                for sent in sentences:
                    sent_tokens = self._count_tokens(sent)
                    if self._count_tokens(current_chunk) + sent_tokens > self.MAX_TOKENS:
                        if current_chunk:
                            chunks.append(TextChunk(
                                text=current_chunk.strip(),
                                slide_number=slide_num,
                                chunk_type=self._detect_chunk_type(current_chunk),
                                page_number=page_num,
                                normalized_text=current_normalized.strip()
                            ))
                        current_chunk = sent
                        current_normalized = self._clean_numbers(sent)
                    else:
                        current_chunk += " " + sent
                        current_normalized += " " + self._clean_numbers(sent)
            else:
                # Check if adding this segment would exceed limit
                if self._count_tokens(current_chunk) + segment_tokens > self.MAX_TOKENS:
                    if current_chunk:
                        chunks.append(TextChunk(
                            text=current_chunk.strip(),
                            slide_number=slide_num,
                            chunk_type=self._detect_chunk_type(current_chunk),
                            page_number=page_num,
                            normalized_text=current_normalized.strip()
                        ))
                    current_chunk = segment
                    current_normalized = segment_normalized
                else:
                    current_chunk += "\n\n" + segment if current_chunk else segment
                    current_normalized += "\n\n" + segment_normalized if current_normalized else segment_normalized
        
        # Add remaining chunk
        if current_chunk and self._count_tokens(current_chunk) >= self.MIN_TOKENS:
            chunks.append(TextChunk(
                text=current_chunk.strip(),
                slide_number=slide_num,
                chunk_type=self._detect_chunk_type(current_chunk),
                page_number=page_num,
                normalized_text=current_normalized.strip()
            ))
        
        return chunks
    
    def extract_pdf(self, file_path: str) -> Tuple[str, List[TextChunk], Dict]:
        """
        Extract structured content from PDF
        
        Returns:
            - full_text: All text concatenated (for backward compatibility)
            - chunks: List of structured chunks with metadata
            - metadata: Dict with pages, structure info
        """
        result = {
            "text": "",
            "pages": 0,
            "chunks": [],
            "metadata": {
                "total_chunks": 0,
                "chunk_types": {},
                "has_structured_data": False
            }
        }
        
        all_chunks: List[TextChunk] = []
        all_text_parts = []
        
        try:
            doc = fitz.open(file_path)
            result["pages"] = len(doc)
            
            for page_num, page in enumerate(doc, 1):
                # Get text blocks to preserve structure
                blocks = page.get_text("blocks")
                
                # Sort blocks by vertical position (y0) to maintain reading order
                blocks.sort(key=lambda b: (b[1], b[0]))  # Sort by y0, then x0
                
                slide_text_parts = []
                
                for block in blocks:
                    # block format: (x0, y0, x1, y1, text, block_no, block_type)
                    x0, y0, x1, y1, text, block_no, block_type = block
                    
                    # Skip very short blocks (likely artifacts)
                    if len(text.strip()) < 3:
                        continue
                    
                    # Clean up text
                    text = text.strip().replace('\n\n\n', '\n\n')
                    slide_text_parts.append(text)
                
                # Combine slide text
                slide_text = "\n\n".join(slide_text_parts)
                if slide_text.strip():
                    all_text_parts.append(slide_text)
                    
                    # Create chunks for this slide
                    slide_chunks = self._split_into_chunks(slide_text, page_num, page_num)
                    all_chunks.extend(slide_chunks)
            
            doc.close()
            
            # Combine all text
            full_text = "\n\n---\n\n".join(all_text_parts)
            result["text"] = full_text
            
            # Build metadata
            type_counts = {}
            for chunk in all_chunks:
                type_counts[chunk.chunk_type] = type_counts.get(chunk.chunk_type, 0) + 1
            
            result["metadata"]["total_chunks"] = len(all_chunks)
            result["metadata"]["chunk_types"] = type_counts
            result["metadata"]["has_structured_data"] = len(all_chunks) > 0
            
            return full_text, all_chunks, result["metadata"]
            
        except Exception as e:
            print(f"Error extracting PDF with PyMuPDF: {e}")
            # Fallback to basic text extraction
            return self._fallback_extraction(file_path)
    
    def _fallback_extraction(self, file_path: str) -> Tuple[str, List[TextChunk], Dict]:
        """Fallback to PyPDF2 if PyMuPDF fails"""
        import PyPDF2
        
        full_text = ""
        chunks = []
        
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text() or ""
                    if text.strip():
                        full_text += text + "\n\n"
                        slide_chunks = self._split_into_chunks(text, page_num, page_num)
                        chunks.extend(slide_chunks)
        except Exception as e:
            print(f"Fallback extraction also failed: {e}")
        
        metadata = {
            "total_chunks": len(chunks),
            "chunk_types": {},
            "has_structured_data": False,
            "fallback_used": True
        }
        
        return full_text, chunks, metadata


# Singleton instance
pdf_extractor = PDFExtractor()
