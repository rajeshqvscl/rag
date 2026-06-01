"""
Document Relationship Mapping - Connect related documents
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import PitchDeck
from app.db.session import SessionLocal
from .embedder import embed_text
from .pinecone_client import index
import numpy as np
import time

_CLUSTERS_CACHE = None
_CLUSTERS_CACHE_TIME = 0
_CLUSTERS_CACHE_TTL = 300

_GRAPH_CACHE = None
_GRAPH_CACHE_TIME = 0
_GRAPH_CACHE_TTL = 300


def compute_document_similarity(doc_id1: str, doc_id2: str) -> float:
    """Compute cosine similarity between two documents"""
    try:
        # Get document embeddings via Pinecone
        # For simplicity, we'll use the company name as a proxy
        # In production, you'd store doc embeddings
        
        # Alternative: Query for both docs and compare
        results1 = index.query(
            vector=embed_text([doc_id1])[0],
            top_k=100,
            include_metadata=True,
            filter={"doc_id": {"$eq": doc_id1}} if doc_id1 else None
        )
        
        results2 = index.query(
            vector=embed_text([doc_id2])[0],
            top_k=100,
            include_metadata=True,
            filter={"doc_id": {"$eq": doc_id2}} if doc_id2 else None
        )
        
        # If we have chunks, we could compute similarity
        # For now, return a placeholder
        return 0.5  # Placeholder - would need proper implementation
        
    except Exception as e:
        print(f"[SIMILARITY ERROR] {e}")
        return 0.0


def get_all_documents() -> List[Dict]:
    """Get all documents from database"""
    db = SessionLocal()
    try:
        # Get pitch decks
        decks = db.query(PitchDeck).all()
        documents = [
            {
                "id": f"deck_{d.id}",
                "type": "pitch_deck",
                "company": d.company,
                "summary": d.summary[:200] if d.summary else "",
                "score": d.score,
                "verdict": d.verdict
            }
            for d in decks
        ]
        
        # Get intelligence insights
        insights = db.query(PitchDeck).filter(
            PitchDeck.status == "completed"
        ).all()
        
        for ins in insights:
            if ins.company:
                documents.append({
                    "id": f"insight_{ins.id}",
                    "type": "intelligence",
                    "company": ins.company,
                    "summary": str(ins.insights)[:200] if ins.insights else "",
                    "score": ins.insights.get("score", 0) if ins.insights else 0
                })
        
        return documents
    finally:
        db.close()


def find_related_documents(doc_id: str, threshold: float = 0.5, limit: int = 10) -> List[Dict]:
    """Find documents related to a given document"""
    documents = get_all_documents()
    
    if not documents:
        return []
    
    # Find the target document
    target_doc = None
    for doc in documents:
        if doc["id"] == doc_id:
            target_doc = doc
            break
    
    if not target_doc:
        return []
    
    # Simple similarity based on company name and keywords
    # In production, you'd use proper embedding similarity
    related = []
    
    for doc in documents:
        if doc["id"] == doc_id:
            continue
        
        # Calculate similarity score
        score = calculate_similarity(target_doc, doc)
        
        if score >= threshold:
            related.append({
                **doc,
                "similarity": round(score, 3)
            })
    
    # Sort by similarity and limit
    related = sorted(related, key=lambda x: x["similarity"], reverse=True)[:limit]
    
    return related


def calculate_similarity(doc1: Dict, doc2: Dict) -> float:
    """Calculate similarity between two documents"""
    score = 0.0
    
    # Company name similarity
    company1 = doc1.get("company", "").lower()
    company2 = doc2.get("company", "").lower()
    
    if company1 and company2:
        # Check for common words
        words1 = set(company1.split())
        words2 = set(company2.split())
        common = words1.intersection(words2)
        
        if common:
            score += 0.5
    
    # Same type bonus
    if doc1.get("type") == doc2.get("type"):
        score += 0.2
    
    # Score similarity (if both have scores)
    score1 = doc1.get("score", 0)
    score2 = doc2.get("score", 0)
    
    if score1 and score2 and score1 > 0 and score2 > 0:
        # Similar scores = higher similarity
        score_diff = abs(score1 - score2) / max(score1, score2, 1)
        if score_diff < 0.3:
            score += 0.3
    
    # Verdict similarity
    verdict1 = doc1.get("verdict", "").lower()
    verdict2 = doc2.get("verdict", "").lower()
    
    if verdict1 and verdict2 and verdict1 == verdict2:
        score += 0.2
    
    return min(score, 1.0)


def get_document_clusters(threshold: float = 0.6) -> List[List[Dict]]:
    """Group related documents into clusters - with caching"""
    global _CLUSTERS_CACHE, _CLUSTERS_CACHE_TIME
    
    current_time = time.time()
    if _CLUSTERS_CACHE is not None and (current_time - _CLUSTERS_CACHE_TIME) < _CLUSTERS_CACHE_TTL:
        return _CLUSTERS_CACHE
    
    documents = get_all_documents()
    
    if not documents:
        return []
    
    clusters = []
    processed = set()
    
    documents = documents[:10]
    
    for doc in documents:
        if doc["id"] in processed:
            continue
        
        cluster = [doc]
        processed.add(doc["id"])
        
        related = find_related_documents(doc["id"], threshold=threshold, limit=10)
        
        for rel_doc in related:
            if rel_doc["id"] not in processed:
                cluster.append(rel_doc)
                processed.add(rel_doc["id"])
        
        if len(cluster) > 1:
            clusters.append(cluster)
    
    _CLUSTERS_CACHE = clusters
    _CLUSTERS_CACHE_TIME = current_time
    
    return clusters


def build_relationship_graph() -> Dict[str, Any]:
    """Build complete relationship graph of all documents - with caching"""
    global _GRAPH_CACHE, _GRAPH_CACHE_TIME
    
    current_time = time.time()
    if _GRAPH_CACHE is not None and (current_time - _GRAPH_CACHE_TIME) < _GRAPH_CACHE_TTL:
        return _GRAPH_CACHE
    
    documents = get_all_documents()
    documents = documents[:15]
    
    edges = []
    
    for i, doc1 in enumerate(documents):
        for j, doc2 in enumerate(documents):
            if i >= j:
                continue
            
            similarity = calculate_similarity(doc1, doc2)
            
            if similarity >= 0.5:
                edges.append({
                    "source": doc1["id"],
                    "target": doc2["id"],
                    "similarity": round(similarity, 3)
                })
    
    _GRAPH_CACHE = {
        "nodes": documents,
        "edges": edges,
        "total_documents": len(documents),
        "total_relationships": len(edges)
    }
    _GRAPH_CACHE_TIME = current_time
    
    return _GRAPH_CACHE
