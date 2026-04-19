"""
Migration script to move from JSON files to PostgreSQL database
"""
import os
import json
import sys
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.database import Draft, Library, Conversation, Memory, User, Analytics, Settings
from app.models.database import Base, DATABASE_URL

def migrate_drafts(db_session):
    """Migrate drafts from JSON to database"""
    drafts_file = "app/data/drafts.json"
    if os.path.exists(drafts_file):
        with open(drafts_file, 'r') as f:
            drafts_data = json.load(f)
        
        # Create default user if not exists
        default_user = db_session.query(User).filter_by(username="default").first()
        if not default_user:
            default_user = User(
                username="default",
                email="default@finrag.com",
                hashed_password="default",
                full_name="Default User"
            )
            db_session.add(default_user)
            db_session.commit()
        
        for draft_data in drafts_data:
            draft = Draft(
                user_id=default_user.id,
                company=draft_data.get('company', 'Unknown'),
                date=datetime.strptime(draft_data.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d'),
                status=draft_data.get('status', 'Draft'),
                confidence=draft_data.get('confidence', 'Medium'),
                analysis=draft_data.get('analysis', ''),
                email_draft=draft_data.get('email_draft', ''),
                revenue_data=draft_data.get('revenue_data', []),
                files=draft_data.get('files', []),
                tags=draft_data.get('tags', [])
            )
            db_session.add(draft)
        
        db_session.commit()
        print(f"Migrated {len(drafts_data)} drafts to database")

def migrate_library(db_session):
    """Migrate library from JSON to database"""
    library_file = "app/data/library.json"
    if os.path.exists(library_file):
        with open(library_file, 'r') as f:
            library_data = json.load(f)
        
        # Create default user if not exists
        default_user = db_session.query(User).filter_by(username="default").first()
        if not default_user:
            default_user = User(
                username="default",
                email="default@finrag.com",
                hashed_password="default",
                full_name="Default User"
            )
            db_session.add(default_user)
            db_session.commit()
        
        for item in library_data:
            library_entry = Library(
                user_id=default_user.id,
                company=item.get('company', 'Unknown'),
                file_name=item.get('file_name', 'Unknown'),
                file_path=item.get('file_path', ''),
                file_size=item.get('file_size', 0),
                file_type=item.get('file_type', 'unknown'),
                date_uploaded=datetime.strptime(item.get('date_uploaded', datetime.now().strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S'),
                confidence=item.get('confidence', 'High'),
                tags=item.get('tags', []),
                metadata=item
            )
            db_session.add(library_entry)
        
        db_session.commit()
        print(f"Migrated {len(library_data)} library entries to database")

def migrate_memory(db_session):
    """Migrate memory from JSON to database"""
    memory_file = "app/data/memory.json"
    if os.path.exists(memory_file):
        with open(memory_file, 'r') as f:
            memory_data = json.load(f)
        
        # Create default user if not exists
        default_user = db_session.query(User).filter_by(username="default").first()
        if not default_user:
            default_user = User(
                username="default",
                email="default@finrag.com",
                hashed_password="default",
                full_name="Default User"
            )
            db_session.add(default_user)
            db_session.commit()
        
        for conv_data in memory_data:
            conversation = Conversation(
                user_id=default_user.id,
                query=conv_data.get('query', ''),
                response=conv_data.get('response', ''),
                context=conv_data.get('context', ''),
                tags=conv_data.get('tags', []),
                timestamp=datetime.strptime(conv_data.get('timestamp', datetime.now().isoformat()), '%Y-%m-%dT%H:%M:%S'),
                session_id=conv_data.get('session_id', 'default')
            )
            db_session.add(conversation)
        
        db_session.commit()
        print(f"Migrated {len(memory_data)} conversations to database")

def main():
    """Main migration function"""
    print("Starting migration to PostgreSQL...")
    
    # Create database engine
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    
    # Create session
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    
    try:
        # Migrate all data
        migrate_drafts(db_session)
        migrate_library(db_session)
        migrate_memory(db_session)
        
        print("Migration completed successfully!")
        
        # Backup old JSON files
        backup_dir = "app/data/backup"
        os.makedirs(backup_dir, exist_ok=True)
        
        if os.path.exists("app/data/drafts.json"):
            os.rename("app/data/drafts.json", f"{backup_dir}/drafts.json.backup")
        
        if os.path.exists("app/data/library.json"):
            os.rename("app/data/library.json", f"{backup_dir}/library.json.backup")
        
        if os.path.exists("app/data/memory.json"):
            os.rename("app/data/memory.json", f"{backup_dir}/memory.json.backup")
        
        print("Old JSON files backed up successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        db_session.rollback()
        sys.exit(1)
    finally:
        db_session.close()

if __name__ == "__main__":
    main()
