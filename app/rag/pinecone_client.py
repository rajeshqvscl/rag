import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

if not PINECONE_API_KEY:
    raise Exception("[ERROR] Missing PINECONE_API_KEY")

pc = Pinecone(api_key=PINECONE_API_KEY)

INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rag-index")
index = pc.Index(INDEX_NAME)

print("[SUCCESS] Connected to Pinecone:", INDEX_NAME)

EXPECTED_DIM = 768
try:
    index_stats = index.describe_index_stats()
    actual_dim = index_stats.get("dimension")
    if actual_dim and actual_dim != EXPECTED_DIM:
        print(f"[WARNING] Pinecone index dimension {actual_dim} does not match expected {EXPECTED_DIM}")
        print(f"[WARNING] This will cause retrieval failures. Consider recreating the index with dimension {EXPECTED_DIM}")
    else:
        print(f"[SUCCESS] Pinecone index dimension validated: {actual_dim or EXPECTED_DIM}")
except Exception as e:
    print(f"[WARNING] Could not validate Pinecone index dimension: {e}")