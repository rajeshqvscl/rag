import os
import json
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

class RAGService:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.vector_dim = 384
        self.model = None # Lazy load

    def _get_conn(self):
        conn = psycopg2.connect(self.db_url)
        register_vector(conn)
        return conn

    def _ensure_table(self):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS document_embeddings (
                        id SERIAL PRIMARY KEY,
                        text TEXT,
                        metadata JSONB,
                        embedding vector({self.vector_dim})
                    )
                """)
                conn.commit()

    def _lazy_load_model(self):
        if self.model is None:
            print(f"🚀 [MEMORY] Loading Stable AI Model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)

    def add_documents(self, docs):
        self._ensure_table()
        self._lazy_load_model()
        
        texts = [doc["text"] for doc in docs]
        embeddings = self.model.encode(texts)
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for doc, embedding in zip(docs, embeddings):
                    cur.execute(
                        "INSERT INTO document_embeddings (text, metadata, embedding) VALUES (%s, %s, %s)",
                        (doc["text"], json.dumps(doc.get("metadata", {})), embedding.tolist())
                    )
                conn.commit()
        print(f"✅ Synced {len(docs)} documents to Neon Cloud Vectors")

    def query(self, query_text, k=5):
        self._ensure_table()
        self._lazy_load_model()
        
        query_embedding = self.model.encode([query_text])[0]
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT text, metadata FROM document_embeddings ORDER BY embedding <=> %s LIMIT %s",
                    (query_embedding.tolist(), k)
                )
                results = []
                for text, metadata in cur.fetchall():
                    results.append({"text": text, **metadata})
                return results

    def load(self): pass
    def save(self): pass
