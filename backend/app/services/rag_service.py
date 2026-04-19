import os
import json
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
import voyageai

class RAGService:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.api_key = os.getenv("VOYAGE_API_KEY")
        self.model_name = "voyage-large-2"
        self.vector_dim = 1536 # Voyage Large dimension
        
        if self.api_key:
            self.client = voyageai.Client(api_key=self.api_key)
        else:
            print("⚠️ [WARNING] VOYAGE_API_KEY missing. RAG will be disabled.")
            self.client = None

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

    def add_documents(self, docs):
        if not self.client: return
        self._ensure_table()
        
        texts = [doc["text"] for doc in docs]
        # Professional Cloud Embedding (0MB RAM used)
        embeddings = self.client.embed(texts, model=self.model_name, input_type="document").embeddings
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for doc, embedding in zip(docs, embeddings):
                    cur.execute(
                        "INSERT INTO document_embeddings (text, metadata, embedding) VALUES (%s, %s, %s)",
                        (doc["text"], json.dumps(doc.get("metadata", {})), embedding)
                    )
                conn.commit()
        print(f"✅ Cloud-Synced {len(docs)} documents to Neon")

    def query(self, query_text, k=5):
        if not self.client: return []
        self._ensure_table()
        
        query_embedding = self.client.embed([query_text], model=self.model_name, input_type="query").embeddings[0]
        
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT text, metadata FROM document_embeddings ORDER BY embedding <=> %s LIMIT %s",
                    (query_embedding, k)
                )
                results = []
                for text, metadata in cur.fetchall():
                    results.append({"text": text, **metadata})
                return results

    def load(self): pass
    def save(self): pass
