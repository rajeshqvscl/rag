import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("e:/rag_system/.env")
db_url = os.getenv("DATABASE_URL")
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    db_url = db_url.replace("&channel_binding=require", "")
    db_url = db_url.replace("channel_binding=require", "")

engine = create_engine(db_url)
with engine.connect() as conn:
    result = conn.execute(text("SELECT id, company, status FROM pitch_deck_library WHERE id = 237"))
    row = result.fetchone()
    print("Row 237:", row)
    
    # Also check the highest ID just in case
    result = conn.execute(text("SELECT id FROM pitch_deck_library ORDER BY id DESC LIMIT 5"))
    print("Latest IDs:", result.fetchall())
