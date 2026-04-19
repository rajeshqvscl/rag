"""
Memory Service for managing conversation history and vector database
"""
import os
import json
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
import faiss
from sqlalchemy.orm import Session
from app.models.database import Conversation, Memory, User
from app.config.database import get_db

class MemoryService:
    def __init__(self):
        self.index_file = os.path.join(os.path.dirname(__file__), "../../data/memory_index.faiss")
        self.vector_index = None
        self.load_vector_index()
        
    def load_vector_index(self):
        """Load vector index if exists"""
        try:
            if os.path.exists(self.index_file):
                self.vector_index = faiss.read_index(self.index_file)
                print(f"Loaded vector index with {self.vector_index.ntotal} vectors")
        except Exception as e:
            print(f"Error loading vector index: {e}")
            self.vector_index = None
    
    def save_vector_index(self):
        """Save vector index to file"""
        try:
            if self.vector_index is not None:
                faiss.write_index(self.vector_index, self.index_file)
                print(f"Saved vector index with {self.vector_index.ntotal} vectors")
        except Exception as e:
            print(f"Error saving vector index: {e}")
    
    def add_conversation(self, query: str, response: str, context: str = "", user_id: int = 1, tags: List[str] = None):
        """Add conversation to memory"""
        db = next(get_db())
        try:
            conversation = Conversation(
                user_id=user_id,
                query=query,
                response=response,
                context=context,
                tags=tags or [],
                timestamp=datetime.utcnow(),
                session_id=f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            )
            db.add(conversation)
            db.commit()
            
            # Add to vector index
            from app.services.embeddings import get_embeddings
            embedding = get_embeddings([query + " " + response])[0]
            self.add_vector_to_index(conversation.id, query + " " + response, embedding)
            
            return conversation
        except Exception as e:
            db.rollback()
            print(f"Error adding conversation: {e}")
            raise
        finally:
            db.close()
    
    def get_conversations(self, limit: int = 10, user_id: int = 1) -> List[Dict]:
        """Get recent conversations"""
        db = next(get_db())
        try:
            conversations = db.query(Conversation).filter(
                Conversation.user_id == user_id
            ).order_by(Conversation.timestamp.desc()).limit(limit).all()
            
            return [
                {
                    "id": conv.id,
                    "timestamp": conv.timestamp.isoformat(),
                    "query": conv.query,
                    "response": conv.response,
                    "context": conv.context,
                    "tags": conv.tags or [],
                    "session_id": conv.session_id
                }
                for conv in conversations
            ]
        except Exception as e:
            print(f"Error getting conversations: {e}")
            return []
        finally:
            db.close()
    
    def search_conversations(self, query: str, user_id: int = 1) -> List[Dict]:
        """Search conversations by query"""
        db = next(get_db())
        try:
            conversations = db.query(Conversation).filter(
                Conversation.user_id == user_id
            ).filter(
                (Conversation.query.ilike(f"%{query}%")) | 
                (Conversation.response.ilike(f"%{query}%"))
            ).order_by(Conversation.timestamp.desc()).limit(5).all()
            
            return [
                {
                    "id": conv.id,
                    "timestamp": conv.timestamp.isoformat(),
                    "query": conv.query,
                    "response": conv.response,
                    "context": conv.context,
                    "tags": conv.tags or []
                }
                for conv in conversations
            ]
        except Exception as e:
            print(f"Error searching conversations: {e}")
            return []
        finally:
            db.close()
    
    def add_vector_to_index(self, conversation_id: int, text: str, embedding: np.ndarray):
        """Add vector to memory index"""
        if self.vector_index is None:
            # Initialize vector index
            dimension = embedding.shape[0] if embedding.ndim == 2 else embedding.shape[0]
            self.vector_index = faiss.IndexFlatL2(dimension)
        
        # Add vector to index
        self.vector_index.add(embedding.reshape(1, -1))
        
        # Save memory record
        db = next(get_db())
        try:
            memory = Memory(
                user_id=1,  # Default user for now
                conversation_id=conversation_id,
                text=text,
                embedding=embedding.tolist(),
                vector_id=self.vector_index.ntotal - 1,
                tags=[]
            )
            db.add(memory)
            db.commit()
            self.save_vector_index()
            print(f"Added vector to memory index. Total vectors: {self.vector_index.ntotal}")
        except Exception as e:
            db.rollback()
            print(f"Error adding vector to memory: {e}")
        finally:
            db.close()
    
    def search_vectors(self, query: str, k: int = 5, user_id: int = 1) -> List[Dict]:
        """Search for similar vectors"""
        if self.vector_index is None or self.vector_index.ntotal == 0:
            return []
        
        try:
            # Get query embedding
            from app.services.embeddings import get_embeddings
            query_embedding = get_embeddings([query])[0]
            
            # Search for similar vectors
            distances, indices = self.vector_index.search(query_embedding.reshape(1, -1), k)
            
            # Get corresponding conversations
            db = next(get_db())
            try:
                results = []
                for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                    if idx < self.vector_index.ntotal:
                        memory = db.query(Memory).filter(
                            Memory.vector_id == idx,
                            Memory.user_id == user_id
                        ).first()
                        
                        if memory and memory.conversation:
                            conv = memory.conversation
                            results.append({
                                "conversation": {
                                    "id": conv.id,
                                    "timestamp": conv.timestamp.isoformat(),
                                    "query": conv.query,
                                    "response": conv.response,
                                    "context": conv.context,
                                    "tags": conv.tags or []
                                },
                                "distance": float(dist),
                                "index": int(idx)
                            })
                
                return results
            finally:
                db.close()
        except Exception as e:
            print(f"Error searching vectors: {e}")
            return []
    
    def get_stats(self, user_id: int = 1) -> Dict:
        """Get memory statistics"""
        db = next(get_db())
        try:
            total_conversations = db.query(Conversation).filter(
                Conversation.user_id == user_id
            ).count()
            
            total_vectors = self.vector_index.ntotal if self.vector_index else 0
            
            return {
                "total_conversations": total_conversations,
                "total_vectors": total_vectors,
                "memory_file": self.index_file
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {"total_conversations": 0, "total_vectors": 0, "memory_file": self.index_file}
        finally:
            db.close()

# Global memory service instance
memory_service = MemoryService()
