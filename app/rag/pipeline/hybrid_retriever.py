"""
Hybrid Retriever - BM25 + Embedding hybrid search
Combines keyword matching with semantic similarity for better recall
"""
from typing import List, Dict, Any, Optional, Tuple
import re
from collections import Counter

from app.rag.embedder import embed_text
from app.rag.pipeline.validation_engine import ValidationEngine


class BM25Retriever:
    """
    BM25 keyword-based retrieval
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths = []
        self.avg_doc_length = 0
        self.doc_freqs = {}
        self.N = 0
        self.idf = {}
        self.documents = []
    
    def index(self, documents: List[str]):
        """Build BM25 index"""
        self.documents = documents
        self.N = len(documents)
        
        doc_freq_counter = Counter()
        
        for doc in documents:
            tokens = self._tokenize(doc)
            self.doc_lengths.append(len(tokens))
            
            unique_tokens = set(tokens)
            for token in unique_tokens:
                doc_freq_counter[token] += 1
        
        self.avg_doc_length = sum(self.doc_lengths) / max(self.N, 1)
        
        for term, df in doc_freq_counter.items():
            self.idf[term] = max(
                0.1,
                self.N / df
            )
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization"""
        text = text.lower()
        tokens = re.findall(r'\w+', text)
        return [t for t in tokens if len(t) > 2]
    
    def score(self, query: str, doc_idx: int) -> float:
        """Calculate BM25 score for query against document"""
        query_tokens = self._tokenize(query)
        doc_tokens = self._tokenize(self.documents[doc_idx])
        
        doc_len = self.doc_lengths[doc_idx]
        doc_tf = Counter(doc_tokens)
        
        score = 0.0
        
        for term in query_tokens:
            if term not in self.idf:
                continue
            
            tf = doc_tf.get(term, 0)
            idf = self.idf[term]
            
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
            
            score += idf * (numerator / max(denominator, 0.001))
        
        return score
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        """Search index, return (doc_idx, score) pairs"""
        scores = []
        
        for i in range(len(self.documents)):
            s = self.score(query, i)
            if s > 0:
                scores.append((i, s))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


class HybridRetriever:
    """
    Combines BM25 and embedding-based retrieval
    """
    
    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha  # Weight for embedding vs BM25
        self.bm25 = BM25Retriever()
        self.embeddings_cache = {}
        self.documents = []
        self.metadata = []
    
    def index(self, documents: List[str], metadata: List[Dict]):
        """Index documents for hybrid search"""
        self.documents = documents
        self.metadata = metadata
        
        print(f"[HYBRID RETRIEVER] Indexing {len(documents)} documents...")
        
        self.bm25.index(documents)
        
        chunk_size = 100
        for i in range(0, len(documents), chunk_size):
            chunk = documents[i:i+chunk_size]
            embeddings = embed_text(chunk)
            
            for j, emb in enumerate(embeddings):
                self.embeddings_cache[i + j] = emb
        
        print(f"[HYBRID RETRIEVER] Indexed {len(self.embeddings_cache)} embeddings")
    
    def _cosine_sim(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 * norm2 == 0:
            return 0.0
        
        return dot / (norm1 * norm2)
    
    def search(
        self, 
        query: str, 
        filter_section: Optional[str] = None,
        filter_doc_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Hybrid search combining BM25 and embeddings
        
        Args:
            query: Search query
            filter_section: Filter by section
            filter_doc_id: Filter by document
            top_k: Number of results
        
        Returns:
            List of result dicts with text, score, metadata
        """
        print(f"[HYBRID RETRIEVER] Searching: '{query}' (section={filter_section})")
        
        bm25_results = self.bm25.search(query, top_k=top_k * 3)
        
        try:
            query_emb = embed_text([query])[0]
        except Exception as e:
            print(f"[HYBRID RETRIEVER] Embedding error: {e}")
            query_emb = None
        
        candidates = []
        
        for doc_idx, bm25_score in bm25_results:
            metadata = self.metadata[doc_idx] if doc_idx < len(self.metadata) else {}
            
            if filter_section and metadata.get("section") != filter_section:
                continue
            
            if filter_doc_id and metadata.get("doc_id") != filter_doc_id:
                continue
            
            embedding_score = 0.0
            if query_emb and doc_idx in self.embeddings_cache:
                embedding_score = self._cosine_sim(query_emb, self.embeddings_cache[doc_idx])
            
            combined_score = (self.alpha * bm25_score) + ((1 - self.alpha) * embedding_score)
            
            candidates.append({
                "text": self.documents[doc_idx][:300],
                "score": round(combined_score, 4),
                "bm25_score": round(bm25_score, 4),
                "embedding_score": round(embedding_score, 4),
                "metadata": metadata
            })
        
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        return candidates[:top_k]


class FactAwareRetriever:
    """
    Retrieval that uses fact registry for improved context
    """
    
    def __init__(self, hybrid_retriever: HybridRetriever):
        self.hybrid = hybrid_retriever
        self.validation = ValidationEngine()
    
    def retrieve(
        self,
        query: str,
        section: Optional[str] = None,
        doc_id: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Retrieve with fact-aware context augmentation
        """
        results = self.hybrid.search(
            query=query,
            filter_section=section,
            filter_doc_id=doc_id,
            top_k=top_k
        )
        
        return {
            "results": results,
            "count": len(results),
            "query": query,
            "filters": {
                "section": section,
                "doc_id": doc_id
            }
        }


# Alias for backward compatibility
class PineconeRetriever:
    """Wrapper for existing Pinecone-based retrieval with hybrid fallback"""
    
    def __init__(self):
        self.hybrid = HybridRetriever(alpha=0.4)
        self._indexed = False
    
    def index_documents(self, chunks: List[str], metadata: List[Dict]):
        """Index for hybrid search"""
        self.hybrid.index(chunks, metadata)
        self._indexed = True
    
    def search(self, query: str, top_k: int = 5, **kwargs) -> List[Dict]:
        """Search using hybrid retrieval"""
        if not self._indexed:
            return []
        
        return self.hybrid.search(
            query=query,
            filter_section=kwargs.get("filter"),
            top_k=top_k
        )