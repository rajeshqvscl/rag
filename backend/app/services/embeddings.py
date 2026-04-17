"""
Embedding service - defaults to local sentence-transformers
Can use Voyage AI if configured
"""
import os
import numpy as np

# Use local by default, can override to voyage
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")

def get_embedding(text: str):
    """Get single embedding"""
    if EMBEDDING_PROVIDER == "voyage":
        from app.services.voyage_embeddings import embed_query
        return np.array(embed_query(text))
    else:
        # Fallback to sentence-transformers
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)
        emb = model.encode(text)
        return emb / np.linalg.norm(emb)

def get_embeddings(texts: list):
    """Get embeddings for multiple texts"""
    if EMBEDDING_PROVIDER == "voyage":
        from app.services.voyage_embeddings import embed_texts
        return np.array(embed_texts(texts))
    else:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)
        embeddings = model.encode(texts)
        return embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)