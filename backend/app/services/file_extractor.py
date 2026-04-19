import os
from pypdf import PdfReader
from docx import Document
import pandas as pd


def extract_text(file_path: str):
    try:
        ext = os.path.splitext(file_path)[1].lower()
        print(f"Extracting text from {ext} file: {file_path}")

        if ext == ".pdf":
            reader = PdfReader(file_path)
            text = "\n".join([page.extract_text() or "" for page in reader.pages])
            print(f" PDF extraction complete, length: {len(text)} characters")
            return text

        elif ext == ".docx":
            doc = Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
            print(f" DOCX extraction complete, length: {len(text)} characters")
            return text

        elif ext in [".xlsx", ".xls", ".csv"]:
            if ext == ".csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            text = df.to_string()
            print(f" {ext.upper()} extraction complete, length: {len(text)} characters")
            return text

        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            print(f" TXT extraction complete, length: {len(text)} characters")
            return text

        else:
            print(f" Unsupported file format: {ext}")
            return ""
    except Exception as e:
        print(f" File extraction error: {str(e)}")
        return f"Extraction error: {str(e)}"