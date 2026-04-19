"""
Migration script: Transfer data from SQLite (finrag.db) to Neon PostgreSQL
"""
import os
import sys
import json
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Verify DATABASE_URL is set
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or "neon.tech" not in DATABASE_URL:
    print("ERROR: Neon PostgreSQL DATABASE_URL not found in .env")
    print("Please ensure .env contains: DATABASE_URL=postgresql://...neon.tech/...")
    sys.exit(1)

print("="*60)
print("FinRAG Database Migration: SQLite → Neon PostgreSQL")
print("="*60)
print(f"Source: finrag.db (SQLite)")
print(f"Target: Neon PostgreSQL")
print("="*60)

# Connect to SQLite
import sqlite3
sqlite_conn = sqlite3.connect('finrag.db')
sqlite_conn.row_factory = sqlite3.Row
sqlite_cursor = sqlite_conn.cursor()

# Connect to PostgreSQL
import psycopg2
neon_conn = psycopg2.connect(DATABASE_URL)
neon_cursor = neon_conn.cursor()

# Get table list from SQLite
sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in sqlite_cursor.fetchall()]
print(f"\nFound tables in SQLite: {tables}")

# Track migration stats
migration_stats = {}

# Define table migration order (respecting foreign keys)
table_order = ['users', 'drafts', 'library', 'conversations', 'memories', 'analytics', 'settings']

# Filter to only existing tables
tables_to_migrate = [t for t in table_order if t in tables]
# Add any other tables not in our predefined list
for t in tables:
    if t not in tables_to_migrate and not t.startswith('sqlite_'):
        tables_to_migrate.append(t)

print(f"\nMigration order: {tables_to_migrate}")

def migrate_table(table_name):
    """Migrate a single table from SQLite to PostgreSQL"""
    print(f"\n{'='*40}")
    print(f"Migrating table: {table_name}")
    print('='*40)
    
    # Get SQLite schema
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = sqlite_cursor.fetchall()
    columns = [col[1] for col in columns_info]
    print(f"Columns: {columns}")
    
    # Get data from SQLite
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    
    if not rows:
        print(f"  No data to migrate")
        return 0
    
    print(f"  Found {len(rows)} rows to migrate")
    
    # Prepare insert statement
    placeholders = ','.join(['%s' for _ in columns])
    columns_str = ','.join(columns)
    
    # Handle ON CONFLICT for users table (avoid duplicate key errors)
    if table_name == 'users':
        insert_sql = f"""
            INSERT INTO {table_name} ({columns_str}) 
            VALUES ({placeholders})
            ON CONFLICT (id) DO UPDATE SET
            {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'id'])}
        """
    else:
        insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
    
    # Insert data into PostgreSQL
    inserted = 0
    errors = 0
    
    for row in rows:
        try:
            # Convert row to tuple, handling JSON and datetime fields
            values = []
            for i, value in enumerate(row):
                col_name = columns[i]
                # Handle JSON fields
                if isinstance(value, str) and (value.startswith('[') or value.startswith('{')):
                    try:
                        json.loads(value)  # Validate it's valid JSON
                        values.append(value)  # Keep as string for PostgreSQL JSON
                    except:
                        values.append(value)
                # Handle datetime strings
                elif isinstance(value, str) and 'T' in value and len(value) > 10:
                    try:
                        # Try to parse as ISO datetime
                        datetime.fromisoformat(value.replace('Z', '+00:00').replace('+00:00', ''))
                        values.append(value)
                    except:
                        values.append(value)
                else:
                    values.append(value)
            
            neon_cursor.execute(insert_sql, tuple(values))
            inserted += 1
            
            if inserted % 100 == 0:
                neon_conn.commit()
                print(f"  ... migrated {inserted} rows")
                
        except Exception as e:
            errors += 1
            if errors <= 5:  # Only show first 5 errors
                print(f"  Error inserting row: {e}")
                print(f"    Row data: {dict(zip(columns, row))}")
    
    neon_conn.commit()
    print(f"  ✓ Migrated {inserted} rows ({errors} errors)")
    return inserted

# Migrate each table
total_migrated = 0
for table in tables_to_migrate:
    try:
        count = migrate_table(table)
        migration_stats[table] = count
        total_migrated += count
    except Exception as e:
        print(f"  ✗ Failed to migrate {table}: {e}")
        migration_stats[table] = f"Error: {e}"

# Close connections
sqlite_conn.close()
neon_conn.close()

print("\n" + "="*60)
print("MIGRATION COMPLETE")
print("="*60)
print(f"\nMigration Summary:")
for table, count in migration_stats.items():
    if isinstance(count, int):
        print(f"  {table}: {count} rows migrated")
    else:
        print(f"  {table}: {count}")

print(f"\nTotal rows migrated: {total_migrated}")
print("="*60)
print("\nNext steps:")
print("1. Restart the backend to use Neon PostgreSQL")
print("2. Verify data at: http://localhost:9000/library")
print("3. Check drafts at: http://localhost:9000/drafts")
print("="*60)
