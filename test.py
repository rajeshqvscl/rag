import sys
import traceback
import os
sys.path.append(os.getcwd())

from app.services.email_processor import process_email

pdf_path = "e:/rag_system/test_pdfs/STC Pitch CCPS Round Fresh Fund Raise.pdf"

# Find any pdf if that one doesn't exist
if not os.path.exists(pdf_path):
    print("PDF not found at", pdf_path)
    # search for pdfs
    import glob
    pdfs = glob.glob("e:/rag_system/**/*.pdf", recursive=True)
    if pdfs:
        pdf_path = pdfs[0]
        print("Using PDF:", pdf_path)
    else:
        print("No PDFs found")
        sys.exit(1)

with open(pdf_path, "rb") as f:
    content = f.read()

print("Starting pipeline...")
try:
    process_email(content, os.path.basename(pdf_path))
except Exception as e:
    print("CAUGHT EXCEPTION:")
    traceback.print_exc()
