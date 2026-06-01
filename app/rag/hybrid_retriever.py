import re
import math
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
from .embedder import embed_text


class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths = []
        self.avg_doc_length = 0
        self.doc_freqs = {}
        self.idf = {}
        self.corpus_size = 0
        self.tokenized_corpus = []
    
    def index(self, documents: List[str]) -> None:
        """Build BM25 index from documents"""
        self.corpus_size = len(documents)
        self.tokenized_corpus = [self._tokenize(doc) for doc in documents]
        self.doc_lengths = [len(doc) for doc in self.tokenized_corpus]
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 1
        
        doc_freqs = Counter()
        for doc_tokens in self.tokenized_corpus:
            unique_tokens = set(doc_tokens)
            for token in unique_tokens:
                doc_freqs[token] += 1
        
        self.doc_freqs = dict(doc_freqs)
        
        for token, df in self.doc_freqs.items():
            self.idf[token] = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1)
    
    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r'\b\w+\b', text.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                     'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                     'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that',
                     'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
        return [t for t in tokens if t not in stop_words and len(t) > 2]
    
    def get_scores(self, query: str) -> List[float]:
        """Get BM25 scores for all documents"""
        query_tokens = self._tokenize(query)
        scores = []
        
        for i, doc_tokens in enumerate(self.tokenized_corpus):
            score = 0.0
            doc_len = self.doc_lengths[i]
            
            tf = Counter(doc_tokens)
            
            for token in query_tokens:
                if token not in self.idf:
                    continue
                
                token_tf = tf.get(token, 0)
                idf = self.idf[token]
                
                numerator = token_tf * (self.k1 + 1)
                denominator = token_tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_length)
                
                score += idf * (numerator / denominator)
            
            scores.append(score)
        
        return scores
    
    def get_top_k(self, query: str, k: int = 10) -> List[Tuple[int, float]]:
        """Get top-k documents with scores"""
        scores = self.get_scores(query)
        doc_scores = [(i, scores[i]) for i in range(len(scores))]
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        return doc_scores[:k]


class HybridRetriever:
    def __init__(self, dense_weight: float = 0.6, bm25_weight: float = 0.4):
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.bm25 = BM25Retriever()
        self.documents = []
        self.embeddings = []
    
    def index_documents(self, documents: List[str]) -> None:
        """Index documents for hybrid retrieval"""
        self.documents = documents
        
        self.bm25.index(documents)
        
        if documents:
            self.embeddings = embed_text(documents)
    
    def retrieve(self, query: str, top_k: int = 5, 
                 section_filter: Optional[str] = None,
                 doc_ids: List[str] = None) -> List[Dict]:
        """Hybrid retrieval combining dense + BM25"""
        bm25_scores = self.bm25.get_scores(query)
        
        query_embedding = embed_text([query])[0]
        
        dense_scores = []
        for emb in self.embeddings:
            sim = self._cosine_similarity(query_embedding, emb)
            dense_scores.append(sim)
        
        combined_scores = []
        for i in range(len(self.documents)):
            combined = (self.dense_weight * dense_scores[i]) + (self.bm25_weight * bm25_scores[i])
            combined_scores.append((i, combined))
        
        combined_scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        seen = set()
        
        for idx, score in combined_scores:
            if len(results) >= top_k:
                break
            
            doc_text = self.documents[idx]
            doc_hash = hash(doc_text)
            
            if doc_hash in seen:
                continue
            
            seen.add(doc_hash)
            
            result = {
                "text": doc_text[:300] + "..." if len(doc_text) > 300 else doc_text,
                "score": round(score, 4),
                "dense_score": round(dense_scores[idx], 4),
                "bm25_score": round(bm25_scores[idx], 4),
                "index": idx
            }
            
            results.append(result)
        
        return results
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def get_section_specific(self, query: str, section: str, top_k: int = 3) -> List[str]:
        """Get documents filtered by section keyword"""
        section_keywords = {
            "financials": ["revenue", "profit", "financial", "margin", "growth", "sales", "income"],
            "team": ["team", "founder", "ceo", "cto", "experience", "background"],
            "market": ["market", "tam", "sam", "opportunity", "industry", "size"],
            "product": ["product", "technology", "platform", "feature", "solution"],
            "traction": ["traction", "customers", "users", "growth", "adoption"],
            "competition": ["competition", "competitor", "advantage", "differentiation"]
        }
        
        keywords = section_keywords.get(section, [])
        
        filtered_docs = []
        for doc in self.documents:
            doc_lower = doc.lower()
            if any(kw in doc_lower for kw in keywords):
                filtered_docs.append(doc)
        
        if not filtered_docs:
            return self.retrieve(query, top_k)
        
        temp_bm25 = BM25Retriever()
        temp_bm25.index(filtered_docs)
        top_indices = temp_bm25.get_top_k(query, top_k)
        
        return [filtered_docs[i] for i, _ in top_indices]


class KeywordSearch:
    @staticmethod
    def exact_search(query: str, documents: List[str]) -> List[Tuple[int, int]]:
        """Find documents with exact phrase matches"""
        query_lower = query.lower()
        query_words = query_lower.split()
        
        results = []
        for i, doc in enumerate(documents):
            doc_lower = doc.lower()
            
            exact_count = doc_lower.count(query_lower)
            word_matches = sum(1 for w in query_words if w in doc_lower)
            
            if exact_count > 0 or word_matches >= len(query_words) * 0.8:
                results.append((i, exact_count + word_matches))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    @staticmethod
    def fuzzy_search(query: str, documents: List[str], threshold: float = 0.7) -> List[Tuple[int, float]]:
        """Fuzzy matching with Levenshtein distance"""
        query_words = query.lower().split()
        
        results = []
        for i, doc in enumerate(documents):
            doc_words = doc.lower().split()
            
            max_match = 0
            for qw in query_words:
                for dw in doc_words:
                    sim = KeywordSearch._levenshtein_similarity(qw, dw)
                    max_match = max(max_match, sim)
            
            if max_match >= threshold:
                results.append((i, max_match))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return KeywordSearch._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    @staticmethod
    def _levenshtein_similarity(s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        
        distance = KeywordSearch._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        
        return 1 - (distance / max_len)


def quick_keyword_search(query: str, documents: List[str]) -> List[str]:
    """Quick keyword search wrapper"""
    searcher = KeywordSearch()
    results = searcher.exact_search(query, documents)
    return [documents[i] for i, _ in results[:5]]