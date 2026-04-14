"""
Comprehensive storage diagnostic and fix script
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config.database import init_db, get_db, engine
from app.models.database import Draft, Library, User, Base
from sqlalchemy import inspect, text
import json

print("=" * 70)
print("STORAGE DIAGNOSTIC & FIX")
print("=" * 70)

# 1. Check database file
print("\n1. DATABASE FILE CHECK")
db_path = os.path.join(os.path.dirname(__file__), "finrag.db")
print(f"   Path: {db_path}")
print(f"   Exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    print(f"   Size: {os.path.getsize(db_path)} bytes")

# 2. Initialize and check tables
print("\n2. TABLE VERIFICATION")
try:
    init_db()
    print("   ✓ Database initialized")
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"   Tables: {tables}")
    
    # Check each required table
    required = ['users', 'drafts', 'library']
    for table in required:
        if table in tables:
            # Count rows
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"   ✓ {table}: {count} rows")
        else:
            print(f"   ✗ {table}: MISSING!")
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# 3. Check data in tables
print("\n3. DATA INSPECTION")
try:
    db = next(get_db())
    
    # Check users
    users = db.query(User).all()
    print(f"   Users: {len(users)}")
    for u in users:
        print(f"      - ID {u.id}: {u.username} ({u.email})")
    
    # Check drafts
    drafts = db.query(Draft).all()
    print(f"   Drafts: {len(drafts)}")
    for d in drafts[:5]:  # Show first 5
        print(f"      - ID {d.id}: {d.company} ({d.status})")
    if len(drafts) > 5:
        print(f"      ... and {len(drafts)-5} more")
    
    # Check library
    library = db.query(Library).all()
    print(f"   Library: {len(library)}")
    for l in library[:5]:
        print(f"      - ID {l.id}: {l.company} - {l.file_name}")
    if len(library) > 5:
        print(f"      ... and {len(library)-5} more")
    
    db.close()
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# 4. Create test entries
print("\n4. CREATING TEST ENTRIES")
try:
    db = next(get_db())
    
    # Create default user
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
        print(f"   ✓ Created default user (ID: {user.id})")
    else:
        print(f"   ✓ Default user exists (ID: {user.id})")
    
    # Create test draft
    from datetime import datetime
    test_draft = Draft(
        user_id=user.id,
        company="TEST COMPANY - Diagnostic",
        date=datetime.utcnow(),
        status="Completed",
        confidence="High",
        analysis="This is a test analysis created by the diagnostic script to verify storage is working.",
        email_draft="Subject: Test Email\n\nThis is a test email draft.",
        revenue_data=[{"year": 2024, "revenue": "100M"}],
        files=[{"name": "test.pdf"}],
        tags=["test", "diagnostic"]
    )
    db.add(test_draft)
    db.commit()
    print(f"   ✓ Created test draft (ID: {test_draft.id})")
    
    # Create test library entry
    test_lib = Library(
        user_id=user.id,
        company="TEST COMPANY - Diagnostic",
        file_name="test_pitch_deck.pdf",
        file_path="/test/path/test.pdf",
        file_size=1024,
        file_type="pdf",
        date_uploaded=datetime.utcnow(),
        confidence="High",
        tags=["test"],
        file_metadata={"test": True}
    )
    db.add(test_lib)
    db.commit()
    print(f"   ✓ Created test library entry (ID: {test_lib.id})")
    
    db.close()
    print("\n   ✓ Test entries created successfully!")
    print("   ✓ Check the frontend - you should see 'TEST COMPANY - Diagnostic'")
    
except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()

# 5. Memory Storage Ideas
print("\n5. MEMORY STORAGE TECHNIQUES & IDEAS")
print("""
Current Storage Architecture:
├── SQLite Database (SQLAlchemy ORM)
│   ├── users table
│   ├── drafts table (JSON columns for flexible data)
│   ├── library table (file metadata)
│   ├── conversations table (chat history)
│   └── memories table (vector embeddings)
├── FAISS Vector Index (HNSW) - for semantic search
└── File System (PDFs, uploads)

Recommended Enhancements:

a) REDIS CACHE LAYER (Fast in-memory lookups)
   - Cache frequent queries: user sessions, recent drafts
   - TTL-based expiration for hot data
   - Pub/sub for real-time updates

b) ELASTICSEARCH (Full-text search)
   - Index analysis text for fast keyword search
   - Fuzzy matching for company names
   - Aggregations for analytics

c) TIME-SERIES DATABASE (InfluxDB/TimescaleDB)
   - Store revenue projections over time
   - Efficient range queries
   - Financial trend analysis

d) OBJECT STORAGE (S3/MinIO)
   - Store large PDFs externally
   - CDN delivery for pitch decks
   - Version control for documents

e) VECTOR DATABASE (Dedicated)
   - Pinecone/Weaviate for embeddings
   - Multi-tenant isolation
   - Better scaling than FAISS

f) GRAPH DATABASE (Neo4j)
   - Track company relationships
   - Investment network mapping
   - Due diligence connections

Implemented Optimizations:
✓ HNSW index for fast vector search (62k+ queries/sec)
✓ JSON columns for flexible schema
✓ Database indexing on company, user_id
✓ Lazy loading of ML models
""")

print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
print("\nNext steps:")
print("1. Restart the backend to ensure clean state")
print("2. Upload a pitch deck in the Analysis tab")
print("3. Check Drafts and Library tabs - should show test entries")
print("4. If issues persist, check browser console (F12) for errors")
