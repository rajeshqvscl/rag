"""
pgvector Memory Service
Advanced memory service using PostgreSQL pgvector for vector similarity search
"""
import os
import json
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.config.database import get_db, DATABASE_URL
from app.models.database import Conversation, Memory, User
from app.utils.pgvector_type import vector_distance, to_pgvector, from_pgvector


class PGVectorMemoryService:
    """Memory service using PostgreSQL pgvector for efficient similarity search"""
    
    def __init__(self):
        self.is_postgres = DATABASE_URL.startswith("postgresql")
        if not self.is_postgres:
            print("⚠ pgvector not available - using fallback to JSON/FAISS")
    
    def add_memory(self, query: str, response: str, 
                   context: str = "", user_id: int = 1, 
                   tags: List[str] = None) -> Dict:
        """Add a memory with vector embedding stored in pgvector"""
        db = next(get_db())
        
        try:
            # Get embedding
            from app.services.embeddings import get_embeddings
            combined_text = f"{query} {response}"
            embedding = get_embeddings([combined_text])[0]
            
            # Create conversation
            conversation = Conversation(
                user_id=user_id,
                query=query,
                response=response,
                context=context,
                tags=tags or [],
                timestamp=datetime.utcnow()
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            
            # Create memory with pgvector
            memory = Memory(
                user_id=user_id,
                conversation_id=conversation.id,
                text=combined_text,
                embedding=embedding.tolist(),  # JSON backup
                embedding_vector=embedding.tolist(),  # pgvector
                tags=tags or []
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)
            
            return {
                "memory_id": memory.id,
                "conversation_id": conversation.id,
                "embedding_stored": True,
                "vector_dimensions": len(embedding)
            }
            
        except Exception as e:
            db.rollback()
            print(f"Error adding memory: {e}")
            raise
        finally:
            db.close()
    
    def search_similar(self, query: str, k: int = 5, 
                       user_id: int = 1,
                       context_filter: str = None,
                       min_similarity: float = 0.7) -> List[Dict]:
        """Search for similar memories using pgvector cosine similarity"""
        
        if not self.is_postgres:
            # Fallback to FAISS-based search
            return self._fallback_search(query, k, user_id)
        
        db = next(get_db())
        
        try:
            # Get query embedding
            from app.services.embeddings import get_embeddings
            query_embedding = get_embeddings([query])[0]
            
            # Use pgvector for similarity search
            # cosine_distance returns 1 - cosine_similarity
            # So we filter for distance < 1 - min_similarity
            max_distance = 1 - min_similarity
            
            query_str = f"""
                SELECT 
                    m.id,
                    m.text,
                    m.tags,
                    m.created_at,
                    m.conversation_id,
                    cosine_distance(m.embedding_vector, :embedding) as distance,
                    1 - cosine_distance(m.embedding_vector, :embedding) as similarity
                FROM memories m
                WHERE m.user_id = :user_id
                AND cosine_distance(m.embedding_vector, :embedding) < :max_distance
                {f"AND m.context = :context_filter" if context_filter else ""}
                ORDER BY distance ASC
                LIMIT :limit
            """
            
            params = {
                "embedding": to_pgvector(query_embedding.tolist()),
                "user_id": user_id,
                "max_distance": max_distance,
                "limit": k
            }
            
            if context_filter:
                params["context_filter"] = context_filter
            
            result = db.execute(text(query_str), params)
            rows = result.fetchall()
            
            results = []
            for row in rows:
                # Get conversation details
                conversation = db.query(Conversation).filter(
                    Conversation.id == row.conversation_id
                ).first()
                
                results.append({
                    "memory_id": row.id,
                    "text": row.text,
                    "tags": row.tags,
                    "similarity": round(row.similarity, 4),
                    "distance": round(row.distance, 4),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "conversation": {
                        "query": conversation.query if conversation else "",
                        "response": conversation.response if conversation else "",
                        "context": conversation.context if conversation else ""
                    } if conversation else None
                })
            
            return results
            
        except Exception as e:
            print(f"Error in pgvector search: {e}")
            # Fallback to regular search
            return self._fallback_search(query, k, user_id)
        finally:
            db.close()
    
    def hybrid_search(self, query: str, k: int = 5,
                      keyword_weight: float = 0.3,
                      vector_weight: float = 0.7) -> List[Dict]:
        """Hybrid search combining keyword matching and vector similarity"""
        
        db = next(get_db())
        
        try:
            # Get query embedding
            from app.services.embeddings import get_embeddings
            query_embedding = get_embeddings([query])[0]
            query_lower = f"%{query.lower()}%"
            
            # Hybrid scoring: combines full-text search with vector similarity
            sql = f"""
                WITH keyword_matches AS (
                    SELECT 
                        m.id,
                        m.text,
                        m.tags,
                        m.conversation_id,
                        m.created_at,
                        CASE 
                            WHEN m.text ILIKE :query THEN 1.0
                            WHEN m.text ILIKE :query_partial THEN 0.5
                            ELSE 0.0
                        END as keyword_score
                    FROM memories m
                    WHERE m.text ILIKE :query_partial
                ),
                vector_matches AS (
                    SELECT 
                        m.id,
                        1 - cosine_distance(m.embedding_vector, :embedding) as vector_score
                    FROM memories m
                    WHERE cosine_distance(m.embedding_vector, :embedding) < 0.5
                )
                SELECT 
                    km.id,
                    km.text,
                    km.tags,
                    km.conversation_id,
                    km.created_at,
                    km.keyword_score,
                    COALESCE(vm.vector_score, 0) as vector_score,
                    ({keyword_weight} * km.keyword_score + 
                     {vector_weight} * COALESCE(vm.vector_score, 0)) as combined_score
                FROM keyword_matches km
                LEFT JOIN vector_matches vm ON km.id = vm.id
                ORDER BY combined_score DESC
                LIMIT :limit
            """
            
            result = db.execute(text(sql), {
                "query": query_lower,
                "query_partial": query_lower,
                "embedding": to_pgvector(query_embedding.tolist()),
                "limit": k
            })
            
            rows = result.fetchall()
            
            results = []
            for row in rows:
                conversation = db.query(Conversation).filter(
                    Conversation.id == row.conversation_id
                ).first()
                
                results.append({
                    "memory_id": row.id,
                    "text": row.text[:200] + "..." if len(row.text) > 200 else row.text,
                    "tags": row.tags,
                    "keyword_score": round(row.keyword_score, 3),
                    "vector_score": round(row.vector_score, 3),
                    "combined_score": round(row.combined_score, 3),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "conversation": {
                        "query": conversation.query if conversation else "",
                        "response": conversation.response if conversation else ""
                    } if conversation else None
                })
            
            return results
            
        except Exception as e:
            print(f"Error in hybrid search: {e}")
            return self._fallback_search(query, k)
        finally:
            db.close()
    
    def search_by_context(self, context_type: str, k: int = 10) -> List[Dict]:
        """Search memories by context type (company, deal, market, financial, general)"""
        db = next(get_db())
        
        try:
            memories = db.query(Memory).join(Conversation).filter(
                Conversation.context == context_type
            ).order_by(Memory.created_at.desc()).limit(k).all()
            
            return [
                {
                    "memory_id": m.id,
                    "text": m.text[:300] + "..." if len(m.text) > 300 else m.text,
                    "tags": m.tags,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "conversation": {
                        "query": m.conversation.query if m.conversation else "",
                        "response": m.conversation.response if m.conversation else ""
                    }
                }
                for m in memories
            ]
        finally:
            db.close()
    
    def get_memory_clusters(self, n_clusters: int = 5) -> List[Dict]:
        """Get clusters of similar memories using pgvector grouping"""
        db = next(get_db())
        
        try:
            # Get sample memories and find centroids
            # This is a simplified version - for production use actual clustering
            sql = """
                SELECT 
                    m.id,
                    m.text,
                    m.embedding_vector,
                    m.tags
                FROM memories m
                ORDER BY m.created_at DESC
                LIMIT 100
            """
            
            result = db.execute(text(sql))
            memories = result.fetchall()
            
            if not memories:
                return []
            
            # Group by tags as a simple clustering method
            clusters = {}
            for mem in memories:
                key_tags = tuple(sorted(mem.tags[:2])) if mem.tags else ("general",)
                if key_tags not in clusters:
                    clusters[key_tags] = {
                        "theme": key_tags,
                        "memories": [],
                        "count": 0
                    }
                clusters[key_tags]["memories"].append({
                    "id": mem.id,
                    "text": mem.text[:100] + "..."
                })
                clusters[key_tags]["count"] += 1
            
            # Return top clusters by size
            sorted_clusters = sorted(clusters.values(), key=lambda x: x["count"], reverse=True)
            return sorted_clusters[:n_clusters]
            
        except Exception as e:
            print(f"Error in clustering: {e}")
            return []
        finally:
            db.close()
    
    def vector_arithmetic(self, positive: List[str], negative: List[str] = None, k: int = 5) -> List[Dict]:
        """
        Vector arithmetic: positive - negative + ...
        Example: Apple + Innovation - Hardware = Software companies
        """
        if not self.is_postgres:
            return []
        
        db = next(get_db())
        
        try:
            from app.services.embeddings import get_embeddings
            
            # Get embeddings for positive terms
            pos_embeddings = get_embeddings(positive)
            result_vector = np.mean(pos_embeddings, axis=0)
            
            # Subtract negative terms
            if negative:
                neg_embeddings = get_embeddings(negative)
                result_vector -= np.mean(neg_embeddings, axis=0)
            
            # Search for closest vectors
            sql = """
                SELECT 
                    m.id,
                    m.text,
                    m.tags,
                    1 - cosine_distance(m.embedding_vector, :embedding) as similarity
                FROM memories m
                ORDER BY cosine_distance(m.embedding_vector, :embedding) ASC
                LIMIT :limit
            """
            
            result = db.execute(text(sql), {
                "embedding": to_pgvector(result_vector.tolist()),
                "limit": k
            })
            
            rows = result.fetchall()
            
            return [
                {
                    "memory_id": row.id,
                    "text": row.text[:150] + "..." if len(row.text) > 150 else row.text,
                    "tags": row.tags,
                    "similarity": round(row.similarity, 4)
                }
                for row in rows
            ]
            
        except Exception as e:
            print(f"Error in vector arithmetic: {e}")
            return []
        finally:
            db.close()
    
    def get_stats(self) -> Dict:
        """Get pgvector statistics"""
        if not self.is_postgres:
            return {"pgvector_available": False, "fallback_mode": True}
        
        db = next(get_db())
        
        try:
            # Check if pgvector extension is installed
            result = db.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
            pgvector_installed = result.fetchone() is not None
            
            # Get memory count
            total_memories = db.query(Memory).count()
            
            # Get memories with pgvector
            pgvector_memories = db.query(Memory).filter(
                Memory.embedding_vector.isnot(None)
            ).count()
            
            # Check indexes
            result = db.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'memories' AND indexname LIKE '%embedding%'
            """))
            indexes = [row[0] for row in result.fetchall()]
            
            return {
                "pgvector_available": pgvector_installed,
                "total_memories": total_memories,
                "pgvector_memories": pgvector_memories,
                "indexes": indexes,
                "database_type": "PostgreSQL with pgvector" if pgvector_installed else "PostgreSQL"
            }
            
        except Exception as e:
            return {
                "pgvector_available": False,
                "error": str(e)
            }
        finally:
            db.close()
    
    def _fallback_search(self, query: str, k: int, user_id: int = 1) -> List[Dict]:
        """Fallback search using FAISS when pgvector is not available"""
        from app.services.memory_service import memory_service
        
        results = memory_service.search_vectors(query, k, user_id)
        
        # Convert to consistent format
        return [
            {
                "memory_id": r.get("conversation", {}).get("id", 0),
                "text": r.get("conversation", {}).get("query", "") + " " + r.get("conversation", {}).get("response", ""),
                "similarity": 1 - r.get("distance", 0),
                "distance": r.get("distance", 0),
                "conversation": r.get("conversation")
            }
            for r in results
        ]


# Singleton instance
pgvector_memory_service = PGVectorMemoryService()
