"""Embedding service - Voyage AI ONLY (voyage-large-2)
No fallback - Voyage is required for pitch deck analysis
"""
import os
import numpy as np

def get_embedding(text: str):
    """Get single embedding using Voyage AI ONLY"""
    from app.services.voyage_embeddings import embed_query
    return np.array(embed_query(text))

def get_embeddings(texts: list):
    """Get embeddings for multiple texts using Voyage AI ONLY"""
    from app.services.voyage_embeddings import embed_texts
    return np.array(embed_texts(texts))