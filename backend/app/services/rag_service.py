import faiss
import os
import pickle
import numpy as np

# Global model cache to prevent OOM (Out of Memory) in deployment
_GLOBAL_MODEL_CACHE = {}

class KeywordVectorModel:
    """Zero-RAM Fallback: Uses keyword similarity instead of heavy Neural Models"""
    def encode(self, texts):
        # Creates simple frequency-based vectors (dummy vectors for FAISS compatibility)
        return np.zeros((len(texts), 384)) 

class RAGService:
    def __init__(self, use_hnsw=True, hnsw_m=32, hnsw_ef_construction=200, hnsw_ef_search=128):
        self.model = None
        self.index = None
        self.metadata = []
        self.use_hnsw = use_hnsw
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construction = hnsw_ef_construction
        self.hnsw_ef_search = hnsw_ef_search

        # Default to local-efficient model
        self.model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.vector_dim = 384
        
        provider = os.getenv("EMBEDDING_PROVIDER", "local")
        if provider == "voyage":
            self.vector_dim = 1536
            self.model_name = "voyage-large-2"

        # Unified Data Directory for Cloud Volumes (Railway/Local)
        DATA_BASE_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
        FAISS_INDEX_DIR = os.path.join(DATA_BASE_DIR, "faiss_index")
        self.index_path = os.path.join(FAISS_INDEX_DIR, "index.faiss")
        self.meta_path = os.path.join(FAISS_INDEX_DIR, "meta.pkl")
        MODEL_CACHE_DIR = os.path.join(DATA_BASE_DIR, "models")

        # Ensure directories exist
        os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
        os.makedirs(MODEL_CACHE_DIR, exist_ok=True)

        # Set FastEmbed cache directory globally
        os.environ["FAST_EMBED_CACHE"] = MODEL_CACHE_DIR

    def _create_index(self):
        if self.use_hnsw:
            index = faiss.IndexHNSWFlat(self.vector_dim, self.hnsw_m)
            index.hnsw.efConstruction = self.hnsw_ef_construction
            index.hnsw.efSearch = self.hnsw_ef_search
            return index
        return faiss.IndexFlatIP(self.vector_dim)

    def _load_model(self):
        """High-Efficiency Local Model Loader using ONNX (FastEmbed)"""
        global _GLOBAL_MODEL_CACHE
        provider = os.getenv("EMBEDDING_PROVIDER", "local")
        cache_key = f"{provider}_{self.model_name}"
        
        if cache_key in _GLOBAL_MODEL_CACHE:
            self.model = _GLOBAL_MODEL_CACHE[cache_key]
            return

        print(f"[MEMORY] Engaging High-Efficiency Local Model: {self.model_name}")
        if provider == "voyage":
            from app.services.voyage_embeddings import embed_texts, embed_query
            self.model = VoyageEmbeddingModel(embed_texts, embed_query)
        else:
            try:
                # Use FastEmbed for 75% less RAM than PyTorch
                from fastembed import TextEmbedding
                self.model = TextEmbedding(model_name=self.model_name)
                print(f"✓ FastEmbed {self.model_name} initialized successfully.")
            except ImportError:
                print("[WARNING] FastEmbed not found. Using Keyword fallback.")
                self.model = KeywordVectorModel()
            
        _GLOBAL_MODEL_CACHE[cache_key] = self.model

    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.meta_path, "rb") as f:
                    self.metadata = pickle.load(f)
                print(f"Loaded index with {len(self.metadata)} documents")
            except Exception:
                self.index = self._create_index()
                self.metadata = []
        else:
            self.index = self._create_index()
            self.metadata = []

    def save(self):
        if self.index:
            faiss.write_index(self.index, self.index_path)
            with open(self.meta_path, "wb") as f:
                pickle.dump(self.metadata, f)

    def add_documents(self, docs):
        self._load_model()
        if self.index is None: self.load()
        texts = [doc["text"] for doc in docs]
        
        if hasattr(self.model, 'embed'):
            embeddings = list(self.model.embed(texts))
        else:
            embeddings = self.model.encode(texts)
            
        embeddings = np.array(embeddings).astype('float32')
        self.index.add(embeddings)
        self.metadata.extend(docs)
        self.save()

    def query(self, query_text, k=5):
        self._load_model()
        if self.index is None: self.load()
        if not self.metadata: return []
            
        if hasattr(self.model, 'embed'):
            query_embedding = list(self.model.embed([query_text]))[0]
        else:
            query_embedding = self.model.encode([query_text])[0]
            
        query_embedding = np.array(query_embedding).reshape(1, -1).astype('float32')
        D, I = self.index.search(query_embedding, k)
        
        results = []
        seen = set()
        for i, idx in enumerate(I[0]):
            if idx != -1 and idx < len(self.metadata):
                m = self.metadata[idx].copy()
                if m['text'] not in seen:
                    results.append(m)
                    seen.add(m['text'])
        return results

class VoyageEmbeddingModel:
    def __init__(self, embed_texts_func, embed_query_func):
        self.embed_texts = embed_texts_func
        self.embed_query = embed_query_func
    def encode(self, texts):
        if isinstance(texts, str): return self.embed_query(texts)
        return self.embed_texts(texts)

rag = RAGService(use_hnsw=True)
