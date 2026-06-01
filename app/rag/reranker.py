"""
Cross-Encoder Reranking for improved retrieval accuracy
"""
import requests
import os
from dotenv import load_dotenv
from typing import List, Dict, Tuple

load_dotenv()

JINA_API_KEY = os.getenv("JINA_API_KEY")

RERANK_URL = "https://api.jina.ai/v1/rerank"


class CrossEncoderReranker:
    """
    Cross-encoder reranking using Jina's rerank API
    Improves retrieval precision by reordering results based on semantic relevance
    """

    def __init__(self, model: str = "jina-reranker-v2-base-multilingual"):
        self.model = model
        self.cache = {}

    def rerank(self, query: str, documents: List[str], top_k: int = 10,
               return_documents: bool = True, namespace: str = "") -> List[Dict]:
        """
        Rerank documents using cross-encoder

        Args:
            query: Search query
            documents: List of document texts to rerank
            top_k: Number of top results to return
            return_documents: Include document text in results
            namespace: Namespace for cache isolation (REQUIRED to prevent cross-doc contamination)

        Returns:
            List of dicts with rank, text, score, and index
        """
        if not documents:
            return []

        # More unique cache key: include namespace, query, doc count, AND first doc hash
        # This prevents contamination between different namespaces/documents
        import hashlib
        first_doc_hash = hashlib.md5(documents[0].encode()).hexdigest()[:8] if documents else ""
        cache_key = f"{namespace or 'none'}:{query[:50]}:{len(documents)}:{first_doc_hash}"
        
        if cache_key in self.cache:
            return self.cache[cache_key][:top_k]

        try:
            headers = {
                "Authorization": f"Bearer {JINA_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_k,
                "return_documents": return_documents
            }

            import time
            max_retries = 3
            backoff_factor = 2
            response = None
            
            for attempt in range(max_retries):
                try:
                    response = requests.post(RERANK_URL, headers=headers, json=payload, timeout=60)
                    if response.status_code == 429:
                        sleep_time = backoff_factor ** attempt
                        print(f"[RERANK] Rate limit or concurrency limit hit (429), retrying in {sleep_time}s (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(sleep_time)
                        continue
                    break
                except Exception as req_err:
                    if attempt == max_retries - 1:
                        raise req_err
                    sleep_time = backoff_factor ** attempt
                    print(f"[RERANK] Connection error: {req_err}, retrying in {sleep_time}s...")
                    time.sleep(sleep_time)

            if response is None or response.status_code != 200:
                err_msg = response.text if response is not None else "No response"
                print(f"[RERANK] API Error: {err_msg}")
                return self._fallback_rerank(documents, top_k)

            data = response.json()
            results = []

            for idx, result in enumerate(data.get("results", [])):
                if isinstance(result, str):
                    result = {"document": {"text": result}}
                doc = result.get("document", result)
                doc_text = doc.get("text", "") if isinstance(doc, dict) else str(doc)
                results.append({
                    "rank": idx + 1,
                    "text": result.get("text", doc_text),
                    "score": result.get("relevance_score", result.get("score", 0)),
                    "index": result.get("index", -1),
                    "model": self.model
                })

            self.cache[cache_key] = results
            return results[:top_k]

        except Exception as e:
            print(f"[RERANK] Error: {e}")
            return self._fallback_rerank(documents, top_k)

    def _fallback_rerank(self, documents: List[str], top_k: int) -> List[Dict]:
        """Fallback when API fails - return documents with uniform scores"""
        return [{
            "rank": i + 1,
            "text": doc,
            "score": 1.0 / (i + 1),
            "index": i,
            "model": "fallback"
        } for i, doc in enumerate(documents[:top_k])]

    def clear_cache(self):
        self.cache = {}


class SimpleReranker:
    """
    Simple keyword-based reranking without API dependency
    Useful when rerank API is unavailable
    """

    @staticmethod
    def rerank(query: str, documents: List[str], top_k: int = 10) -> List[Dict]:
        """
        Rerank documents based on keyword overlap and position

        Args:
            query: Search query
            documents: List of document texts
            top_k: Number of results to return

        Returns:
            List of dicts with rank, text, score, index
        """
        if not documents:
            return []

        query_terms = set(query.lower().split())

        scored = []
        for idx, doc in enumerate(documents):
            doc_lower = doc.lower()

            score = 0.0

            query_word_count = len(query_terms)
            doc_word_count = len(set(doc_lower.split()))

            matching_terms = query_terms.intersection(set(doc_lower.split()))
            term_overlap = len(matching_terms) / query_word_count if query_word_count > 0 else 0
            score += term_overlap * 0.6

            exact_matches = doc_lower.count(query.lower())
            score += min(exact_matches * 0.1, 0.3)

            for i, term in enumerate(query_terms):
                if term in doc_lower:
                    first_pos = doc_lower.find(term)
                    position_score = 1.0 / (first_pos + 1) if first_pos >= 0 else 0
                    score += position_score * 0.1

            scored.append({
                "rank": 0,
                "text": doc,
                "score": round(score, 4),
                "index": idx,
                "model": "simple_reranker"
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        for i, item in enumerate(scored[:top_k]):
            item["rank"] = i + 1

        return scored[:top_k]


class EnsembleReranker:
    """
    Ensemble reranking combining multiple signals:
    - Cross-encoder scores
    - Keyword matching
    - Position bias
    - Length normalization
    """

    def __init__(self):
        self.cross_encoder = CrossEncoderReranker()
        self.simple_reranker = SimpleReranker()
        self.use_cross_encoder = JINA_API_KEY is not None

    def rerank(self, query: str, documents: List[str], top_k: int = 10,
               weights: Dict[str, float] = None, namespace: str = "") -> List[Dict]:
        """
        Ensemble reranking with weighted combination

        Args:
            query: Search query
            documents: List of documents
            top_k: Number of results
            weights: Custom weights for scoring components
            namespace: Namespace for cache isolation

        Returns:
            Reranked documents with ensemble scores
        """
        if weights is None:
            weights = {
                "cross_encoder": 0.6,
                "keyword": 0.3,
                "position": 0.1
            }

        if len(documents) <= 1:
            return [{
                "rank": 1,

                "text": doc,
                "score": 1.0,
                "index": i,
                "model": "single"
            } for i, doc in enumerate(documents)]

        scores = {i: {"ensemble": 0.0, "details": {}} for i in range(len(documents))}

        if self.use_cross_encoder and weights.get("cross_encoder", 0) > 0:
            try:
                ce_results = self.cross_encoder.rerank(query, documents, top_k=len(documents), namespace=namespace)
                for result in ce_results:
                    idx = result["index"]
                    scores[idx]["details"]["cross_encoder"] = result["score"]
                    scores[idx]["ensemble"] += weights["cross_encoder"] * result["score"]
            except Exception as e:
                print(f"[ENSEMBLE] Cross-encoder failed: {e}")

        simple_results = self.simple_reranker.rerank(query, documents, top_k=len(documents))
        for result in simple_results:
            idx = result["index"]
            scores[idx]["details"]["keyword"] = result["score"]
            scores[idx]["ensemble"] += weights["keyword"] * result["score"]

        sorted_results = sorted(scores.items(), key=lambda x: x[1]["ensemble"], reverse=True)

        results = []
        for rank, (idx, score_data) in enumerate(sorted_results[:top_k], 1):
            results.append({
                "rank": rank,
                "text": documents[idx],
                "score": round(score_data["ensemble"], 4),
                "index": idx,
                "details": score_data["details"],
                "model": "ensemble"
            })

        return results


def rerank_documents(query: str, documents: List[str], top_k: int = 10,
                     method: str = "ensemble", namespace: str = "") -> List[Dict]:
    """
    Convenience function for reranking

    Args:
        query: Search query
        documents: List of document texts (or dicts with "text" key)
        top_k: Number of results to return
        method: "cross_encoder", "simple", or "ensemble"
        namespace: Namespace for cache isolation

    Returns:
        Reranked documents
    """
    # Normalize: accept both strings and dicts
    normalized_docs = []
    for doc in documents:
        if isinstance(doc, str):
            normalized_docs.append(doc)
        elif isinstance(doc, dict):
            normalized_docs.append(doc.get("text", str(doc)))
        else:
            normalized_docs.append(str(doc))
    
    documents = normalized_docs

    if method == "cross_encoder":
        reranker = CrossEncoderReranker()
        results = reranker.rerank(query, documents, top_k, namespace=namespace)
    elif method == "simple":
        reranker = SimpleReranker()
        results = reranker.rerank(query, documents, top_k)
    else:
        reranker = EnsembleReranker()
        results = reranker.rerank(query, documents, top_k, namespace=namespace)

    return results


def get_retrieval_stats(results: List[Dict]) -> Dict:
    """
    Get retrieval statistics for evaluation
    """
    if not results:
        return {
            "count": 0,
            "avg_score": 0,
            "max_score": 0,
            "min_score": 0,
            "score_std": 0
        }

    # Normalize: handle both string items and dict items
    normalized_results = []
    for r in results:
        if isinstance(r, dict):
            normalized_results.append(r)
        elif isinstance(r, str):
            normalized_results.append({"text": r, "score": 0})
        else:
            normalized_results.append({"score": 0})

    scores = [r.get("score", 0) for r in normalized_results]
    import statistics

    return {
        "count": len(normalized_results),
        "avg_score": round(statistics.mean(scores), 4),
        "max_score": round(max(scores), 4),
        "min_score": round(min(scores), 4),
        "score_std": round(statistics.stdev(scores) if len(scores) > 1 else 0, 4)
    }