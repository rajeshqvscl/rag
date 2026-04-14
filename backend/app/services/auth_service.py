"""
Authentication service for user management
"""
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.models.database import User
from app.config.database import get_db

class AuthService:
    def __init__(self):
        self.secret_key = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        self.refresh_token_expire_days = 7
        
    def hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
    
    def create_access_token(self, data: Dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, data: Dict) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            if payload.get("type") != token_type:
                return None
            
            return payload
        except JWTError:
            return None
    
    def authenticate_user(self, db: Session, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        user = db.query(User).filter(User.username == username).first()
        
        if not user or not self.verify_password(password, user.hashed_password):
            return None
        
        if not user.is_active:
            return None
        
        return user
    
    def create_user(self, db: Session, username: str, email: str, password: str, full_name: str = None) -> User:
        """Create new user"""
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            raise ValueError("Username or email already exists")
        
        # Create new user
        hashed_password = self.hash_password(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name or username,
            is_active=True,
            is_admin=False
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return user
    
    def update_user(self, db: Session, user_id: int, **kwargs) -> Optional[User]:
        """Update user information"""
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return None
        
        # Update allowed fields
        allowed_fields = ["email", "full_name", "is_active"]
        for field, value in kwargs.items():
            if field in allowed_fields and hasattr(user, field):
                setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        return user
    
    def change_password(self, db: Session, user_id: int, current_password: str, new_password: str) -> bool:
        """Change user password"""
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not self.verify_password(current_password, user.hashed_password):
            return False
        
        user.hashed_password = self.hash_password(new_password)
        user.updated_at = datetime.utcnow()
        db.commit()
        
        return True
    
    def reset_password(self, db: Session, email: str) -> Optional[str]:
        """Reset password and return temporary password"""
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            return None
        
        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)
        user.hashed_password = self.hash_password(temp_password)
        user.updated_at = datetime.utcnow()
        db.commit()
        
        return temp_password
    
    def get_user_by_token(self, db: Session, token: str) -> Optional[User]:
        """Get user by JWT token"""
        payload = self.verify_token(token)
        
        if not payload:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        return user
    
    def is_admin(self, user: User) -> bool:
        """Check if user is admin"""
        return user.is_admin if user else False
    
    def create_default_admin(self, db: Session) -> User:
        """Create default admin user if not exists"""
        admin_user = db.query(User).filter(User.is_admin == True).first()
        
        if not admin_user:
            admin_user = self.create_user(
                db=db,
                username="admin",
                email="admin@finrag.com",
                password="admin123",  # Change this in production
                full_name="System Administrator"
            )
            admin_user.is_admin = True
            db.commit()
            db.refresh(admin_user)
        
        return admin_user
    
    def get_or_create_oauth_user(
        self, 
        db: Session, 
        email: str, 
        full_name: str, 
        provider: str, 
        provider_id: str
    ) -> User:
        """Get existing OAuth user or create new one"""
        # Try to find user by OAuth provider ID
        user = db.query(User).filter(
            User.oauth_provider == provider,
            User.oauth_provider_id == provider_id
        ).first()
        
        if user:
            return user
        
        # Try to find user by email
        user = db.query(User).filter(User.email == email).first()
        
        if user:
            # Link OAuth to existing user
            user.oauth_provider = provider
            user.oauth_provider_id = provider_id
            user.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(user)
            return user
        
        # Create new user from OAuth data
        # Generate username from email
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        
        # Ensure unique username
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Generate random secure password for OAuth user
        random_password = secrets.token_urlsafe(32)
        hashed_password = self.hash_password(random_password)
        
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name or username,
            is_active=True,
            is_admin=False,
            oauth_provider=provider,
            oauth_provider_id=provider_id
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        return user

# Global auth service instance
auth_service = AuthService()
