"""
BM25 Retrieval Layer
Primary retrieval for the agentic RAG system.
Uses BM25 (Okapi BM25) over stored FAISS metadata — no GPU needed.
"""
import os
import re
import pickle
from typing import List, Dict, Any
from collections import defaultdict
import math


class BM25Retriever:
    """
    Lightweight BM25 retriever over the FAISS metadata index.
    Falls back to TF-IDF keyword scoring if rank_bm25 is unavailable.
    """

    def __init__(self, meta_path: str = "app/data/faiss_index/meta.pkl"):
        self.meta_path = meta_path
        self._corpus: List[str] = []
        self._docs: List[Dict] = []
        self._bm25 = None
        self._loaded = False

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def retrieve(self, query: str, k: int = 5, symbol: str = None) -> List[Dict]:
        """
        Retrieve top-k chunks relevant to query.
        Filters by symbol/company if provided.
        """
        self._ensure_loaded()

        if not self._corpus:
            return []

        tokens = self._tokenize(query)
        if self._bm25:
            scores = self._bm25.get_scores(tokens)
        else:
            scores = self._tfidf_scores(tokens)

        # Build ranked results
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results = []
        seen_texts = set()

        # Normalize company filter for text matching
        company_lower = symbol.lower() if symbol else None

        for idx, score in ranked:
            if score <= 0:
                continue
            doc = self._docs[idx].copy()
            doc["bm25_score"] = round(float(score), 4)
            text_key = doc.get("text", "")[:100]

            # Filter by company: match symbol OR company name appears in text
            if company_lower:
                doc_symbol = (doc.get("symbol") or "").lower()
                doc_text = doc.get("text", "").lower()
                if company_lower not in doc_symbol and company_lower not in doc_text:
                    continue

            if text_key in seen_texts:
                continue

            results.append(doc)
            seen_texts.add(text_key)

            if len(results) >= k:
                break

        return results

    def retrieve_for_email(self, email_text: str, company: str = None, k: int = 6) -> List[Dict]:
        """Specialised retrieval for email context — searches company name + key phrases."""
        queries = [email_text]
        if company:
            queries.append(company)

        # Extract key financial terms from email
        financial_terms = re.findall(
            r'\b(?:revenue|ARR|MRR|growth|funding|valuation|runway|burn|series|seed|'
            r'investment|return|profit|ebitda|margin|cagr|tam|sam)\b',
            email_text, flags=re.IGNORECASE
        )
        if financial_terms:
            queries.append(" ".join(set(financial_terms)))

        all_results: Dict[int, Dict] = {}
        for q in queries:
            for doc in self.retrieve(q, k=k, symbol=company):
                idx_key = doc.get("text", "")[:80]
                if idx_key not in all_results:
                    all_results[idx_key] = doc
                else:
                    # Accumulate score
                    all_results[idx_key]["bm25_score"] = (
                        all_results[idx_key].get("bm25_score", 0) + doc.get("bm25_score", 0)
                    )

        ranked = sorted(all_results.values(), key=lambda x: x.get("bm25_score", 0), reverse=True)
        return ranked[:k]

    def reload(self):
        """Force reload from disk."""
        self._loaded = False
        self._ensure_loaded()

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._load()
        self._loaded = True

    def _load(self):
        self._corpus = []
        self._docs = []
        self._bm25 = None

        if not os.path.exists(self.meta_path):
            print(f"[BM25] No metadata index at {self.meta_path}")
            return

        try:
            with open(self.meta_path, "rb") as f:
                self._docs = pickle.load(f)
        except Exception as e:
            print(f"[BM25] Failed to load metadata: {e}")
            return

        self._corpus = [self._tokenize(d.get("text", "")) for d in self._docs]

        try:
            from rank_bm25 import BM25Okapi
            self._bm25 = BM25Okapi(self._corpus)
            print(f"[BM25] Loaded BM25 index over {len(self._docs)} documents")
        except ImportError:
            print("[BM25] rank_bm25 not installed — using TF-IDF fallback")
            self._build_tfidf()

    def _tokenize(self, text: str) -> List[str]:
        """Simple whitespace + punctuation tokenizer, lowercase."""
        tokens = re.sub(r'[^\w\s\$%]', ' ', text.lower()).split()
        # Remove very short tokens
        return [t for t in tokens if len(t) > 1]

    def _build_tfidf(self):
        """Build TF-IDF term frequencies for fallback scoring."""
        self._df: Dict[str, int] = defaultdict(int)
        self._tf: List[Dict[str, float]] = []
        N = len(self._corpus)

        for tokens in self._corpus:
            freq: Dict[str, int] = defaultdict(int)
            for t in tokens:
                freq[t] += 1
            total = max(len(tokens), 1)
            self._tf.append({t: c / total for t, c in freq.items()})
            for t in set(tokens):
                self._df[t] += 1

        self._idf: Dict[str, float] = {
            t: math.log((N + 1) / (df + 1)) + 1
            for t, df in self._df.items()
        }

    def _tfidf_scores(self, query_tokens: List[str]) -> List[float]:
        """Score all documents against query using TF-IDF."""
        scores = []
        for tf in self._tf:
            score = sum(tf.get(t, 0) * self._idf.get(t, 0) for t in query_tokens)
            scores.append(score)
        return scores


# Singleton
retriever = BM25Retriever()
