from .pinecone_client import index
from .embedder import embed_text
from app.utils.text_utils import safe_lower

from typing import List, Dict, Any, Optional
import concurrent.futures

NEGATIVE_KEYWORDS = [
    "gtm", "sales strategy", "comparison vs",
    "financial projections", "ebitda projections"
]


def filter_chunks(chunks):
    filtered = []

    for c in chunks:
        c_lower = safe_lower(c)

        if any(nk in c_lower for nk in NEGATIVE_KEYWORDS):
            continue

        filtered.append(c)

    return filtered


def generate_queries(query, section=None):
    """Generate optimized single query per section to reduce latency"""
    base_queries = [query]

    investor_queries = {
        "financials": ["revenue growth ARR sales traction actuals INR Crore"],
        "tech": ["technology product platform AI solution IP patent"],
        "team": ["founder CEO CTO team IIT MDI IIM experience background"],
        "market": ["TAM SAM SOM market size opportunity growth addressable"],
        "funding": ["raising funding valuation round investment current raise"],
        "competition": ["competition competitor differentiation moat positioning"],
        "product": ["product technology platform AI copilot features solution"],
        "traction": ["traction milestones customers growth metrics adoption revenue"],
        "awards": ["award recognition certification achievement partner ecosystem"],
        "impact": ["impact sustainability ESG social metrics environmental carbon"]
    }

    if section and section in investor_queries:
        return investor_queries[section]

    return base_queries


def get_all_namespaces():
    """Get list of all namespaces in the index"""
    try:
        stats = index.describe_index_stats()
        namespaces = list(stats.get("namespaces", {}).keys())
        print(f"[DEBUG] Found {len(namespaces)} namespaces in index")
        return namespaces
    except Exception as e:
        print(f"[DEBUG] Error getting namespaces: {e}")
        return []


def retrieve(query: str, namespace: str = None, section: Optional[str] = None,
              doc_id: Optional[str] = None, domain: Optional[str] = None,
              top_k: int = 3, include_metadata: bool = False,
              use_reranking: bool = True) -> List[Any]:
    """
    Context-Aware Retrieval with Metadata Filtering and Reranking

    Args:
        query: Search query
        namespace: Specific namespace to search (default: search all)
        section: Filter by section (financials, tech, etc.)
        doc_id: Filter by document ID
        domain: Filter by domain
        top_k: Number of results (reduced to 3 for lower latency)
        include_metadata: Return metadata with results
        use_reranking: Use cross-encoder reranking for better precision

    Returns:
        If include_metadata=True: List of dicts with {text, score, doc_id, domain, section}
        Otherwise: List of strings (chunk texts)
    """
    print(f"\n[DEBUG] RETRIEVER CALLED")
    print(f"[DEBUG] Query: {query}")
    print(f"[DEBUG] Namespace: {namespace or 'ALL'}")
    print(f"[DEBUG] Section: {section}")
    print(f"[DEBUG] Doc ID Filter: {doc_id}")
    print(f"[DEBUG] Domain: {domain}")
    print(f"[DEBUG] top_k: {top_k}")
    print(f"[DEBUG] Include Metadata: {include_metadata}")
    print(f"[DEBUG] Use Reranking: {use_reranking}")

    queries = generate_queries(query, section)

    all_chunks = []
    chunk_scores = {}

    filter_dict = {}
    if doc_id:
        filter_dict["doc_id"] = doc_id

    if not namespace:
        raise ValueError(
            "retrieve() called without namespace — data contamination risk. "
            "Pass namespace=<company_name> to isolate company data."
        )
    from app.rag.vector_store import version_namespace
    versioned_ns = version_namespace(namespace)
    namespaces = [versioned_ns]

    print(f"[DEBUG] Searching namespaces: {namespaces}")
    print(f"[DEBUG] Using {len(queries)} query variants for {section or 'general'}")

    for ns in namespaces:
        try:
            batch_embeddings = embed_text(queries, namespace=namespace or "")
        except Exception as e:
            print(f"[DEBUG] Batch embedding failed: {e}")
            continue
        for q, query_embedding in zip(queries, batch_embeddings):
            try:
                results = index.query(
                    vector=query_embedding,
                    top_k=top_k,
                    include_metadata=True,
                    namespace=ns,
                    filter=filter_dict if filter_dict else None
                )

                matches = getattr(results, "matches", results.get("matches", []))
                print(f"[DEBUG] Namespace '{ns}', query '{q[:50]}...' returned {len(matches)} matches")

                for match in matches:
                    metadata = getattr(match, "metadata", match.get("metadata", {}))
                    score = getattr(match, "score", match.get("score", 0))

                    if metadata and "text" in metadata:
                        text = metadata["text"]
                        match_doc_id = metadata.get("doc_id")

                        if doc_id and match_doc_id != doc_id:
                            continue

                        if text in chunk_scores:
                            chunk_scores[text]["count"] += 1
                            chunk_scores[text]["score"] = max(chunk_scores[text]["score"], score)
                        else:
                            chunk_scores[text] = {
                                "count": 1,
                                "score": score,
                                "metadata": {
                                    "doc_id": match_doc_id or metadata.get("doc_id", "unknown"),
                                    "domain": metadata.get("domain", "general"),
                                    "section": metadata.get("section", "unknown"),
                                    "company": metadata.get("company", "Unknown"),
                                    "page": metadata.get("page", 0)
                                }
                            }

            except Exception as e:
                print(f"[DEBUG] Error querying namespace '{ns}': {e}")
                continue

    if not chunk_scores:
        print("[WARNING] No chunks retrieved from Pinecone")
        return [] if not include_metadata else []

    chunks_list = list(chunk_scores.keys())
    print(f"[DEBUG] Unique chunks before reranking: {len(chunks_list)}")

    # Sort chunks by raw retrieval score to assess similarity
    sorted_chunks_raw = sorted(chunk_scores.items(), key=lambda x: x[1]["score"], reverse=True)
    top_similarity = sorted_chunks_raw[0][1]["score"] if sorted_chunks_raw else 0.0

    # Skip reranking if similarity > 0.85, chunks count <= 5, or fast_mode is active
    should_skip_rerank = False
    try:
        from app.rag.pipeline_orchestrator import is_fast_mode
        if is_fast_mode():
            print("[RETRIEVER] Fast mode active: bypassing Jina Rerank completely")
            should_skip_rerank = True
    except Exception:
        pass

    if not should_skip_rerank:
        if len(chunks_list) <= 5:
            print(f"[RETRIEVER] Skipping reranking: unique chunks count ({len(chunks_list)}) is <= 5")
            should_skip_rerank = True
        elif top_similarity > 0.85:
            print(f"[RETRIEVER] Skipping reranking: top similarity ({top_similarity:.3f}) is > 0.85")
            should_skip_rerank = True

    if use_reranking and len(chunks_list) > 1 and not should_skip_rerank:
        try:
            from app.rag.reranker import rerank_documents, get_retrieval_stats

            reranked = rerank_documents(query, chunks_list, top_k=min(top_k, 3), namespace=namespace or "")
            stats = get_retrieval_stats(reranked)
            print(f"[DEBUG] Reranking stats: {stats}")

            if include_metadata:
                filtered = []
                for r in reranked:
                    chunk_text = r["text"]
                    meta = chunk_scores[chunk_text]["metadata"]
                    filtered.append({
                        "text": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                        "score": r["score"],
                        "doc_id": meta.get("doc_id", "unknown"),
                        "domain": meta.get("domain", "general"),
                        "section": meta.get("section", "unknown"),
                        "company": meta.get("company", "Unknown"),
                        "page": meta.get("page", 0),
                        "rerank_rank": r["rank"]
                    })
            else:
                filtered = [r["text"] for r in reranked]

        except Exception as e:
            print(f"[DEBUG] Reranking failed, using score-based ranking: {e}")
            sorted_chunks = sorted(chunk_scores.items(),
                                  key=lambda x: (x[1]["count"], x[1]["score"]),
                                  reverse=True)

            if include_metadata:
                filtered = []
                for chunk_text, data in sorted_chunks[:top_k]:
                    meta = data["metadata"]
                    filtered.append({
                        "text": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                        "score": data["score"],
                        "doc_id": meta.get("doc_id", "unknown"),
                        "domain": meta.get("domain", "general"),
                        "section": meta.get("section", "unknown"),
                        "company": meta.get("company", "Unknown"),
                        "page": meta.get("page", 0)
                    })
            else:
                filtered = [chunk_text for chunk_text, _ in sorted_chunks[:top_k]]
    else:
        sorted_chunks = sorted(chunk_scores.items(),
                              key=lambda x: (x[1]["count"], x[1]["score"]),
                              reverse=True)

        if include_metadata:
            filtered = []
            for chunk_text, data in sorted_chunks[:top_k]:
                meta = data["metadata"]
                filtered.append({
                    "text": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                    "score": data["score"],
                    "doc_id": meta.get("doc_id", "unknown"),
                    "domain": meta.get("domain", "general"),
                    "section": meta.get("section", "unknown"),
                    "company": meta.get("company", "Unknown"),
                    "page": meta.get("page", 0)
                })
        else:
            filtered = [chunk_text for chunk_text, _ in sorted_chunks[:top_k]]

    print(f"[DEBUG] Final chunks returned: {len(filtered)}\n")

    return filtered


def retrieve_with_sources(query: str, namespace: str = None, section: Optional[str] = None,
                          doc_id: Optional[str] = None, domain: Optional[str] = None,
                          top_k: int = 3) -> Dict[str, Any]:
    """
    Enhanced retrieval that returns chunks with source information for citations
    """
    results = retrieve(query, namespace, section, doc_id, domain, top_k, include_metadata=True)

    return {
        "chunks": [r["text"] for r in results],
        "sources": results,
        "count": len(results)
    }


def retrieve_hybrid(query: str, documents: List[str], top_k: int = 3,
                    section: Optional[str] = None) -> List[Dict]:
    """
    Hybrid retrieval combining keyword + semantic search on provided documents
    """
    if not documents:
        return []

    from app.rag.hybrid_retriever import HybridRetriever

    try:
        retriever = HybridRetriever()
        retriever.index_documents(documents)

        results = retriever.retrieve(query, top_k=top_k, section_filter=section)

        return results
    except Exception as e:
        print(f"[DEBUG] Hybrid retrieval failed: {e}")
        keyword_results = []
        from app.rag.hybrid_retriever import KeywordSearch
        searcher = KeywordSearch()
        exact_results = searcher.exact_search(query, documents)

        for idx, match_count in exact_results[:top_k]:
            keyword_results.append({
                "text": documents[idx][:300] + "..." if len(documents[idx]) > 300 else documents[idx],
                "score": match_count / 10.0,
                "method": "keyword"
            })

        return keyword_results


def retrieve_multiple_sections(sections: Dict[str, str], namespace: str,
                              doc_id: Optional[str] = None) -> Dict[str, List[Any]]:
    """
    Parallel retrieval for multiple sections to reduce latency.
    Runs all section retrievals concurrently.

    Args:
        sections: Dict of {section_name: query}
        namespace: Namespace to search in
        doc_id: Optional document ID filter

    Returns:
        Dict of {section_name: [results]}
    """
    results = {}

    def fetch_section(section_name: str, query: str):
        return section_name, retrieve(query, namespace=namespace, doc_id=doc_id, top_k=3)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sections)) as executor:
        futures = {executor.submit(fetch_section, name, query): name for name, query in sections.items()}

        for future in concurrent.futures.as_completed(futures):
            try:
                section_name, section_results = future.result()
                results[section_name] = section_results
            except Exception as e:
                print(f"[DEBUG] Section retrieval failed: {e}")
                results[futures[future]] = []

    return results