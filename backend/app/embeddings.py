from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer('all-MiniLM-L6-v2')  # or your current model

def get_embedding(text: str):
    emb = model.encode(text)
    emb = emb / np.linalg.norm(emb)  # normalize
    return emb