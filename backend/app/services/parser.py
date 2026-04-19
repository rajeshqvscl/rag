import fitz  # PyMuPDF

def extract_text(file_path: str):
    doc = fitz.open(file_path)

    if len(doc) == 0:
        raise RuntimeError("PARSER_ERROR: 0 pages")

    text = ""
    for page in doc:
        text += page.get_text()

    if not text.strip():
        raise RuntimeError("PARSER_ERROR: empty text")

    return text
