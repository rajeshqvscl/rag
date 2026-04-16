"""
Migration: Add revenue_data column to pitch_decks table
This stores revenue trajectory data extracted from pitch deck graphs
"""
import sys
import os

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

from sqlalchemy import text
from app.config.database import engine, Base
from app.models.database import PitchDeck

def upgrade():
    """Add missing columns to pitch_decks table"""
    with engine.connect() as conn:
        try:
            # Check existing columns (SQLite)
            result = conn.execute(text("""
                PRAGMA table_info(pitch_decks)
            """))
            existing_columns = [row[1] for row in result.fetchall()]
            
            # Columns to add
            columns_to_add = {
                'analysis': "TEXT",
                'email_draft': "TEXT",
                'revenue_data': "TEXT DEFAULT '[]'"
            }
            
            for column_name, column_def in columns_to_add.items():
                if column_name in existing_columns:
                    print(f"Column {column_name} already exists, skipping")
                else:
                    try:
                        conn.execute(text(f"""
                            ALTER TABLE pitch_decks 
                            ADD COLUMN {column_name} {column_def}
                        """))
                        print(f"Successfully added column {column_name}")
                    except Exception as e:
                        print(f"Error adding column {column_name}: {e}")
            
            conn.commit()
            print("Migration completed successfully")
            
        except Exception as e:
            conn.rollback()
            print(f"Error in migration: {e}")
            raise

def downgrade():
    """Remove revenue_data column from pitch_decks table"""
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly
            # Need to recreate table without the column
            print("SQLite doesn't support DROP COLUMN directly. Manual recreation needed.")
            print("To rollback: Create new table without revenue_data, copy data, rename tables.")
            
        except Exception as e:
            conn.rollback()
            print(f"Error removing revenue_data column: {e}")
            raise

if __name__ == "__main__":
    upgrade()
