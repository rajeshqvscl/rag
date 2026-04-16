"""
Migration script to enable pgvector extension and update vector storage
Run this after updating the database schema to use pgvector
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finrag.db")

# Create engine directly (avoid circular imports)
if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300
    )

print("="*60)
print("pgvector Extension Migration")
print("="*60)
print(f"Database: {DATABASE_URL.split('@')[0].split(':')[0]}:*****")

# Check if using PostgreSQL (required for pgvector)
if not DATABASE_URL.startswith("postgresql"):
    print("\n⚠ Warning: pgvector requires PostgreSQL")
    print("Your database appears to be SQLite or other non-PostgreSQL")
    print("pgvector will only work with PostgreSQL (including Neon)")
    sys.exit(0)

try:
    with engine.connect() as conn:
        # Enable pgvector extension
        print("\nEnabling pgvector extension...")
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            print("✓ pgvector extension enabled")
        except Exception as e:
            print(f"⚠ Could not enable pgvector: {e}")
            print("Note: You may need to install pgvector on your PostgreSQL server")
            print("For Neon: pgvector is pre-installed ✓")
            print("For local PostgreSQL: Run 'CREATE EXTENSION vector' as superuser")
        
        # Check if vector extension is available
        result = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
        if not result.fetchone():
            print("\n✗ pgvector extension not available")
            print("Please install pgvector on your PostgreSQL server first")
            sys.exit(1)
        
        # Check if memories table exists
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'memories'
        """))
        
        if not result.fetchone():
            print("\n⚠ Memories table does not exist yet")
            print("It will be created with pgvector support when you start the app")
            sys.exit(0)
        
        # Check if embedding_vector column exists
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'memories' 
            AND column_name = 'embedding_vector'
        """))
        
        if result.fetchone():
            print("\n✓ embedding_vector column already exists")
        else:
            print("\nAdding embedding_vector column...")
            conn.execute(text("ALTER TABLE memories ADD COLUMN embedding_vector vector(384)"))
            conn.commit()
            print("✓ Added embedding_vector column (384 dimensions)")
        
        # Create HNSW index for fast similarity search
        print("\nCreating HNSW index for vector similarity search...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_memories_embedding_vector 
                ON memories USING hnsw (embedding_vector vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """))
            conn.commit()
            print("✓ Created HNSW index for fast similarity search")
        except Exception as e:
            conn.rollback()
            print(f"⚠ Could not create HNSW index: {e}")
            print("Trying with IVFFlat index instead...")
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_memories_embedding_vector 
                    ON memories USING ivfflat (embedding_vector vector_cosine_ops)
                    WITH (lists = 100)
                """))
                conn.commit()
                print("✓ Created IVFFlat index")
            except Exception as e2:
                conn.rollback()
                print(f"⚠ Could not create index: {e2}")
        
        # Create GIN index for context filtering
        print("\nCreating GIN index for context filtering...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_memories_context 
                ON memories USING GIN (tags)
            """))
            conn.commit()
            print("✓ Created GIN index on tags")
        except Exception as e:
            conn.rollback()
            print(f"⚠ Could not create GIN index: {e}")
        
        # Migrate existing embeddings from JSON to vector (if any)
        print("\nChecking for existing embeddings to migrate...")
        try:
            result = conn.execute(text("""
                SELECT id, embedding FROM memories 
                WHERE embedding IS NOT NULL 
                LIMIT 5
            """))
            rows = result.fetchall()
            
            if rows:
                print(f"Found {len(rows)} memories with embeddings")
                print("Note: Run 'python migrate_embeddings_to_pgvector.py' to migrate existing data to pgvector format")
            else:
                print("✓ No existing embeddings to migrate")
        except Exception as e:
            conn.rollback()
            print(f"⚠ Could not check existing embeddings: {e}")
        
    print("\n" + "="*60)
    print("pgvector Migration completed!")
    print("="*60)
    print("\n✓ pgvector is now ready for vector similarity search")
    print("\nNew features available:")
    print("  - Fast cosine similarity search")
    print("  - HNSW/IVFFlat approximate nearest neighbor search")
    print("  - Vector arithmetic and operations")
    print("  - Integration with SQL queries")
    
except Exception as e:
    print(f"\n✗ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
