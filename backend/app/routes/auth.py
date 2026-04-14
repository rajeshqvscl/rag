"""
Authentication routes for user management
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.services.auth_service import auth_service
from app.models.database import User
from app.config.database import get_db

router = APIRouter()
security = HTTPBearer()

# Pydantic models
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: str
    updated_at: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class PasswordReset(BaseModel):
    email: EmailStr

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = auth_service.verify_token(credentials.credentials)
        if payload is None:
            raise credentials_exception
        
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Get current admin user"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return current_user

@router.post("/auth/register", response_model=UserResponse)
def register_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user"""
    try:
        # Validate input
        if len(user.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
        
        if len(user.username) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters long")
        
        # Create user
        new_user = auth_service.create_user(
            db=db,
            username=user.username,
            email=user.email,
            password=user.password,
            full_name=user.full_name
        )
        
        return UserResponse(
            id=new_user.id,
            username=new_user.username,
            email=new_user.email,
            full_name=new_user.full_name,
            is_active=new_user.is_active,
            is_admin=new_user.is_admin,
            created_at=new_user.created_at.isoformat(),
            updated_at=new_user.updated_at.isoformat()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/login", response_model=Token)
def login_user(
    user_credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """Login user and return JWT tokens"""
    user = auth_service.authenticate_user(db, user_credentials.username, user_credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth_service.create_access_token(data={"sub": str(user.id)})
    refresh_token = auth_service.create_refresh_token(data={"sub": str(user.id)})
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60
    )

@router.post("/auth/refresh", response_model=Token)
def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    payload = auth_service.verify_token(refresh_token, "refresh")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    access_token = auth_service.create_access_token(data={"sub": str(user.id)})
    new_refresh_token = auth_service.create_refresh_token(data={"sub": str(user.id)})
    
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=auth_service.access_token_expire_minutes * 60
    )

@router.get("/auth/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        created_at=current_user.created_at.isoformat(),
        updated_at=current_user.updated_at.isoformat()
    )

@router.put("/auth/me", response_model=UserResponse)
def update_current_user(
    user_update: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update current user information"""
    try:
        updated_user = auth_service.update_user(db, current_user.id, **user_update)
        
        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(
            id=updated_user.id,
            username=updated_user.username,
            email=updated_user.email,
            full_name=updated_user.full_name,
            is_active=updated_user.is_active,
            is_admin=updated_user.is_admin,
            created_at=updated_user.created_at.isoformat(),
            updated_at=updated_user.updated_at.isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/change-password")
def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    try:
        if len(password_data.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters long")
        
        success = auth_service.change_password(
            db, current_user.id, password_data.current_password, password_data.new_password
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        return {"status": "success", "message": "Password changed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/auth/reset-password")
def reset_password(
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
):
    """Reset password and send temporary password"""
    try:
        temp_password = auth_service.reset_password(db, reset_data.email)
        
        if not temp_password:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # In production, send email with temp_password
        # For now, return it (remove this in production)
        return {
            "status": "success",
            "message": "Password reset successful",
            "temp_password": temp_password  # Remove this in production
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/auth/users", response_model=list[UserResponse])
def list_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    users = db.query(User).all()
    
    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat()
        )
        for user in users
    ]

@router.post("/auth/init-admin")
def initialize_admin(db: Session = Depends(get_db)):
    """Initialize default admin user"""
    try:
        admin_user = auth_service.create_default_admin(db)
        
        return {
            "status": "success",
            "message": "Default admin user created/updated",
            "admin": {
                "username": admin_user.username,
                "email": admin_user.email
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Google OAuth Routes
@router.get("/auth/google/login")
def google_login():
    """Initiate Google OAuth login"""
    try:
        from app.services.google_oauth_service import google_oauth_service
        auth_url = google_oauth_service.get_authorization_url()
        return {"authorization_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google OAuth error: {str(e)}")

@router.get("/auth/google/callback")
def google_callback(
    code: str,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback"""
    try:
        from app.services.google_oauth_service import google_oauth_service
        
        # Exchange code for tokens and get user info
        user_info = google_oauth_service.get_user_info(code)
        
        if not user_info or not user_info.get("email"):
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        # Create or get user
        user = auth_service.get_or_create_oauth_user(
            db=db,
            email=user_info["email"],
            full_name=user_info.get("name", user_info["email"]),
            provider="google",
            provider_id=user_info.get("id")
        )
        
        # Generate tokens
        access_token = auth_service.create_access_token(data={"sub": str(user.id)})
        refresh_token = auth_service.create_refresh_token(data={"sub": str(user.id)})
        
        return {
            "status": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": auth_service.access_token_expire_minutes * 60,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google callback error: {str(e)}")
