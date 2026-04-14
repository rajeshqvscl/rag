"""
Initialize admin user and create test user
Run this to fix "Invalid username or password" error
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app.config.database import SessionLocal
from app.services.auth_service import auth_service
from app.models.database import User

def init_admin():
    print("="*60)
    print("FinRAG Admin Initialization")
    print("="*60)
    
    db = SessionLocal()
    
    try:
        # Check if any users exist
        user_count = db.query(User).count()
        print(f"\nCurrent users in database: {user_count}")
        
        # Create default admin if no admin exists
        admin = db.query(User).filter(User.is_admin == True).first()
        
        if not admin:
            print("\nCreating default admin user...")
            admin = auth_service.create_user(
                db=db,
                username="admin",
                email="admin@finrag.com",
                password="admin123",
                full_name="System Administrator"
            )
            admin.is_admin = True
            db.commit()
            print("[OK] Admin created: admin / admin123")
        else:
            print(f"\n[OK] Admin user exists: {admin.username}")
        
        # Create test user if only admin exists
        if user_count <= 1:
            print("\nCreating test user...")
            test_user = auth_service.create_user(
                db=db,
                username="testuser",
                email="test@finrag.com",
                password="test123",
                full_name="Test User"
            )
            db.commit()
            print("[OK] Test user created: testuser / test123")
        
        # List all users
        print("\n" + "="*60)
        print("All Users:")
        print("="*60)
        users = db.query(User).all()
        for user in users:
            admin_tag = " [ADMIN]" if user.is_admin else ""
            print(f"  - {user.username} ({user.email}){admin_tag}")
        
        print("\n" + "="*60)
        print("Login Credentials:")
        print("="*60)
        print("  Admin:    admin / admin123")
        print("  Test:     testuser / test123")
        print("="*60)
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    init_admin()
