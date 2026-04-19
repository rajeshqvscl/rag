"""Migration script to add analysis and email_draft columns to PitchDeck table"""
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
print("Pitch Deck Analysis & Email Draft Migration")
print("="*60)
print(f"Database: {DATABASE_URL.split('@')[0].split(':')[0]}:*****")

try:
    with engine.connect() as conn:
        # Check if pitch_decks table exists
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'pitch_decks'
        """))
        
        if not result.fetchone():
            print("\n⚠ pitch_decks table does not exist yet")
            print("Run migrate_pitch_decks.py first")
            sys.exit(0)
        
        # Check which columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'pitch_decks'
        """))
        existing_columns = {row[0] for row in result.fetchall()}
        
        new_columns = []
        
        # Add new columns if they don't exist
        if 'analysis' not in existing_columns:
            print("\nAdding analysis column...")
            conn.execute(text("ALTER TABLE pitch_decks ADD COLUMN analysis TEXT"))
            new_columns.append('analysis')
        
        if 'email_draft' not in existing_columns:
            print("Adding email_draft column...")
            conn.execute(text("ALTER TABLE pitch_decks ADD COLUMN email_draft TEXT"))
            new_columns.append('email_draft')
        
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
    print("\nPitch decks now support:")
    print("  - AI-generated investment analysis")
    print("  - AI-generated outreach email drafts")
    
except Exception as e:
    print(f"\n✗ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
