"""
Database models for PostgreSQL migration
"""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

Base = declarative_base()

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
    embedding = Column(JSON)  # Store embedding as JSON array
    vector_id = Column(Integer)  # Reference to vector index
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="memories")
    conversation = relationship("Conversation", back_populates="memories")

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

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/finrag")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    Base.metadata.create_all(bind=engine)
