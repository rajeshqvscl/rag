"""Migration script to add enhanced classification columns to EmailReply table"""
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
print("Email Reply Enhanced Classification Migration")
print("="*60)
print(f"Database: {DATABASE_URL.split('@')[0].split(':')[0]}:*****")

try:
    with engine.connect() as conn:
        # Check if email_replies table exists
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'email_replies'
        """))
        
        if not result.fetchone():
            print("\n⚠ email_replies table does not exist yet")
            print("Run migrate_email_replies.py first")
            sys.exit(0)
        
        # Check which columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'email_replies'
        """))
        existing_columns = {row[0] for row in result.fetchall()}
        
        new_columns = []
        
        # Add new columns if they don't exist
        if 'sender_confidence' not in existing_columns:
            print("\nAdding sender_confidence column...")
            conn.execute(text("ALTER TABLE email_replies ADD COLUMN sender_confidence FLOAT DEFAULT 0.0"))
            new_columns.append('sender_confidence')
        
        if 'combined_confidence' not in existing_columns:
            print("Adding combined_confidence column...")
            conn.execute(text("ALTER TABLE email_replies ADD COLUMN combined_confidence FLOAT DEFAULT 0.0"))
            new_columns.append('combined_confidence')
        
        if 'classification_method' not in existing_columns:
            print("Adding classification_method column...")
            conn.execute(text("ALTER TABLE email_replies ADD COLUMN classification_method VARCHAR"))
            new_columns.append('classification_method')
        
        if 'is_claude_identified' not in existing_columns:
            print("Adding is_claude_identified column...")
            conn.execute(text("ALTER TABLE email_replies ADD COLUMN is_claude_identified BOOLEAN DEFAULT FALSE"))
            new_columns.append('is_claude_identified')
        
        if 'claude_analysis' not in existing_columns:
            print("Adding claude_analysis column...")
            conn.execute(text("ALTER TABLE email_replies ADD COLUMN claude_analysis JSONB"))
            new_columns.append('claude_analysis')
        
        if 'classification_reasoning' not in existing_columns:
            print("Adding classification_reasoning column...")
            conn.execute(text("ALTER TABLE email_replies ADD COLUMN classification_reasoning TEXT"))
            new_columns.append('classification_reasoning')
        
        conn.commit()
        
        if new_columns:
            print(f"\n✓ Added {len(new_columns)} new columns:")
            for col in new_columns:
                print(f"  - {col}")
        else:
            print("\n✓ All columns already exist")
        
    print("\n" + "="*60)
    print("Migration completed!")
    print("="*60)
    print("\nEmail replies now support:")
    print("  - Claude AI-powered sender identification")
    print("  - Enhanced confidence scoring")
    print("  - Classification method tracking")
    print("  - AI reasoning and analysis storage")
    
except Exception as e:
    print(f"\n✗ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
