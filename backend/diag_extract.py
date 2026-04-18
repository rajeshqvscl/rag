import sys, os
sys.path.insert(0, '.')

path = 'data/pitch_decks/Bijliride_Pitch_Deck_V4_20260416_102253.pdf'

from app.services.pdf_extractor import pdf_extractor
full_text, chunks, metadata = pdf_extractor.extract_pdf(path)

print('=== RAW EXTRACTOR OUTPUT ===')
print(f'full_text length: {len(full_text)}')
print(f'chunks count: {len(chunks)}')
print(f'metadata: {metadata}')
print(f'text preview: {repr(full_text[:300])}')
print()

from app.services.pitch_deck_service import PitchDeckService
svc = PitchDeckService()
extracted = svc.extract_pdf_text(path, 'Bijliride_Pitch_Deck_V4.pdf')
print('=== PITCHDECKSERVICE RESULT ===')
print(f'pages: {extracted.get("pages")}')
print(f'text length: {len(extracted.get("text",""))}')
print(f'company_name: {extracted.get("company_name")}')
print(f'industry: {extracted.get("industry")}')
print(f'stage: {extracted.get("stage")}')
print(f'key_metrics: {extracted.get("key_metrics")}')
print(f'founders: {extracted.get("founders",[])}')
print(f'chunks count: {len(extracted.get("chunks",[]))}')
print(f'summary: {repr(extracted.get("summary",""))[:200]}')
