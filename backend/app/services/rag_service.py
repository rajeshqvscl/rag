import faiss
import os
import pickle
import numpy as np


class RAGService:
    def __init__(self, use_hnsw=True, hnsw_m=32, hnsw_ef_construction=200, hnsw_ef_search=128):
        """
        Initialize RAG Service with optional HNSW index
        
        Args:
            use_hnsw: Use HNSW index instead of flat index (much faster for large datasets)
            hnsw_m: Number of connections per layer (higher = more accurate, slower build)
            hnsw_ef_construction: Size of dynamic candidate list during construction
            hnsw_ef_search: Size of dynamic candidate list during search (higher = more accurate)
        """
        self.model = None
        self.index = None
        self.metadata = []
        
        self.use_hnsw = use_hnsw
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construction = hnsw_ef_construction
        self.hnsw_ef_search = hnsw_ef_search
        self.vector_dim = 384  # Dimension of all-MiniLM-L6-v2 embeddings

        self.index_path = "app/data/faiss_index/index.faiss"
        self.meta_path = "app/data/faiss_index/meta.pkl"
        self.model_name = "all-MiniLM-L6-v2"

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)

        # Lazy load - don't load index on startup to save memory
        # Index will be loaded on first use
        
    def _create_index(self):
        """Create appropriate FAISS index based on configuration"""
        if self.use_hnsw:
            # HNSW Index - graph-based approximate nearest neighbor
            # Much faster for large datasets with minimal accuracy loss
            print(f"Creating HNSW index (M={self.hnsw_m}, efConstruction={self.hnsw_ef_construction})")
            index = faiss.IndexHNSWFlat(self.vector_dim, self.hnsw_m)
            index.hnsw.efConstruction = self.hnsw_ef_construction
            index.hnsw.efSearch = self.hnsw_ef_search
            return index
        else:
            # Flat Index - exact brute force search
            # Simpler but slower for large datasets
            print("Creating Flat IP index (exact search)")
            return faiss.IndexFlatIP(self.vector_dim)

    def _load_model(self):
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)

    def load(self):
        """Load existing index or create new one"""
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.meta_path, "rb") as f:
                    self.metadata = pickle.load(f)
                print(f"Loaded index with {len(self.metadata)} documents")
                
                # Check if loaded index type matches configuration
                is_hnsw_loaded = hasattr(self.index, 'hnsw') or \
                                (hasattr(self.index, 'index') and hasattr(self.index.index, 'hnsw'))
                if self.use_hnsw != is_hnsw_loaded:
                    print(f"Warning: Loaded index type differs from configuration (use_hnsw={self.use_hnsw})")
                    
            except Exception as e:
                print(f"Failed to load FAISS index: {e}. Creating new index.")
                self.index = self._create_index()
                self.metadata = []
        else:
            print("No existing index found. Creating new index.")
            self.index = self._create_index()
            self.metadata = []

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "wb") as f:
            pickle.dump(self.metadata, f)

    def add_documents(self, docs):
        """Add documents to the index"""
        self._load_model()
        texts = [doc["text"] for doc in docs]
        embeddings = self.model.encode(texts)
        
        # Convert to float32 for FAISS
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings)
        embeddings = embeddings.astype('float32')
        
        # Simple add works for both HNSW and Flat indices
        # FAISS maintains internal sequential IDs that match our metadata list
        self.index.add(embeddings)
        self.metadata.extend(docs)
        self.save()
        print(f"Added {len(docs)} documents. Total: {len(self.metadata)}")

    def query(self, query_text, k=5, symbol=None):
        """Query the index with vector search + optional keyword fallback"""
        self._load_model()
        
        if len(self.metadata) == 0:
            return []
        
        # 1. Vector Search
        query_embedding = self.model.encode([query_text])
        
        # Convert to float32
        if not isinstance(query_embedding, np.ndarray):
            query_embedding = np.array(query_embedding)
        query_embedding = query_embedding.astype('float32')
        
        # Search with over-fetching for filtering
        search_k = min(k * 3, len(self.metadata))  # Get more candidates for filtering
        D, I = self.index.search(query_embedding, search_k)

        results = []
        seen_texts = set()
        
        for i, idx in enumerate(I[0]):
            if idx == -1:  # FAISS returns -1 for empty slots
                continue
            if idx < len(self.metadata):
                m = self.metadata[idx].copy()
                m['score'] = float(D[0][i]) if i < len(D[0]) else 0.0
                if symbol and m.get('symbol') != symbol:
                    continue
                if m['text'] not in seen_texts:
                    results.append(m)
                    seen_texts.add(m['text'])

        # 2. Keyword Search (Simple fallback)
        if len(results) < k:
            keywords = query_text.lower().split()
            keyword_results = []
            for m in self.metadata:
                if symbol and m.get('symbol') != symbol:
                    continue
                if m['text'] not in seen_texts:
                    text_lower = m['text'].lower()
                    if any(kw in text_lower for kw in keywords):
                        m_copy = m.copy()
                        m_copy['score'] = 0.5  # Lower score for keyword matches
                        keyword_results.append(m_copy)
                        seen_texts.add(m['text'])
            
            results.extend(keyword_results)
        
        # Sort by score and return top k
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:k]


    def get_stats(self):
        """Get index statistics"""
        stats = {
            "total_documents": len(self.metadata),
            "index_type": "HNSW" if self.use_hnsw else "Flat",
            "vector_dimension": self.vector_dim,
            "model_name": self.model_name
        }
        
        if self.use_hnsw and hasattr(self.index, 'hnsw'):
            stats["hnsw_m"] = self.hnsw_m
            stats["hnsw_ef_construction"] = self.hnsw_ef_construction
            stats["hnsw_ef_search"] = self.hnsw_ef_search
            stats["hnsw_levels"] = self.index.hnsw.max_level if hasattr(self.index.hnsw, 'max_level') else None
        elif self.use_hnsw and hasattr(self.index, 'index') and hasattr(self.index.index, 'hnsw'):
            inner = self.index.index
            stats["hnsw_m"] = self.hnsw_m
            stats["hnsw_ef_construction"] = self.hnsw_ef_construction
            stats["hnsw_ef_search"] = self.hnsw_ef_search
            stats["hnsw_levels"] = inner.hnsw.max_level if hasattr(inner.hnsw, 'max_level') else None
            
        return stats
    
    def benchmark_query(self, query_text="financial analysis report", k=5, iterations=100):
        """Benchmark query performance"""
        import time
        
        if len(self.metadata) == 0:
            return {"error": "No documents in index"}
        
        self._load_model()
        query_embedding = self.model.encode([query_text]).astype('float32')
        
        # Warmup
        for _ in range(5):
            self.index.search(query_embedding, k)
        
        # Benchmark
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            self.index.search(query_embedding, k)
            end = time.perf_counter()
            times.append((end - start) * 1000)  # Convert to ms
        
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        return {
            "index_type": "HNSW" if self.use_hnsw else "Flat",
            "total_docs": len(self.metadata),
            "iterations": iterations,
            "k": k,
            "avg_ms": round(avg_time, 3),
            "min_ms": round(min_time, 3),
            "max_ms": round(max_time, 3),
            "queries_per_second": round(1000 / avg_time, 1)
        }
    
    def rebuild_index(self, use_hnsw=None, hnsw_m=None, hnsw_ef_construction=None):
        """Rebuild index with new configuration"""
        if use_hnsw is not None:
            self.use_hnsw = use_hnsw
        if hnsw_m is not None:
            self.hnsw_m = hnsw_m
        if hnsw_ef_construction is not None:
            self.hnsw_ef_construction = hnsw_ef_construction
            
        print(f"Rebuilding index with HNSW={self.use_hnsw}")
        
        # Save old data
        old_metadata = self.metadata.copy()
        
        # Create new index
        self.metadata = []
        self.index = self._create_index()
        
        # Re-add all documents
        if old_metadata:
            batch_size = 100
            for i in range(0, len(old_metadata), batch_size):
                batch = old_metadata[i:i+batch_size]
                self.add_documents(batch)
                print(f"Re-added {min(i+batch_size, len(old_metadata))}/{len(old_metadata)} documents")
        
        self.save()
        print(f"Index rebuilt with {len(self.metadata)} documents")
        return self.get_stats()


# Create global instance with HNSW enabled
rag = RAGService(use_hnsw=True, hnsw_m=32, hnsw_ef_construction=200, hnsw_ef_search=128)
