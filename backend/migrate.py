"""
Database migration script - adds missing columns to Neon PostgreSQL
Run from: backend/ directory
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

print(f"Connecting to database...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# All ALTER TABLE statements - IF NOT EXISTS ensures idempotency
migrations = [
    # pitch_decks missing columns
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS revenue_data JSONB",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS founders JSONB",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS team_size INTEGER",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS funding_stage VARCHAR",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS funding_amount VARCHAR",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS funding_currency VARCHAR DEFAULT 'USD'",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS valuation VARCHAR",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS company_website VARCHAR",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS location VARCHAR",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS rating FLOAT",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS tags JSONB",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS notes TEXT",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP",
    "ALTER TABLE pitch_decks ADD COLUMN IF NOT EXISTS last_viewed_at TIMESTAMP",
    # library missing column
    "ALTER TABLE library ADD COLUMN IF NOT EXISTS file_metadata JSONB",
    # users OAuth columns (may be missing in older schemas)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider_id VARCHAR",
]

success = 0
skipped = 0

for sql in migrations:
    try:
        cur.execute(sql)
        print(f"  OK: {sql[:70]}")
        success += 1
    except Exception as e:
        print(f"  SKIP ({e.__class__.__name__}): {sql[:60]}")
        skipped += 1
        conn.rollback()

conn.commit()
cur.close()
conn.close()
print(f"\nMigration complete! {success} applied, {skipped} skipped.")
