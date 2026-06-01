import os
from typing import Optional
from pathlib import Path
import PyPDF2

# ✅ use YOUR actual function signature
from app.rag.vector_store import save_index


def extract_pdf_text(file_path: str) -> str:
    text = []

    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            content = page.extract_text() or ""
            text.append(content)

    return "\n".join(text)


def simple_chunk(text: str, chunk_size: int = 500):
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i + chunk_size])
    return chunks


def index_document(file_path: str, doc_id: str) -> Optional[str]:
    if not file_path or not Path(file_path).exists():
        return None

    text = extract_pdf_text(file_path)

    if not text.strip():
        return None

    # ✅ chunk text
    chunks = simple_chunk(text)

    # ✅ FIXED: match your function signature
    save_index(chunks, document_name=doc_id)

    return "indexed"


def get_all_tables() -> list:
    """
    Get all extracted tables from processed documents
    This would typically query a cached/stored table index
    """
    # Placeholder - in production would query from stored table data
    return []