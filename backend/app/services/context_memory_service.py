"""
Context-Aware Memory Service
Enhanced memory system with intelligent context detection and retrieval
"""
import os
import json
import numpy as np
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import faiss
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.database import Conversation, Memory, User


@dataclass
class MemoryContext:
    """Represents the context of a memory"""
    context_type: str  # 'company', 'deal', 'market', 'financial', 'general'
    entities: List[str] = field(default_factory=list)  # ['Apple', 'Microsoft', 'Series A']
    topics: List[str] = field(default_factory=list)  # ['valuation', 'revenue', 'growth']
    sentiment: str = 'neutral'  # 'positive', 'negative', 'neutral'
    importance: float = 0.5  # 0.0 to 1.0
    expiration: Optional[datetime] = None  # When this memory becomes less relevant


class ContextAwareMemoryService:
    """Enhanced memory service with context awareness"""
    
    # Context type detection patterns
    CONTEXT_PATTERNS = {
        'company': [
            r'\b(company|corporation|inc\.?|llc|ltd\.?|corp\.?|enterprise|business|firm|startup)\b',
            r'\b(ceo|cto|cfo|founder|executive|management|team|employee)\b',
            r'\b(headquarters|office|location|region|market presence)\b'
        ],
        'deal': [
            r'\b(series\s+[a-d]|seed round|angel|venture capital|vc|funding|investment|investor)\b',
            r'\b(term sheet|due diligence|valuation|cap table|equity|stake|shares)\b',
            r'\b(acquisition|merger|ipo|exit|buyout|takeover)\b',
            r'\b(deal|transaction|negotiation|offer|proposal|partnership)\b'
        ],
        'market': [
            r'\b(market|industry|sector|segment|niche|vertical|competitor|competition)\b',
            r'\b(trend|growth|decline|opportunity|threat|swot|positioning)\b',
            r'\b(market share|penetration|adoption|demand|supply)\b'
        ],
        'financial': [
            r'\b(revenue|profit|loss|earnings|income|expense|cost|margin)\b',
            r'\b(ebitda|cash flow|balance sheet|income statement|p&l)\b',
            r'\b(million|billion|k|usd|\$|€|£|inr)\b',
            r'\b(growth rate|cagr|projection|forecast|budget)\b',
            r'\b(pe ratio|eps|roe|roi|npv|irr|wacc)\b'
        ]
    }
    
    # Topic extraction keywords
    TOPIC_KEYWORDS = {
        'valuation': ['valuation', 'worth', 'price', 'multiple', 'ev/ebitda', 'p/e'],
        'revenue': ['revenue', 'sales', 'top line', 'turnover', 'income'],
        'growth': ['growth', 'expansion', 'scaling', 'increase', 'upward'],
        'risk': ['risk', 'concern', 'challenge', 'issue', 'problem', 'threat'],
        'opportunity': ['opportunity', 'potential', 'prospect', 'advantage'],
        'team': ['team', 'founder', 'talent', 'hiring', 'retention', 'culture'],
        'product': ['product', 'technology', 'innovation', 'feature', 'roadmap'],
        'market': ['market', 'customer', 'user', 'adoption', 'demand']
    }
    
    def __init__(self):
        self.index_file = os.path.join(os.path.dirname(__file__), "../../data/context_memory_index.faiss")
        self.context_file = os.path.join(os.path.dirname(__file__), "../../data/memory_contexts.json")
        self.vector_index = None
        self.memory_contexts = {}  # memory_id -> MemoryContext
        self.context_indices = defaultdict(list)  # context_type -> [memory_ids]
        self.load_index()
        self.load_contexts()
    
    def load_index(self):
        """Load FAISS vector index"""
        try:
            if os.path.exists(self.index_file):
                self.vector_index = faiss.read_index(self.index_file)
                print(f"✓ Loaded context-aware memory index with {self.vector_index.ntotal} vectors")
        except Exception as e:
            print(f"⚠ Error loading memory index: {e}")
            self.vector_index = None
    
    def save_index(self):
        """Save FAISS vector index"""
        try:
            if self.vector_index is not None:
                faiss.write_index(self.vector_index, self.index_file)
        except Exception as e:
            print(f"✗ Error saving memory index: {e}")
    
    def load_contexts(self):
        """Load memory contexts from JSON"""
        try:
            if os.path.exists(self.context_file):
                with open(self.context_file, 'r') as f:
                    data = json.load(f)
                    for memory_id, ctx_data in data.items():
                        self.memory_contexts[int(memory_id)] = MemoryContext(**ctx_data)
                print(f"✓ Loaded {len(self.memory_contexts)} memory contexts")
        except Exception as e:
            print(f"⚠ Error loading contexts: {e}")
    
    def save_contexts(self):
        """Save memory contexts to JSON"""
        try:
            data = {
                str(k): {
                    'context_type': v.context_type,
                    'entities': v.entities,
                    'topics': v.topics,
                    'sentiment': v.sentiment,
                    'importance': v.importance,
                    'expiration': v.expiration.isoformat() if v.expiration else None
                }
                for k, v in self.memory_contexts.items()
            }
            with open(self.context_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"✗ Error saving contexts: {e}")
    
    def detect_context(self, text: str, metadata: Dict = None) -> MemoryContext:
        """Automatically detect context from text"""
        text_lower = text.lower()
        
        # Detect context type
        context_scores = {}
        for ctx_type, patterns in self.CONTEXT_PATTERNS.items():
            score = sum(1 for pattern in patterns if re.search(pattern, text_lower))
            context_scores[ctx_type] = score
        
        # Default to 'general' if no strong match
        if max(context_scores.values(), default=0) == 0:
            context_type = 'general'
        else:
            context_type = max(context_scores, key=context_scores.get)
        
        # Extract entities (capitalized words, quoted phrases)
        entities = []
        # Company names (Capitalized words)
        company_matches = re.findall(r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\b', text)
        entities.extend([e for e in company_matches if len(e) > 2])
        # Quoted phrases
        quoted = re.findall(r'"([^"]+)"', text)
        entities.extend(quoted)
        entities = list(set(entities))[:10]  # Limit to 10 unique entities
        
        # Extract topics
        topics = []
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                topics.append(topic)
        
        # Detect sentiment
        sentiment = self._detect_sentiment(text_lower)
        
        # Calculate importance based on multiple factors
        importance = self._calculate_importance(text, context_type, metadata)
        
        # Set expiration based on context type
        expiration = self._get_expiration(context_type)
        
        return MemoryContext(
            context_type=context_type,
            entities=entities,
            topics=topics,
            sentiment=sentiment,
            importance=importance,
            expiration=expiration
        )
    
    def _detect_sentiment(self, text: str) -> str:
        """Simple sentiment detection"""
        positive_words = ['good', 'great', 'excellent', 'positive', 'strong', 'growth', 'profit', 'success', 'opportunity', 'advantage']
        negative_words = ['bad', 'poor', 'negative', 'weak', 'decline', 'loss', 'risk', 'problem', 'concern', 'challenge']
        
        pos_count = sum(1 for w in positive_words if w in text)
        neg_count = sum(1 for w in negative_words if w in text)
        
        if pos_count > neg_count:
            return 'positive'
        elif neg_count > pos_count:
            return 'negative'
        return 'neutral'
    
    def _calculate_importance(self, text: str, context_type: str, metadata: Dict = None) -> float:
        """Calculate importance score (0.0 to 1.0)"""
        importance = 0.5  # Base importance
        
        # Financial numbers increase importance
        if re.search(r'\$\d+\s*(million|billion|m|b)?|\d+\s*(million|billion)\s*usd', text, re.IGNORECASE):
            importance += 0.2
        
        # Deal-related terms
        if context_type == 'deal':
            importance += 0.15
        
        # Executive names or key decisions
        if re.search(r'\b(ceo|cto|founder|board|decided|approved)\b', text, re.IGNORECASE):
            importance += 0.1
        
        # Length factor (more detailed = more important)
        if len(text) > 500:
            importance += 0.05
        
        # Metadata boost
        if metadata:
            if metadata.get('is_key_decision'):
                importance += 0.2
            if metadata.get('is_faq'):
                importance += 0.1
        
        return min(1.0, importance)
    
    def _get_expiration(self, context_type: str) -> Optional[datetime]:
        """Get expiration date based on context type"""
        now = datetime.utcnow()
        expiration_map = {
            'market': now + timedelta(days=30),  # Market info expires in 30 days
            'financial': now + timedelta(days=90),  # Financial info expires in 90 days
            'deal': now + timedelta(days=180),  # Deal info expires in 6 months
            'company': now + timedelta(days=365),  # Company info expires in 1 year
            'general': None  # No expiration
        }
        return expiration_map.get(context_type)
    
    def add_contextual_memory(self, query: str, response: str, 
                              metadata: Dict = None, user_id: int = 1) -> Dict:
        """Add a memory with automatic context detection"""
        db = next(get_db())
        
        try:
            # Detect context from combined text
            combined_text = f"{query} {response}"
            context = self.detect_context(combined_text, metadata)
            
            # Create conversation record
            conversation = Conversation(
                user_id=user_id,
                query=query,
                response=response,
                context=context.context_type,
                tags=context.entities + context.topics,
                timestamp=datetime.utcnow()
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            
            # Add to vector index
            from app.services.embeddings import get_embeddings
            embedding = get_embeddings([combined_text])[0]
            
            if self.vector_index is None:
                dimension = embedding.shape[0]
                self.vector_index = faiss.IndexFlatL2(dimension)
            
            self.vector_index.add(embedding.reshape(1, -1))
            vector_id = self.vector_index.ntotal - 1
            
            # Create memory record
            memory = Memory(
                user_id=user_id,
                conversation_id=conversation.id,
                text=combined_text,
                embedding=embedding.tolist(),
                vector_id=vector_id,
                tags=context.entities + context.topics
            )
            db.add(memory)
            db.commit()
            
            # Store context
            self.memory_contexts[memory.id] = context
            self.context_indices[context.context_type].append(memory.id)
            self.save_contexts()
            self.save_index()
            
            return {
                "memory_id": memory.id,
                "conversation_id": conversation.id,
                "context": {
                    "type": context.context_type,
                    "entities": context.entities,
                    "topics": context.topics,
                    "sentiment": context.sentiment,
                    "importance": context.importance,
                    "expiration": context.expiration.isoformat() if context.expiration else None
                },
                "status": "success"
            }
            
        except Exception as e:
            db.rollback()
            print(f"Error adding contextual memory: {e}")
            raise
        finally:
            db.close()
    
    def retrieve_contextual_memories(self, query: str, 
                                     context_filter: str = None,
                                     entity_filter: str = None,
                                     k: int = 5) -> List[Dict]:
        """Retrieve memories with context-aware ranking"""
        if self.vector_index is None or self.vector_index.ntotal == 0:
            return []
        
        try:
            # Get query embedding
            from app.services.embeddings import get_embeddings
            query_embedding = get_embeddings([query])[0]
            
            # Get query context for filtering
            query_context = self.detect_context(query)
            
            # Search in vector space
            distances, indices = self.vector_index.search(
                query_embedding.reshape(1, -1), 
                min(k * 3, self.vector_index.ntotal)  # Get more candidates
            )
            
            # Filter and rank by context relevance
            db = next(get_db())
            try:
                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    memory = db.query(Memory).filter(
                        Memory.vector_id == idx
                    ).first()
                    
                    if not memory or memory.id not in self.memory_contexts:
                        continue
                    
                    context = self.memory_contexts[memory.id]
                    
                    # Apply filters
                    if context_filter and context.context_type != context_filter:
                        continue
                    if entity_filter and entity_filter not in context.entities:
                        continue
                    
                    # Calculate context relevance score
                    relevance_score = self._calculate_relevance(
                        query_context, context, float(dist)
                    )
                    
                    results.append({
                        "memory_id": memory.id,
                        "conversation": {
                            "query": memory.conversation.query if memory.conversation else "",
                            "response": memory.conversation.response if memory.conversation else "",
                            "timestamp": memory.conversation.timestamp.isoformat() if memory.conversation else None
                        },
                        "context": {
                            "type": context.context_type,
                            "entities": context.entities,
                            "topics": context.topics,
                            "sentiment": context.sentiment,
                            "importance": context.importance
                        },
                        "relevance_score": relevance_score,
                        "vector_distance": float(dist)
                    })
                
                # Sort by relevance score
                results.sort(key=lambda x: x["relevance_score"], reverse=True)
                return results[:k]
                
            finally:
                db.close()
                
        except Exception as e:
            print(f"Error retrieving contextual memories: {e}")
            return []
    
    def _calculate_relevance(self, query_context: MemoryContext, 
                            memory_context: MemoryContext, 
                            vector_distance: float) -> float:
        """Calculate context-aware relevance score"""
        score = 1.0 / (1.0 + vector_distance)  # Base semantic similarity
        
        # Boost for matching context type
        if query_context.context_type == memory_context.context_type:
            score *= 1.3
        
        # Boost for matching entities
        common_entities = set(query_context.entities) & set(memory_context.entities)
        if common_entities:
            score *= (1 + len(common_entities) * 0.2)
        
        # Boost for matching topics
        common_topics = set(query_context.topics) & set(memory_context.topics)
        if common_topics:
            score *= (1 + len(common_topics) * 0.15)
        
        # Boost by importance
        score *= (0.5 + memory_context.importance)
        
        # Penalize expired memories
        if memory_context.expiration and datetime.utcnow() > memory_context.expiration:
            score *= 0.5
        
        return score
    
    def get_context_summary(self, context_type: str = None) -> Dict:
        """Get summary of memories by context"""
        summary = defaultdict(lambda: {
            "count": 0,
            "avg_importance": 0,
            "top_entities": [],
            "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0}
        })
        
        for memory_id, context in self.memory_contexts.items():
            key = context.context_type if not context_type else context_type
            
            summary[key]["count"] += 1
            summary[key]["avg_importance"] += context.importance
            summary[key]["top_entities"].extend(context.entities)
            summary[key]["sentiment_distribution"][context.sentiment] += 1
        
        # Calculate averages and get top entities
        result = {}
        for key, data in summary.items():
            if data["count"] > 0:
                data["avg_importance"] /= data["count"]
                # Get most common entities
                from collections import Counter
                entity_counts = Counter(data["top_entities"])
                data["top_entities"] = [e for e, _ in entity_counts.most_common(10)]
                result[key] = data
        
        return result
    
    def clean_expired_memories(self):
        """Remove or deprioritize expired memories"""
        now = datetime.utcnow()
        expired_ids = [
            mid for mid, ctx in self.memory_contexts.items()
            if ctx.expiration and now > ctx.expiration
        ]
        
        for mid in expired_ids:
            if mid in self.memory_contexts:
                self.memory_contexts[mid].importance *= 0.5  # Reduce importance
        
        self.save_contexts()
        return len(expired_ids)


# Global instance
context_memory_service = ContextAwareMemoryService()
