from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer('all-MiniLM-L6-v2')  # or your current model

def get_embedding(text: str):
    emb = model.encode(text)
    emb = emb / np.linalg.norm(emb)  # normalize
    return emb

def get_embeddings(texts: list):
    """Get embeddings for multiple texts"""
    embeddings = model.encode(texts)
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)  # normalize
    return embeddings