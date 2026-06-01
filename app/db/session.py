from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "")
    DATABASE_URL = DATABASE_URL.replace("channel_binding=require", "")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=3,
    max_overflow=5,
    connect_args={"connect_timeout": 30}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Run migrations to add missing columns
def run_migrations():
    import traceback
    from sqlalchemy import text
    import time
    # Retry connection up to 3 times (DNS/network may not be ready at import time)
    for attempt in range(3):
        try:
            with engine.connect() as conn:
                # Add columns using IF NOT EXISTS to avoid errors
                migrations = [
                    ("client_reverts", "company VARCHAR"),
                    ("client_reverts", "type VARCHAR DEFAULT 'client'"),
                    ("client_reverts", "cheque_size VARCHAR"),
                    ("client_reverts", "sector VARCHAR"),
                    ("client_reverts", "status VARCHAR DEFAULT 'pending'"),
                    ("client_reverts", "processed_at TIMESTAMP"),
                    ("client_reverts", "document_path VARCHAR"),
                    ("client_reverts", "urgency_level VARCHAR"),
                    ("client_reverts", "query_type VARCHAR"),
                    ("client_reverts", "reasoning VARCHAR"),
                    ("client_reverts", "last_follow_up TIMESTAMP"),
                    ("client_reverts", "follow_up_count INT DEFAULT 0"),
                    ("client_reverts", "archived_at TIMESTAMP"),
                    ("client_reverts", "archived_reason VARCHAR"),
                    ("pitch_deck_library", "archived_at TIMESTAMP"),
                    ("pitch_deck_library", "archived_reason VARCHAR"),
                    ("pitch_deck_library", "status VARCHAR DEFAULT 'processing'"),
                    ("pitch_deck_library", "insights JSONB"),
                ]
                
                for table, column_def in migrations:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column_def}"))
                        conn.commit()
                    except Exception as e:
                        print(f"[MIGRATION] Error adding {column_def} to {table}: {e}")
                        conn.rollback()
                
                drop_migrations = [
                    ("client_reverts", "name"),
                    ("client_reverts", "verdict"),
                    ("client_reverts", "deal_status"),
                    ("client_reverts", "investment_signal"),
                    ("client_reverts", "funding_stage"),
                    ("client_reverts", "matched_clients"),
                ]
                for table, column in drop_migrations:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
                        conn.commit()
                    except Exception as e:
                        print(f"[MIGRATION] Error dropping {column} from {table}: {e}")
                        conn.rollback()

                try:
                    result = conn.execute(text("""
                        SELECT table_name, column_name 
                        FROM information_schema.columns 
                        WHERE table_name IN ('client_reverts', 'pitch_deck_library')
                        ORDER BY table_name, ordinal_position
                    """))
                    columns = result.fetchall()
                    print(f"[MIGRATION] Verified {len(columns)} columns exist")
                except Exception as e:
                    print(f"[MIGRATION] Verification failed: {e}")
                    
            print("[MIGRATION] Complete")
            return  # Success - exit retry loop
        except Exception as e:
            print(f"[MIGRATION] Attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                traceback.print_exc()

# Run migrations on import
run_migrations()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
