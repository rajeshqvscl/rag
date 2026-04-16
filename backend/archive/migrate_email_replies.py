"""Migration script to add EmailReply table"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from app.config.database import engine, DATABASE_URL
from sqlalchemy import text

print("="*60)
print("Email Reply Table Migration")
print("="*60)
print(f"Database: {DATABASE_URL.split('@')[0].split(':')[0]}:*****")

try:
    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'email_replies'
        """))
        
        if result.fetchone():
            print("\n✓ Email replies table already exists")
            sys.exit(0)
        
        # Create email_replies table
        print("\nCreating email_replies table...")
        conn.execute(text("""
            CREATE TABLE email_replies (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                sender_email VARCHAR NOT NULL,
                sender_name VARCHAR,
                sender_type VARCHAR DEFAULT 'unknown',
                subject VARCHAR,
                body_text TEXT,
                body_html TEXT,
                intent_status VARCHAR DEFAULT 'pending',
                intent_keywords JSONB DEFAULT '[]',
                intent_confidence FLOAT DEFAULT 0.0,
                company VARCHAR,
                draft_id INTEGER REFERENCES drafts(id),
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                email_date TIMESTAMP,
                message_id VARCHAR UNIQUE,
                thread_id VARCHAR,
                processed BOOLEAN DEFAULT FALSE,
                processed_at TIMESTAMP,
                notes TEXT
            )
        """))
        
        # Create indexes
        print("Creating indexes...")
        conn.execute(text("CREATE INDEX idx_email_replies_sender_email ON email_replies(sender_email)"))
        conn.execute(text("CREATE INDEX idx_email_replies_company ON email_replies(company)"))
        conn.execute(text("CREATE INDEX idx_email_replies_thread_id ON email_replies(thread_id)"))
        conn.execute(text("CREATE INDEX idx_email_replies_intent_status ON email_replies(intent_status)"))
        conn.execute(text("CREATE INDEX idx_email_replies_sender_type ON email_replies(sender_type)"))
        
        conn.commit()
        print("✓ Email replies table created successfully")
        print("✓ Indexes created")
        
    print("\n" + "="*60)
    print("Migration completed!")
    print("="*60)
    print("\nYou can now:")
    print("  1. POST /email-reply - Process incoming email replies")
    print("  2. GET /email-replies - View all replies with filtering")
    print("  3. GET /email-replies/stats - View reply statistics")
    
except Exception as e:
    print(f"\n✗ Migration failed: {e}")
    sys.exit(1)
