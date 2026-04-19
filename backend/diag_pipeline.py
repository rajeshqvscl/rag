import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.pipeline import run_pipeline
from app.config import validate_env

try:
    print("Validating environment...")
    validate_env()
    print("Environment valid")
    
    pdf_path = r"c:\Users\Admin\OneDrive\Documents\fin_rag\backend\data\pitch_decks\Bijliride_Pitch_Deck_V4_20260416_102253.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"PDF not found at {pdf_path}")
    else:
        print(f"Testing pipeline with: {pdf_path}")
        result = run_pipeline(pdf_path)
        print("Pipeline result:", result)

except Exception as e:
    import traceback
    print("PIPELINE TEST FAILED:")
    print(str(e))
    traceback.print_exc()
