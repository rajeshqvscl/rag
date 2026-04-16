"""
Database models for PostgreSQL migration
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from app.utils.pgvector_type import Vector
from datetime import datetime
import os

# Import Base from config to avoid circular imports
from app.config.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # OAuth provider info
    oauth_provider = Column(String, nullable=True)  # 'google', 'github', etc.
    oauth_provider_id = Column(String, nullable=True)  # Provider's user ID
    
    # Relationships
    drafts = relationship("Draft", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    memories = relationship("Memory", back_populates="user")

class Draft(Base):
    __tablename__ = "drafts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company = Column(String, index=True, nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="Draft")
    confidence = Column(String, default="Medium")
    analysis = Column(Text)
    email_draft = Column(Text)
    revenue_data = Column(JSON)
    files = Column(JSON)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="drafts")

class Library(Base):
    __tablename__ = "library"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company = Column(String, index=True, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    file_type = Column(String)
    date_uploaded = Column(DateTime, default=datetime.utcnow)
    confidence = Column(String, default="High")
    tags = Column(JSON, default=list)
    file_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User")

class PitchDeck(Base):
    """Store pitch deck PDFs with metadata"""
    __tablename__ = "pitch_decks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Company information
    company_name = Column(String, index=True, nullable=False)
    company_website = Column(String)
    industry = Column(String, index=True)
    stage = Column(String, index=True)  # 'Pre-seed', 'Seed', 'Series A', 'Series B', etc.
    location = Column(String)
    
    # Funding information
    funding_stage = Column(String)
    funding_amount = Column(String)  # e.g., "$5M"
    funding_currency = Column(String, default="USD")
    valuation = Column(String)
    
    # File information
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)  # in bytes
    file_type = Column(String, default="application/pdf")
    pdf_pages = Column(Integer)
    
    # Pitch deck content (extracted text)
    extracted_text = Column(Text)
    summary = Column(Text)
    key_metrics = Column(JSON, default=dict)  # {'revenue': '$1M', 'growth': '50%', 'users': '10000'}
    revenue_data = Column(JSON, default=list)  # [{'year': '2024', 'revenue': 1000000}, ...] - extracted from graphs
    
    # AI-generated analysis and email draft
    analysis = Column(Text)  # Full investment analysis
    email_draft = Column(Text)  # Generated outreach email
    
    # Team information
    founders = Column(JSON, default=list)  # ['John Doe - CEO', 'Jane Smith - CTO']
    team_size = Column(Integer)
    
    # Status and tracking
    status = Column(String, default="new")  # 'new', 'reviewed', 'interested', 'passed', 'funded'
    priority = Column(String, default="medium")  # 'low', 'medium', 'high'
    rating = Column(Float)  # 1-10 rating
    tags = Column(JSON, default=list)
    notes = Column(Text)
    
    # Dates
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime)
    last_viewed_at = Column(DateTime)
    
    # Relationships
    user = relationship("User")


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    context = Column(Text)
    tags = Column(JSON, default=list)
    timestamp = Column(DateTime, default=datetime.utcnow)
    session_id = Column(String, index=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    memories = relationship("Memory", back_populates="conversation")

class Memory(Base):
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    text = Column(Text, nullable=False)
    embedding = Column(JSON)  # Store embedding as JSON array (fallback for non-PG)
    embedding_vector = Column(Vector(384))  # pgvector storage for similarity search
    vector_id = Column(Integer)  # Reference to FAISS index (optional)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="memories")
    conversation = relationship("Conversation", back_populates="memories")


class EmailReply(Base):
    """Store email replies from clients/investors with intent classification"""
    __tablename__ = "email_replies"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # Sender information
    sender_email = Column(String, index=True, nullable=False)
    sender_name = Column(String)
    sender_type = Column(String, default="unknown")  # 'client', 'investor', 'unknown'
    sender_confidence = Column(Float, default=0.0)  # Confidence in sender type identification
    
    # Email content
    subject = Column(String)
    body_text = Column(Text)
    body_html = Column(Text)
    
    # Intent classification
    intent_status = Column(String, default="pending")  # 'interested', 'not_interested', 'pending'
    intent_keywords = Column(JSON, default=list)  # ['not interested', 'interested', 'maybe', etc.]
    intent_confidence = Column(Float, default=0.0)  # 0.0 to 1.0
    combined_confidence = Column(Float, default=0.0)  # Combined sender + intent confidence
    
    # Classification method tracking
    classification_method = Column(String)  # 'claude_high_confidence', 'keyword_only', 'blended', etc.
    is_claude_identified = Column(Boolean, default=False)  # Whether Claude AI was used
    claude_analysis = Column(JSON)  # Full Claude analysis results
    classification_reasoning = Column(Text)  # Human-readable reasoning
    
    # Related deal/company
    company = Column(String, index=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"), nullable=True)
    
    # Email metadata
    received_at = Column(DateTime, default=datetime.utcnow)
    email_date = Column(DateTime)
    message_id = Column(String, unique=True)
    thread_id = Column(String, index=True)
    
    # Processing status
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    notes = Column(Text)
    
    # Relationships
    user = relationship("User")
    draft = relationship("Draft")

class Analytics(Base):
    __tablename__ = "analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_type = Column(String, index=True, nullable=False)
    event_data = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)
    session_id = Column(String, index=True)
    
    # Relationships
    user = relationship("User")

class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    key = Column(String, nullable=False)
    value = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
