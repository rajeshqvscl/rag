"""
Advanced search service with hybrid search capabilities
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
from app.models.database import Draft, Library, Conversation, Memory, User
from app.config.database import get_db
from app.services.embeddings import get_embeddings
import numpy as np
import re

class SearchService:
    def __init__(self):
        self.embedding_cache = {}
        
    def get_or_create_default_user(self, db: Session) -> User:
        """Get or create default user"""
        user = db.query(User).filter_by(username="default").first()
        if not user:
            user = User(
                username="default",
                email="default@finrag.com",
                hashed_password="default",
                full_name="Default User"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    
    def preprocess_text(self, text: str) -> str:
        """Preprocess text for better search"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters but keep spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def keyword_search(self, query: str, search_type: str = "all", user_id: int = 1) -> List[Dict]:
        """Perform keyword search across different content types"""
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return []
            
            processed_query = self.preprocess_text(query)
            keywords = processed_query.split()
            
            results = []
            
            # Search drafts
            if search_type in ["all", "drafts"]:
                drafts = db.query(Draft).filter(Draft.user_id == user_id).filter(
                    or_(
                        Draft.company.ilike(f"%{query}%"),
                        Draft.analysis.ilike(f"%{query}%"),
                        Draft.email_draft.ilike(f"%{query}%")
                    )
                ).all()
                
                for draft in drafts:
                    results.append({
                        "type": "draft",
                        "id": draft.id,
                        "title": f"Draft: {draft.company}",
                        "content": draft.analysis or draft.email_draft or "",
                        "company": draft.company,
                        "date": draft.created_at.isoformat(),
                        "confidence": draft.confidence,
                        "score": self.calculate_keyword_score(processed_query, draft.company + " " + (draft.analysis or "") + " " + (draft.email_draft or ""))
                    })
            
            # Search library
            if search_type in ["all", "library"]:
                library = db.query(Library).filter(Library.user_id == user_id).filter(
                    or_(
                        Library.company.ilike(f"%{query}%"),
                        Library.file_name.ilike(f"%{query}%")
                    )
                ).all()
                
                for item in library:
                    results.append({
                        "type": "library",
                        "id": item.id,
                        "title": f"Library: {item.company}",
                        "content": f"{item.file_name} - {item.company}",
                        "company": item.company,
                        "date": item.date_uploaded.isoformat(),
                        "confidence": item.confidence,
                        "score": self.calculate_keyword_score(processed_query, item.company + " " + item.file_name)
                    })
            
            # Search conversations
            if search_type in ["all", "conversations"]:
                conversations = db.query(Conversation).filter(Conversation.user_id == user_id).filter(
                    or_(
                        Conversation.query.ilike(f"%{query}%"),
                        Conversation.response.ilike(f"%{query}%"),
                        Conversation.context.ilike(f"%{query}%")
                    )
                ).all()
                
                for conv in conversations:
                    results.append({
                        "type": "conversation",
                        "id": conv.id,
                        "title": f"Conversation: {conv.query[:50]}...",
                        "content": conv.query + " " + conv.response,
                        "company": "Conversation",
                        "date": conv.timestamp.isoformat(),
                        "confidence": "High",
                        "score": self.calculate_keyword_score(processed_query, conv.query + " " + conv.response)
                    })
            
            # Sort by score
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:50]  # Limit to 50 results
            
        finally:
            db.close()
    
    def semantic_search(self, query: str, search_type: str = "all", user_id: int = 1, k: int = 10) -> List[Dict]:
        """Perform semantic search using embeddings"""
        try:
            # Get query embedding
            query_embedding = get_embeddings([query])[0]
            
            db = next(get_db())
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return []
                
                results = []
                
                # Search memory vectors
                if search_type in ["all", "conversations"]:
                    memories = db.query(Memory).filter(Memory.user_id == user_id).all()
                    
                    if memories:
                        # Calculate similarities
                        similarities = []
                        for memory in memories:
                            if memory.embedding:
                                memory_embedding = np.array(memory.embedding)
                                similarity = np.dot(query_embedding, memory_embedding) / (
                                    np.linalg.norm(query_embedding) * np.linalg.norm(memory_embedding)
                                )
                                similarities.append((similarity, memory))
                        
                        # Sort by similarity
                        similarities.sort(key=lambda x: x[0], reverse=True)
                        
                        # Get top results
                        for similarity, memory in similarities[:k]:
                            if memory.conversation:
                                results.append({
                                    "type": "conversation",
                                    "id": memory.conversation.id,
                                    "title": f"Semantic Match: {memory.conversation.query[:50]}...",
                                    "content": memory.conversation.query + " " + memory.conversation.response,
                                    "company": "Conversation",
                                    "date": memory.conversation.timestamp.isoformat(),
                                    "confidence": "High",
                                    "score": float(similarity)
                                })
                
                return results
                
            finally:
                db.close()
                
        except Exception as e:
            print(f"Semantic search failed: {e}")
            return []
    
    def hybrid_search(self, query: str, search_type: str = "all", user_id: int = 1, k: int = 20) -> List[Dict]:
        """Perform hybrid search combining keyword and semantic search"""
        # Get keyword results
        keyword_results = self.keyword_search(query, search_type, user_id)
        
        # Get semantic results
        semantic_results = self.semantic_search(query, search_type, user_id, k)
        
        # Combine and deduplicate
        all_results = {}
        
        # Add keyword results
        for result in keyword_results:
            key = f"{result['type']}_{result['id']}"
            all_results[key] = result
        
        # Add semantic results (with higher weight)
        for result in semantic_results:
            key = f"{result['type']}_{result['id']}"
            if key in all_results:
                # Combine scores
                all_results[key]["score"] = (all_results[key]["score"] * 0.3 + result["score"] * 0.7)
            else:
                result["score"] = result["score"] * 0.7  # Weight semantic results higher
                all_results[key] = result
        
        # Sort by combined score
        combined_results = list(all_results.values())
        combined_results.sort(key=lambda x: x["score"], reverse=True)
        
        return combined_results[:k]
    
    def calculate_keyword_score(self, query: str, content: str) -> float:
        """Calculate keyword search score"""
        if not query or not content:
            return 0.0
        
        query_words = set(query.split())
        content_words = set(content.lower().split())
        
        # Calculate Jaccard similarity
        intersection = query_words.intersection(content_words)
        union = query_words.union(content_words)
        
        if not union:
            return 0.0
        
        jaccard_score = len(intersection) / len(union)
        
        # Bonus for exact matches
        exact_match_bonus = 0.0
        if query.lower() in content.lower():
            exact_match_bonus = 0.5
        
        return jaccard_score + exact_match_bonus
    
    def advanced_search(self, query: str, filters: Dict = None, search_type: str = "all", user_id: int = 1) -> List[Dict]:
        """Advanced search with filters"""
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return []
            
            results = []
            
            # Apply filters
            date_filter = None
            company_filter = None
            confidence_filter = None
            
            if filters:
                if "date_from" in filters:
                    date_filter = datetime.fromisoformat(filters["date_from"])
                if "company" in filters:
                    company_filter = filters["company"]
                if "confidence" in filters:
                    confidence_filter = filters["confidence"]
            
            # Search drafts with filters
            if search_type in ["all", "drafts"]:
                query_drafts = db.query(Draft).filter(Draft.user_id == user_id)
                
                # Apply text search
                query_drafts = query_drafts.filter(
                    or_(
                        Draft.company.ilike(f"%{query}%"),
                        Draft.analysis.ilike(f"%{query}%"),
                        Draft.email_draft.ilike(f"%{query}%")
                    )
                )
                
                # Apply filters
                if date_filter:
                    query_drafts = query_drafts.filter(Draft.created_at >= date_filter)
                if company_filter:
                    query_drafts = query_drafts.filter(Draft.company.ilike(f"%{company_filter}%"))
                if confidence_filter:
                    query_drafts = query_drafts.filter(Draft.confidence == confidence_filter)
                
                drafts = query_drafts.all()
                
                for draft in drafts:
                    results.append({
                        "type": "draft",
                        "id": draft.id,
                        "title": f"Draft: {draft.company}",
                        "content": draft.analysis or draft.email_draft or "",
                        "company": draft.company,
                        "date": draft.created_at.isoformat(),
                        "confidence": draft.confidence,
                        "score": self.calculate_keyword_score(query, draft.company + " " + (draft.analysis or "") + " " + (draft.email_draft or ""))
                    })
            
            # Similar filtering for other content types...
            
            # Sort by score
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:50]
            
        finally:
            db.close()
    
    def get_search_suggestions(self, query: str, user_id: int = 1) -> List[str]:
        """Get search suggestions based on partial query"""
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return []
            
            suggestions = set()
            
            # Get company names from drafts
            if len(query) > 2:
                drafts = db.query(Draft).filter(Draft.user_id == user_id).filter(
                    Draft.company.ilike(f"%{query}%")
                ).limit(10).all()
                
                for draft in drafts:
                    suggestions.add(draft.company)
            
            # Get file names from library
            library = db.query(Library).filter(Library.user_id == user_id).filter(
                Library.file_name.ilike(f"%{query}%")
            ).limit(10).all()
            
            for item in library:
                suggestions.add(item.file_name)
            
            return sorted(list(suggestions))[:10]
            
        finally:
            db.close()

# Global search service instance
search_service = SearchService()
