"""
Voyage AI Embeddings Service - voyage-large-2 (1536 dims)
"""
import os
import numpy as np
import faiss
from typing import List

# Lazy load client
_vo_client = None

def _get_voyage_client():
    global _vo_client
    if _vo_client is None:
        import voyageai
        api_key = os.getenv("VOYAGE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY or ANTHROPIC_API_KEY not set")
        _vo_client = voyageai.Client(api_key=api_key)
    return _vo_client

def embed_texts(texts: List[str], model: str = "voyage-large-2") -> List[List[float]]:
    """Get embeddings for multiple texts using Voyage AI"""
    if not texts:
        return []
    
    vo = _get_voyage_client()
    
    # Voyage handles batching automatically
    result = vo.embed(texts, model=model, input_type="document")
    return result.embeddings

def embed_query(query: str, model: str = "voyage-large-2") -> List[float]:
    """Get embedding for a single query"""
    vo = _get_voyage_client()
    result = vo.embed([query], model=model, input_type="query")
    return result.embeddings[0]

def get_embedding(text: str) -> np.ndarray:
    """Legacy-compatible single embedding function"""
    emb = embed_query(text)
    return np.array(emb)

def get_embeddings(texts: List[str]) -> np.ndarray:
    """Legacy-compatible batch embedding function"""
    embs = embed_texts(texts)
    return np.array(embs)

class VoyageFAISSIndex:
    """FAISS index optimized for Voyage embeddings (1536 dims)"""
    
    DIM = 1536
    
    def __init__(self, index_path: str = "app/data/voyage_index.faiss", 
                 meta_path: str = "app/data/voyage_meta.pkl"):
        self.index_path = index_path
        self.meta_path = meta_path
        self.index = None
        self.metadata = []
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
    
    def _create_index(self):
        """Create HNSW index for fast approximate search"""
        import faiss
        # HNSW for better performance with 1536-dim vectors
        index = faiss.IndexHNSWFlat(self.DIM, 32)
        index.hnsw.efConstruction = 200
        index.hnsw.efSearch = 128
        return index
    
    def add_documents(self, texts: List[str], metadatas: List[dict] = None):
        """Add documents to index"""
        import faiss
        
        if metadatas is None:
            metadatas = [{"text": t} for t in texts]
        
        # Get embeddings
        embeddings = embed_texts(texts)
        vectors = np.array(embeddings).astype("float32")
        
        # Normalize for cosine similarity
        faiss.normalize_L2(vectors)
        
        # Initialize index if needed
        if self.index is None:
            self.index = self._create_index()
        
        # Add to index
        self.index.add(vectors)
        self.metadata.extend(metadatas)
        
        # Save
        self._save()
    
    def search(self, query: str, k: int = 5) -> List[tuple]:
        """Search index for query"""
        import faiss
        
        if self.index is None:
            self._load()
        
        if self.index is None or self.index.ntotal == 0:
            return []
        
        # Embed query
        q_emb = embed_query(query)
        q_vec = np.array([q_emb]).astype("float32")
        faiss.normalize_L2(q_vec)
        
        # Search
        distances, indices = self.index.search(q_vec, k)
        
        # Return results with metadata
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.metadata):
                results.append((self.metadata[idx], float(distances[0][i])))
        
        return results
    
    def _save(self):
        """Save index and metadata"""
        import pickle
        if self.index is not None:
            faiss.write_index(self.index, self.index_path)
            with open(self.meta_path, "wb") as f:
                pickle.dump(self.metadata, f)
    
    def _load(self):
        """Load index and metadata"""
        import pickle
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.meta_path, "rb") as f:
                    self.metadata = pickle.load(f)
                print(f"Loaded Voyage index with {len(self.metadata)} documents")
            except Exception as e:
                print(f"Failed to load Voyage index: {e}")
                self.index = None
                self.metadata = []
