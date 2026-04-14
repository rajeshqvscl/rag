"""
Database diagnostic script - checks if tables exist and data is being saved
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.database import init_db, get_db, engine
from app.models.database import Draft, Library, User, Base
from sqlalchemy import inspect

print("=" * 60)
print("FinRAG Database Diagnostic")
print("=" * 60)

# Check if database file exists
db_path = os.path.join(os.path.dirname(__file__), "finrag.db")
print(f"\nDatabase file: {db_path}")
print(f"File exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    print(f"File size: {os.path.getsize(db_path)} bytes")

# Initialize database
print("\nInitializing database...")
try:
    init_db()
    print("✓ Database initialized successfully")
except Exception as e:
    print(f"✗ Error initializing database: {e}")

# Check tables
print("\nChecking tables...")
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"Tables found: {tables}")

required_tables = ['users', 'drafts', 'library', 'conversations', 'memories']
for table in required_tables:
    if table in tables:
        print(f"  ✓ {table}")
    else:
        print(f"  ✗ {table} - MISSING")

# Try to create a test draft
print("\nTesting draft creation...")
try:
    db = next(get_db())
    
    # Create default user if not exists
    user = db.query(User).filter_by(username="default").first()
    if not user:
        user = User(
            username="default",
            email="default@finrag.com",
            hashed_password="default",
            full_name="Default User"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✓ Created default user (ID: {user.id})")
    else:
        print(f"✓ Default user exists (ID: {user.id})")
    
    # Check existing drafts
    drafts = db.query(Draft).all()
    print(f"✓ Found {len(drafts)} drafts in database")
    for draft in drafts:
        print(f"  - Draft #{draft.id}: {draft.company} ({draft.date})")
    
    # Check existing library entries
    library = db.query(Library).all()
    print(f"✓ Found {len(library)} library entries")
    for item in library:
        print(f"  - Library #{item.id}: {item.company} - {item.file_name}")
    
    db.close()
    print("\n✓ Database connection working properly")
    
except Exception as e:
    print(f"\n✗ Database error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Diagnostic complete")
print("=" * 60)
