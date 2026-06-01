"""
Dynamic Smart Chunking - Context-aware chunking using semantic boundaries
"""

import re
from typing import List, Dict, Any, Optional
from app.rag.chunker import chunk_text as fixed_chunk_text


SEMANTIC_BOUNDARIES = [
    r"\n##\s+",  # Markdown H2
    r"\n#\s+",   # Markdown H1
    r"\n\d+\.\s+",  # Numbered lists
    r"\n[A-Z][A-Z\s]{5,}\n",  # ALL CAPS headings
    r"\n---+",  # Horizontal rules
    r"\n\*\*",  # Bold headers
]


def find_semantic_boundaries(text: str) -> List[int]:
    """Find semantic boundaries in text (section breaks, headers, etc.)"""
    boundaries = [0]  # Always start at 0
    
    for pattern in SEMANTIC_BOUNDARIES:
        matches = [m.start() for m in re.finditer(pattern, text, re.IGNORECASE)]
        boundaries.extend(matches)
    
    boundaries.append(len(text))  # Always end at end
    return sorted(set(boundaries))


def semantic_chunk(text: str, min_chunk_size: int = 300, max_chunk_size: int = 1000) -> List[Dict[str, Any]]:
    """
    Chunk text using semantic boundaries (section headers, natural breaks)
    instead of fixed sizes
    """
    boundaries = find_semantic_boundaries(text)
    chunks = []
    
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        chunk_content = text[start:end].strip()
        
        if len(chunk_content) < 50:  # Skip tiny chunks
            continue
        
        # If chunk is too large, split it
        if len(chunk_content) > max_chunk_size:
            # Split by sentences
            sentences = re.split(r'(?<=[.!?])\s+', chunk_content)
            sub_chunk = ""
            for sentence in sentences:
                if len(sub_chunk) + len(sentence) > max_chunk_size and sub_chunk:
                    chunks.append({
                        "content": sub_chunk.strip(),
                        "metadata": {
                            "chunk_type": "semantic",
                            "boundary": "sentence",
                            "size": len(sub_chunk)
                        }
                    })
                    sub_chunk = sentence
                else:
                    sub_chunk += " " + sentence if sub_chunk else sentence
            
            if sub_chunk.strip():
                chunks.append({
                    "content": sub_chunk.strip(),
                    "metadata": {
                        "chunk_type": "semantic",
                        "boundary": "sentence",
                        "size": len(sub_chunk)
                    }
                })
        else:
            chunks.append({
                "content": chunk_content,
                "metadata": {
                    "chunk_type": "semantic",
                    "boundary": "section",
                    "size": len(chunk_content)
                }
            })
    
    return chunks


def hybrid_chunk(text: str, chunk_size: int = 600, overlap: int = 100) -> List[Dict[str, Any]]:
    """
    Hybrid approach: Use semantic boundaries but also ensure reasonable chunk sizes
    """
    # First try semantic chunking
    semantic_chunks = semantic_chunk(text, min_chunk_size=200, max_chunk_size=800)
    
    # If semantic chunks are too small or too few, fall back to fixed
    if len(semantic_chunks) < 2 or all(len(c["content"]) < 200 for c in semantic_chunks):
        fixed_chunks = fixed_chunk_text(
            [{"text": text, "page": 1}], 
            chunk_size=chunk_size, 
            overlap=overlap
        )
        return [
            {
                "content": c["content"],
                "metadata": {
                    **c["metadata"],
                    "chunk_type": "fixed"
                }
            }
            for c in fixed_chunks
        ]
    
    return semantic_chunks


def smart_chunk(text: str, strategy: str = "auto", chunk_size: int = 600, overlap: int = 100) -> List[Dict[str, Any]]:
    """
    Main entry point for smart chunking
    
    Args:
        text: Text to chunk
        strategy: "semantic", "fixed", or "auto" (default)
        chunk_size: For fixed strategy
        overlap: For fixed strategy
    """
    if strategy == "fixed":
        fixed_chunks = fixed_chunk_text(
            [{"text": text, "page": 1}], 
            chunk_size=chunk_size, 
            overlap=overlap
        )
        return [
            {
                "content": c["content"],
                "metadata": {
                    **c["metadata"],
                    "chunk_type": "fixed"
                }
            }
            for c in fixed_chunks
        ]
    elif strategy == "semantic":
        return semantic_chunk(text, min_chunk_size=200, max_chunk_size=1000)
    else:  # auto
        return hybrid_chunk(text, chunk_size, overlap)


def chunk_with_metadata(pages: List[Dict], strategy: str = "auto", chunk_size: int = 600) -> List[Dict[str, Any]]:
    """Chunk multiple pages with metadata tracking"""
    all_chunks = []
    
    for page in pages:
        text = page.get("text", "")
        page_num = page.get("page", 1)
        
        if not text.strip():
            continue
        
        chunks = smart_chunk(text, strategy=strategy, chunk_size=chunk_size)
        
        for chunk in chunks:
            chunk["metadata"]["page"] = page_num
            chunk["metadata"]["strategy"] = strategy
            all_chunks.append(chunk)
    
    return all_chunks