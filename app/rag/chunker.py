import re
from typing import List, Dict, Any, Optional


SEMANTIC_BOUNDARIES = [
    r"\n##\s+",
    r"\n#\s+",
    r"\n\d+\.\s+",
    r"\n[A-Z][A-Z\s]{5,}\n",
    r"\n---+",
    r"\n\*\*",
    r"\n[•\-\*]\s+",
]


def identify_section(text):
    """Enhanced section detection based on multiple keywords"""
    text_lower = text.lower() if text else ""

    section_keywords = {
        "traction": ["traction", "milestones", "customers", "clients", "adoption", "usage", "orders", "bookings", "revenue growth"],
        "financials": ["financial", "revenue", "profit", "ebitda", "margin", "unit economics", "pricing", "burn rate", "runway", "cash flow", "actuals"],
        "market": ["market", "tam", "sam", "som", "opportunity", "industry", "size", "growth rate", "addressable"],
        "competition": ["competition", "competitor", "differentiation", "advantage", "competitive", "unique", "moat", "barriers"],
        "team": ["team", "founder", "co-founder", "ceo", "cto", "advisor", "board", "experience", "background", "leadership"],
        "funding": ["funding", "raising", "investment", "capital", "valuation", "series", "round", "use of funds", "runway"],
        "product": ["product", "technology", "platform", "solution", "service", "feature", "ip", "patent", "development"],
        "awards": ["award", "recognition", "achievement", "certification", "partner", "ecosystem", "clientele"],
        "impact": ["impact", "sustainability", "esg", "social", "environmental", "carbon", "outcome"]
    }

    for section, keywords in section_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score >= 2:
            return section

    if any(k in text_lower for k in ["revenue", "financial", "growth", "profit", "pipeline", "order", "contract"]):
        return "financials"
    if any(k in text_lower for k in ["tech", "product", "platform", "engineered", "software", "hardware", "ip", "patent"]):
        return "product"
    if any(k in text_lower for k in ["team", "founder", "experience", "background", "ceo", "cto"]):
        return "team"
    return "general"


def find_semantic_boundaries(text: str) -> List[int]:
    """Find semantic boundaries in text (section breaks, headers, etc.)"""
    boundaries = [0]

    for pattern in SEMANTIC_BOUNDARIES:
        matches = [m.start() for m in re.finditer(pattern, text, re.IGNORECASE)]
        boundaries.extend(matches)

    boundaries.append(len(text))
    return sorted(set(boundaries))


def semantic_chunk(text: str, min_chunk_size: int = 200, max_chunk_size: int = 800) -> List[Dict[str, Any]]:
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

        if len(chunk_content) < 50:
            continue

        section = identify_section(chunk_content)

        if len(chunk_content) > max_chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', chunk_content)
            sub_chunk = ""
            for sentence in sentences:
                if len(sub_chunk) + len(sentence) > max_chunk_size and sub_chunk:
                    chunks.append({
                        "content": sub_chunk.strip(),
                        "metadata": {
                            "section": identify_section(sub_chunk),
                            "chunk_type": "semantic",
                            "boundary": "sentence"
                        }
                    })
                    sub_chunk = sentence
                else:
                    sub_chunk += " " + sentence if sub_chunk else sentence

            if sub_chunk.strip():
                chunks.append({
                    "content": sub_chunk.strip(),
                    "metadata": {
                        "section": identify_section(sub_chunk),
                        "chunk_type": "semantic",
                        "boundary": "sentence"
                    }
                })
        else:
            chunks.append({
                "content": chunk_content,
                "metadata": {
                    "section": section,
                    "chunk_type": "semantic",
                    "boundary": "section"
                }
            })

    return chunks


def chunk_text(pages, chunk_size=600, overlap=100):
    """
    Section-aware chunking with semantic boundaries and rich metadata

    Args:
        pages: List of {"page": num, "text": str, "tables": [], "sections": []} dicts
        chunk_size: Max chars per chunk (ignored for semantic chunking)
        overlap: Overlap between chunks (for fallback fixed chunking)

    Returns:
        List of {"content": str, "metadata": dict} with enhanced metadata
    """
    all_chunks = []
    all_tables_content = ""

    for page in pages:
        text = page.get("text", "") if page else ""
        page_num = page.get("page", 1) if page else 1
        tables = page.get("tables", []) if page else []

        if not text or not text.strip():
            continue

        # Phase 1A: Inject layout metadata per page
        headings = page.get("headings", [])
        sections = page.get("sections", [])
        layout_hints = ""
        if headings or sections:
            parts = []
            if headings:
                parts.append(f"headings: {' | '.join(headings[:4])}")
            if sections:
                parts.append(f"sections: {', '.join(sections)}")
            layout_hints = f"\n[LAYOUT: Page {page_num} — {'; '.join(parts)}]\n"

        # Aggregate table content across pages for structured injection
        for table in tables:
            if isinstance(table, str):
                table_str = table
            elif isinstance(table, list):
                rows = []
                for row in table[:15]:
                    if isinstance(row, list):
                        rows.append(" | ".join(str(c) if c else "" for c in row))
                    else:
                        rows.append(str(row))
                table_str = "\n".join(rows)
            else:
                table_str = str(table)
            all_tables_content += f"\n[TABLE]\n{table_str}\n[/TABLE]\n"

        semantic_chunks = semantic_chunk(text, min_chunk_size=200, max_chunk_size=800)

        for chunk in semantic_chunks:
            content = layout_hints + chunk["content"]

            all_chunks.append({
                "content": content,
                "metadata": {
                    "page": page_num,
                    "section": chunk["metadata"].get("section", "general"),
                    "chunk_type": chunk["metadata"].get("chunk_type", "semantic"),
                    "has_tables": len(tables) > 0,
                    "boundary": chunk["metadata"].get("boundary", "unknown")
                }
            })

    # Append aggregated table content to the last chunk for cross-reference
    if all_tables_content and all_chunks:
        last_chunk = all_chunks[-1]
        last_chunk["content"] += all_tables_content

    if len(all_chunks) < 2:
        return fallback_fixed_chunk(pages, chunk_size, overlap)

    return all_chunks


def fallback_fixed_chunk(pages, chunk_size=600, overlap=100):
    """Fallback to fixed-size chunking with metadata"""
    chunks = []
    for page in pages:
        text = page.get("text", "") if page else ""
        page_num = page.get("page", 1) if page else 1
        tables = page.get("tables", []) if page else []

        if not text or not text.strip():
            continue

        headings = page.get("headings", [])
        sections = page.get("sections", [])
        layout_hints = ""
        if headings or sections:
            parts = []
            if headings:
                parts.append(f"headings: {' | '.join(headings[:4])}")
            if sections:
                parts.append(f"sections: {', '.join(sections)}")
            layout_hints = f"\n[LAYOUT: Page {page_num} — {'; '.join(parts)}]\n"

        table_content = ""
        for table in tables:
            table_content += f"\n[TABLE]\n{table}\n[/TABLE]\n"

        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_content = text[start:end].strip()

            if len(chunk_content) > 50:
                section = identify_section(chunk_content)
                chunks.append({
                    "content": layout_hints + chunk_content + (table_content if start == 0 else ""),
                    "metadata": {
                        "page": page_num,
                        "section": section,
                        "chunk_type": "fixed",
                        "has_tables": len(tables) > 0
                    }
                })
            start += chunk_size - overlap

    return chunks