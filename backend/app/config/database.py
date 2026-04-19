"""
Database configuration and connection management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finrag.db")

# Log database type (without exposing credentials)
if "neon.tech" in DATABASE_URL:
    print("Using Neon PostgreSQL Database (Cloud)")
elif DATABASE_URL.startswith("postgresql"):
    print("Using PostgreSQL Database")
elif DATABASE_URL.startswith("sqlite"):
    print("Using SQLite Database (Local)")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=True
    )
else:
    # PostgreSQL with connection pooling for cloud databases like Neon
    engine = create_engine(
        DATABASE_URL,
        echo=True,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=300,    # Recycle connections after 5 minutes
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define Base here to avoid circular imports
Base = declarative_base()

def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    print("Database: Initializing tables...")
    # Import models here to ensure they're registered with Base
    from app.models import database
    print(f"Database: Creating tables on {engine.url.render_as_string(hide_password=True)}...")
    Base.metadata.create_all(bind=engine)
    print("Database: Initialization complete.")
