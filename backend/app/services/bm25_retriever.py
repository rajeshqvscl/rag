"""
BM25 Retrieval System for Pitch Decks
Implements BM25 + FAISS hybrid retrieval for comparison testing
"""
import os
import json
import pickle
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import numpy as np

# Try to import BM25
BM25_AVAILABLE = False
try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
    print("[OK] BM25 available")
except ImportError:
    print("[WARN] rank_bm25 not installed - run: pip install rank-bm25")

# Try to import sentence transformers for embeddings
EMBEDDINGS_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
    print("[OK] Sentence Transformers available")
except ImportError:
    print("[WARN] sentence-transformers not installed - run: pip install sentence-transformers")


@dataclass
class Chunk:
    """Document chunk with metadata"""
    id: str
    text: str
    page: int
    chunk_type: str  # 'text', 'table', 'chart', 'header'
    metadata: Dict[str, Any]


class BM25Retriever:
    """BM25-based document retriever with optional FAISS embeddings"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.bm25 = None
        self.chunks: List[Chunk] = []
        self.tokenized_corpus: List[List[str]] = []
        
        # FAISS for embedding-based retrieval (optional comparison)
        self.faiss_index = None
        self.embedding_model = None
        self.chunk_embeddings = None
        
        if EMBEDDINGS_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer(model_name)
                print(f"[OK] Loaded embedding model: {model_name}")
            except Exception as e:
                print(f"[WARN] Failed to load embedding model: {e}")
    
    def chunk_document(self, text: str, pages: int, chunk_size: int = 500, overlap: int = 100) -> List[Chunk]:
        """
        Split document into overlapping chunks
        
        Args:
            text: Full document text
            pages: Number of pages
            chunk_size: Target chunk size in characters
            overlap: Overlap between chunks
            
        Returns:
            List of Chunk objects
        """
        chunks = []
        
        # Simple sliding window chunking
        start = 0
        chunk_id = 0
        
        while start < len(text):
            end = min(start + chunk_size, len(text))
            
            # Try to break at sentence or paragraph
            if end < len(text):
                # Look for sentence boundary
                for i in range(min(end, len(text) - 1), start, -1):
                    if text[i] in '.!?' and i + 1 < len(text) and text[i + 1] in ' \n':
                        end = i + 1
                        break
            
            chunk_text = text[start:end].strip()
            
            if len(chunk_text) > 50:  # Minimum chunk size
                # Estimate page number
                page = min(int(start / (len(text) / pages)) + 1, pages) if pages > 0 else 1
                
                chunk = Chunk(
                    id=f"chunk_{chunk_id:04d}",
                    text=chunk_text,
                    page=page,
                    chunk_type="text",
                    metadata={
                        "start_char": start,
                        "end_char": end,
                        "char_count": len(chunk_text)
                    }
                )
                chunks.append(chunk)
                chunk_id += 1
            
            start = end - overlap
            if start >= len(text):
                break
        
        print(f"✓ Created {len(chunks)} chunks (size={chunk_size}, overlap={overlap})")
        return chunks
    
    def index_document(self, text: str, pages: int, chunk_size: int = 500, use_embeddings: bool = True) -> Dict:
        """
        Index a document for retrieval
        
        Args:
            text: Document text
            pages: Page count
            chunk_size: Chunk size
            use_embeddings: Whether to also create FAISS embeddings
            
        Returns:
            Indexing statistics
        """
        # Create chunks
        self.chunks = self.chunk_document(text, pages, chunk_size)
        
        if not self.chunks:
            return {"status": "error", "message": "No chunks created"}
        
        stats = {
            "total_chunks": len(self.chunks),
            "bm25_available": BM25_AVAILABLE,
            "embeddings_available": EMBEDDINGS_AVAILABLE and use_embeddings
        }
        
        # Build BM25 index
        if BM25_AVAILABLE:
            self.tokenized_corpus = [self._tokenize(chunk.text) for chunk in self.chunks]
            self.bm25 = BM25Okapi(self.tokenized_corpus)
            stats["bm25_indexed"] = True
            print(f"✓ BM25 index built with {len(self.tokenized_corpus)} documents")
        
        # Build FAISS index (for comparison)
        if use_embeddings and EMBEDDINGS_AVAILABLE and self.embedding_model:
            try:
                import faiss
                
                # Create embeddings
                chunk_texts = [chunk.text for chunk in self.chunks]
                print(f"Generating embeddings for {len(chunk_texts)} chunks...")
                self.chunk_embeddings = self.embedding_model.encode(
                    chunk_texts, 
                    show_progress_bar=True,
                    convert_to_numpy=True
                )
                
                # Build FAISS index
                dimension = self.chunk_embeddings.shape[1]
                self.faiss_index = faiss.IndexFlatIP(dimension)  # Inner product (cosine similarity)
                
                # Normalize for cosine similarity
                faiss.normalize_L2(self.chunk_embeddings)
                self.faiss_index.add(self.chunk_embeddings)
                
                stats["faiss_indexed"] = True
                stats["embedding_dim"] = dimension
                print(f"✓ FAISS index built: {self.faiss_index.ntotal} vectors, dim={dimension}")
                
            except ImportError:
                print("⚠ FAISS not installed - run: pip install faiss-cpu")
                stats["faiss_indexed"] = False
            except Exception as e:
                print(f"⚠ FAISS indexing failed: {e}")
                stats["faiss_indexed"] = False
        
        return stats
    
    def search(self, query: str, top_k: int = 5, method: str = "hybrid") -> List[Dict]:
        """
        Search indexed documents
        
        Args:
            query: Search query
            top_k: Number of results
            method: 'bm25', 'embedding', or 'hybrid'
            
        Returns:
            List of results with scores
        """
        if not self.chunks:
            return []
        
        results = []
        
        # BM25 search
        if method in ["bm25", "hybrid"] and BM25_AVAILABLE and self.bm25:
            tokenized_query = self._tokenize(query)
            bm25_scores = self.bm25.get_scores(tokenized_query)
            
            # Get top-k BM25 results
            top_indices = np.argsort(bm25_scores)[-top_k:][::-1]
            
            for idx in top_indices:
                if bm25_scores[idx] > 0:
                    results.append({
                        "chunk_id": self.chunks[idx].id,
                        "text": self.chunks[idx].text[:300] + "...",
                        "page": self.chunks[idx].page,
                        "bm25_score": float(bm25_scores[idx]),
                        "method": "bm25"
                    })
        
        # Embedding search
        if method in ["embedding", "hybrid"] and self.faiss_index and self.embedding_model:
            query_embedding = self.embedding_model.encode([query], convert_to_numpy=True)
            faiss.normalize_L2(query_embedding)
            
            distances, indices = self.faiss_index.search(query_embedding, top_k)
            
            for i, idx in enumerate(indices[0]):
                if idx >= 0 and idx < len(self.chunks):
                    results.append({
                        "chunk_id": self.chunks[idx].id,
                        "text": self.chunks[idx].text[:300] + "...",
                        "page": self.chunks[idx].page,
                        "embedding_score": float(distances[0][i]),
                        "method": "embedding"
                    })
        
        # Hybrid: combine scores
        if method == "hybrid":
            # Merge and deduplicate
            seen_ids = set()
            unique_results = []
            for r in results:
                if r["chunk_id"] not in seen_ids:
                    seen_ids.add(r["chunk_id"])
                    unique_results.append(r)
            results = unique_results[:top_k]
        
        return results
    
    def compare_methods(self, query: str, top_k: int = 5) -> Dict:
        """
        Compare BM25 vs Embedding retrieval for a query
        
        Returns:
            Comparison results
        """
        bm25_results = self.search(query, top_k, method="bm25")
        embedding_results = self.search(query, top_k, method="embedding")
        hybrid_results = self.search(query, top_k, method="hybrid")
        
        return {
            "query": query,
            "bm25": {
                "count": len(bm25_results),
                "top_scores": [r.get("bm25_score", 0) for r in bm25_results[:3]],
                "results": bm25_results
            },
            "embedding": {
                "count": len(embedding_results),
                "top_scores": [r.get("embedding_score", 0) for r in embedding_results[:3]],
                "results": embedding_results
            },
            "hybrid": {
                "count": len(hybrid_results),
                "results": hybrid_results
            }
        }
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization for BM25"""
        # Lowercase and split on non-alphanumeric
        import re
        return re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Chunk]:
        """Get full chunk by ID"""
        for chunk in self.chunks:
            if chunk.id == chunk_id:
                return chunk
        return None


# Singleton instance
bm25_retriever = BM25Retriever()
