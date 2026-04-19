"""
Migration script to add OAuth columns to User table
Run this after updating the database schema
"""
import os
import sys

# Load environment
from dotenv import load_dotenv
load_dotenv()

from app.config.database import engine, DATABASE_URL
from sqlalchemy import text

print("="*60)
print("OAuth Migration Script")
print("="*60)
print(f"Database: {DATABASE_URL.split('@')[0].split(':')[0]}:*****")

# Check if using PostgreSQL (Neon)
if not DATABASE_URL.startswith("postgresql"):
    print("\nWarning: This script is designed for PostgreSQL (Neon)")
    print("SQLite doesn't require ALTER TABLE for new columns")
    print("Your SQLite database should work without migration.")
    sys.exit(0)

try:
    # Connect and add columns
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('oauth_provider', 'oauth_provider_id')
        """))
        existing_columns = [row[0] for row in result]
        
        if 'oauth_provider' not in existing_columns:
            print("\nAdding 'oauth_provider' column...")
            conn.execute(text("ALTER TABLE users ADD COLUMN oauth_provider VARCHAR"))
            print("✓ Added oauth_provider")
        else:
            print("✓ oauth_provider already exists")
        
        if 'oauth_provider_id' not in existing_columns:
            print("\nAdding 'oauth_provider_id' column...")
            conn.execute(text("ALTER TABLE users ADD COLUMN oauth_provider_id VARCHAR"))
            print("✓ Added oauth_provider_id")
        else:
            print("✓ oauth_provider_id already exists")
        
        conn.commit()
    
    print("\n" + "="*60)
    print("Migration completed successfully!")
    print("="*60)
    print("\nYour database is now ready for OAuth authentication.")
    
except Exception as e:
    print(f"\n✗ Migration failed: {e}")
    print("\nIf columns already exist, you can ignore this error.")
    sys.exit(1)
