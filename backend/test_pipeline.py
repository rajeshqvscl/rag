"""
Test script for the updated pipeline
Tests: PyMuPDF extraction, chunking, number normalization, Voyage embeddings
"""
import os
import sys
import io

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_pdf_extraction():
    """Test the new structured PDF extractor"""
    print("\n" + "="*60)
    print("TEST 1: Structured PDF Extraction (PyMuPDF)")
    print("="*60)
    
    # Check for pymupdf
    try:
        import fitz
        print("[OK] PyMuPDF (fitz) is available")
    except ImportError:
        print("[MISSING] PyMuPDF not installed. Run: pip install pymupdf")
        return False, []
    
    try:
        from services.pdf_extractor import pdf_extractor
        print("[OK] pdf_extractor imported successfully")
        
        # Find a test PDF
        test_pdf = "data/pitch_decks/Bijliride_Pitch_Deck_V4_20260416_102253.pdf"
        if not os.path.exists(test_pdf):
            # Find any PDF
            pitch_decks_dir = "data/pitch_decks"
            pdfs = [f for f in os.listdir(pitch_decks_dir) if f.endswith('.pdf')]
            if pdfs:
                test_pdf = os.path.join(pitch_decks_dir, pdfs[0])
        
        if os.path.exists(test_pdf):
            print(f"\nTesting extraction on: {test_pdf}")
            full_text, chunks, metadata = pdf_extractor.extract_pdf(test_pdf)
            
            print(f"[OK] Extraction complete")
            print(f"  - Total text length: {len(full_text)} chars")
            print(f"  - Number of chunks: {len(chunks)}")
            print(f"  - Chunk types: {metadata.get('chunk_types', {})}")
            print(f"  - Has structured data: {metadata.get('has_structured_data', False)}")
            
            # Show sample chunks
            if chunks:
                print(f"\n  Sample chunks:")
                for i, chunk in enumerate(chunks[:3]):
                    print(f"    Chunk {i+1} (Slide {chunk.slide_number}, Type: {chunk.chunk_type}):")
                    preview = chunk.text[:100].replace('\n', ' ')
                    print(f"      Text: {preview}...")
                    if chunk.normalized_text != chunk.text:
                        norm_preview = chunk.normalized_text[:100].replace('\n', ' ')
                        print(f"      Normalized: {norm_preview}...")
            
            return True, chunks
        else:
            print(f"[WARN] No test PDF found")
            return False, []
            
    except Exception as e:
        print(f"[FAIL] PDF extraction test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False, []


def test_number_normalization():
    """Test the number normalization function"""
    print("\n" + "="*60)
    print("TEST 2: Number Normalization")
    print("="*60)
    
    try:
        from services.pdf_extractor import pdf_extractor
        
        test_cases = [
            ("$25K", "$25,000"),
            ("$5M", "$5,000,000"),
            ("$1.5B", "$1,500,000,000"),
            ("Revenue: $100K per month", "Revenue: $100,000 per month"),
            ("$10M ARR growing to $50M", "$10,000,000 ARR growing to $50,000,000"),
            ("₹5 Crore", "₹50,000,000"),
            ("₹10 Lakh", "₹1,000,000"),
        ]
        
        all_passed = True
        for input_text, expected in test_cases:
            result = pdf_extractor._clean_numbers(input_text)
            status = "[OK]" if result == expected else "[FAIL]"
            if result != expected:
                all_passed = False
            print(f"{status} '{input_text}' -> '{result}'")
            if result != expected:
                print(f"   Expected: '{expected}'")
        
        return all_passed
        
    except Exception as e:
        print(f"[FAIL] Number normalization test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_chunking():
    """Test the chunking logic"""
    print("\n" + "="*60)
    print("TEST 3: Chunking (150-300 tokens)")
    print("="*60)
    
    try:
        from services.pdf_extractor import pdf_extractor
        import tiktoken
        
        encoding = tiktoken.get_encoding("cl100k_base")
        
        # Create test text that simulates a pitch deck slide
        test_text = """Financial Highlights

Revenue: $5M ARR (growing 100% YoY)
Customers: 500+ enterprise clients
Burn Rate: $200K/month
Runway: 18 months

The company is on track to hit $10M by end of year."""
        
        chunks = pdf_extractor._split_into_chunks(test_text, slide_num=1, page_num=1)
        
        print(f"[OK] Input text token count: {len(encoding.encode(test_text))}")
        print(f"[OK] Created {len(chunks)} chunk(s)")
        
        for i, chunk in enumerate(chunks):
            token_count = len(encoding.encode(chunk.text))
            print(f"\n  Chunk {i+1}:")
            print(f"    - Tokens: {token_count}")
            print(f"    - Type: {chunk.chunk_type}")
            print(f"    - Slide: {chunk.slide_number}")
            print(f"    - Preview: {chunk.text[:80]}...")
            
            # Verify token count is within limits
            if token_count > 300:
                print(f"    [WARN] WARNING: Exceeds 300 token limit!")
            elif token_count < 150 and len(chunks) > 1:
                print(f"    [WARN] WARNING: Below 150 tokens (may be too small)")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Chunking test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_voyage_embeddings():
    """Test Voyage AI embeddings"""
    print("\n" + "="*60)
    print("TEST 4: Voyage AI Embeddings")
    print("="*60)
    
    # Check for API key
    api_key = os.getenv("VOYAGE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[WARN] No VOYAGE_API_KEY or ANTHROPIC_API_KEY found in environment")
        print("  Skipping Voyage embedding test")
        return None
    
    try:
        from services.embeddings import get_embedding, get_embeddings
        
        # Test single embedding
        test_text = "Revenue of $5 million with 100% YoY growth in the SaaS sector"
        print(f"\nTesting single embedding...")
        print(f"  Input: '{test_text[:50]}...'")
        
        emb = get_embedding(test_text)
        print(f"[OK] Single embedding shape: {emb.shape}")
        print(f"  Dimensions: {len(emb)}")
        
        # Test batch embeddings
        test_texts = [
            "Financial performance: $10M ARR",
            "Team: 3 founders with 20+ years experience",
            "Market: $50B TAM in fintech"
        ]
        print(f"\nTesting batch embeddings ({len(test_texts)} texts)...")
        
        embs = get_embeddings(test_texts)
        print(f"[OK] Batch embeddings shape: {embs.shape}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Voyage embedding test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_pitch_deck_service():
    """Test the pitch deck service integration"""
    print("\n" + "="*60)
    print("TEST 5: Pitch Deck Service Integration")
    print("="*60)
    
    try:
        from services.pitch_deck_service import PitchDeckService
        
        service = PitchDeckService()
        print("[OK] PitchDeckService initialized")
        
        # Find a test PDF
        test_pdf = "data/pitch_decks/Bijliride_Pitch_Deck_V4_20260416_102253.pdf"
        if not os.path.exists(test_pdf):
            pitch_decks_dir = "data/pitch_decks"
            pdfs = [f for f in os.listdir(pitch_decks_dir) if f.endswith('.pdf')]
            if pdfs:
                test_pdf = os.path.join(pitch_decks_dir, pdfs[0])
        
        if os.path.exists(test_pdf):
            print(f"\nTesting extraction on: {os.path.basename(test_pdf)}")
            result = service.extract_pdf_text(test_pdf)
            
            print(f"[OK] Extraction complete")
            print(f"  - Pages: {result.get('pages', 0)}")
            print(f"  - Chunks: {len(result.get('chunks', []))}")
            print(f"  - Metrics: {result.get('key_metrics', {})}")
            print(f"  - Industry: {result.get('industry')}")
            print(f"  - Stage: {result.get('stage')}")
            
            # Show chunk breakdown
            chunks = result.get('chunks', [])
            if chunks:
                type_counts = {}
                for c in chunks:
                    t = c.get('type', 'general')
                    type_counts[t] = type_counts.get(t, 0) + 1
                print(f"  - Chunk breakdown: {type_counts}")
            
            return True
        else:
            print(f"[WARN] No test PDF found")
            return False
            
    except Exception as e:
        print(f"[FAIL] Pitch deck service test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("PIPELINE TEST SUITE - Voyage AI + Structured Extraction")
    print("="*60)
    
    # Change to backend directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    results = {}
    
    # Run tests
    results['pdf_extraction'], chunks = test_pdf_extraction()
    results['number_normalization'] = test_number_normalization()
    results['chunking'] = test_chunking()
    results['voyage_embeddings'] = test_voyage_embeddings()
    results['pitch_deck_service'] = test_pitch_deck_service()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in results.items():
        if result is True:
            status = "[OK] PASS"
        elif result is False:
            status = "[FAIL] FAIL"
        else:
            status = "[WARN] SKIP"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    
    if failed == 0:
        print("\n[SUCCESS] All critical tests passed! Pipeline is ready.")
    else:
        print(f"\n[WARN] {failed} test(s) failed. Review errors above.")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
