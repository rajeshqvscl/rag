"""Migration script to add PitchDeck table"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app.config.database import engine, DATABASE_URL
from sqlalchemy import text

print("="*60)
print("Pitch Deck Table Migration")
print("="*60)
print(f"Database: {DATABASE_URL.split('@')[0].split(':')[0]}:*****")

try:
    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'pitch_decks'
        """))
        
        if result.fetchone():
            print("\n✓ Pitch decks table already exists")
            sys.exit(0)
        
        # Create pitch_decks table
        print("\nCreating pitch_decks table...")
        conn.execute(text("""
            CREATE TABLE pitch_decks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                company_name VARCHAR NOT NULL,
                company_website VARCHAR,
                industry VARCHAR,
                stage VARCHAR,
                location VARCHAR,
                funding_stage VARCHAR,
                funding_amount VARCHAR,
                funding_currency VARCHAR DEFAULT 'USD',
                valuation VARCHAR,
                file_name VARCHAR NOT NULL,
                file_path VARCHAR NOT NULL,
                file_size INTEGER,
                file_type VARCHAR DEFAULT 'application/pdf',
                pdf_pages INTEGER,
                extracted_text TEXT,
                summary TEXT,
                key_metrics JSONB DEFAULT '{}',
                founders JSONB DEFAULT '[]',
                team_size INTEGER,
                status VARCHAR DEFAULT 'new',
                priority VARCHAR DEFAULT 'medium',
                rating FLOAT,
                tags JSONB DEFAULT '[]',
                notes TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                last_viewed_at TIMESTAMP
            )
        """))
        
        # Create indexes
        print("Creating indexes...")
        conn.execute(text("CREATE INDEX idx_pitch_decks_company ON pitch_decks(company_name)"))
        conn.execute(text("CREATE INDEX idx_pitch_decks_industry ON pitch_decks(industry)"))
        conn.execute(text("CREATE INDEX idx_pitch_decks_stage ON pitch_decks(stage)"))
        conn.execute(text("CREATE INDEX idx_pitch_decks_status ON pitch_decks(status)"))
        conn.execute(text("CREATE INDEX idx_pitch_decks_priority ON pitch_decks(priority)"))
        
        conn.commit()
        print("✓ Pitch decks table created successfully")
        print("✓ Indexes created")
        
    print("\n" + "="*60)
    print("Migration completed!")
    print("="*60)
    print("\nYou can now:")
    print("  1. POST /pitch-decks/upload - Upload PDF pitch decks")
    print("  2. GET /pitch-decks - List all pitch decks")
    print("  3. GET /pitch-decks/{id}/download - Download PDF")
    print("  4. POST /pitch-decks/{id}/status - Update review status")
    
except Exception as e:
    print(f"\n✗ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
