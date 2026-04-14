"""
Enterprise security routes for advanced security features
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.enterprise_security_service import enterprise_security_service
from app.models.database import User
from app.config.database import get_db
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class PasswordValidationRequest(BaseModel):
    password: str

class SessionCreationRequest(BaseModel):
    user_id: int
    user_agent: str
    ip_address: str

class RateLimitRequest(BaseModel):
    user_id: int
    action: str
    limit: int = 100
    window_minutes: int = 60

class DataEncryptionRequest(BaseModel):
    data: str
    encryption_key: Optional[str] = None

def get_or_create_default_user(db: Session) -> User:
    """Get or create default user"""
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
    return user

@router.post("/security/validate-password")
def validate_password_strength(
    request: PasswordValidationRequest,
    api_key: str = Depends(get_api_key)
):
    """Validate password against enterprise security policy"""
    try:
        validation_result = enterprise_security_service.validate_password_strength(request.password)
        
        return {
            "status": "success",
            "password_validation": validation_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/hash-password")
def hash_password(
    request: PasswordValidationRequest,
    api_key: str = Depends(get_api_key)
):
    """Hash password using bcrypt"""
    try:
        hashed_password = enterprise_security_service.hash_password_bcrypt(request.password)
        
        return {
            "status": "success",
            "hashed_password": hashed_password
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/verify-password")
def verify_password(
    password: str,
    hashed_password: str,
    api_key: str = Depends(get_api_key)
):
    """Verify password using bcrypt"""
    try:
        is_valid = enterprise_security_service.verify_password_bcrypt(password, hashed_password)
        
        return {
            "status": "success",
            "is_valid": is_valid
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/create-session")
def create_secure_session(
    request: SessionCreationRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Create secure session with enterprise features"""
    try:
        user = get_or_create_default_user(db)
        
        # Verify user exists
        if request.user_id != user.id:
            raise HTTPException(status_code=404, detail="User not found")
        
        session_result = enterprise_security_service.create_secure_session(
            request.user_id,
            request.user_agent,
            request.ip_address
        )
        
        return {
            "status": "success",
            "session_data": session_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/validate-session")
def validate_session(
    session_token: str,
    ip_address: str,
    api_key: str = Depends(get_api_key)
):
    """Validate session with enterprise security checks"""
    try:
        validation_result = enterprise_security_service.validate_session(session_token, ip_address)
        
        return {
            "status": "success",
            "session_validation": validation_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/detect-suspicious-activity/{user_id}")
def detect_suspicious_activity(
    user_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Detect suspicious activity patterns"""
    try:
        user = get_or_create_default_user(db)
        
        if user_id != user.id:
            raise HTTPException(status_code=404, detail="User not found")
        
        suspicious_activity = enterprise_security_service.detect_suspicious_activity(user_id)
        
        return {
            "status": "success",
            "suspicious_activity": suspicious_activity
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/rate-limit")
def enforce_rate_limiting(
    request: RateLimitRequest,
    api_key: str = Depends(get_api_key)
):
    """Enforce rate limiting for API actions"""
    try:
        rate_limit_result = enterprise_security_service.enforce_rate_limiting(
            request.user_id,
            request.action,
            request.limit,
            request.window_minutes
        )
        
        return {
            "status": "success",
            "rate_limiting": rate_limit_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/encrypt-data")
def encrypt_sensitive_data(
    request: DataEncryptionRequest,
    api_key: str = Depends(get_api_key)
):
    """Encrypt sensitive data"""
    try:
        encryption_result = enterprise_security_service.encrypt_sensitive_data(
            request.data,
            request.encryption_key
        )
        
        return {
            "status": "success",
            "encryption_result": encryption_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/decrypt-data")
def decrypt_sensitive_data(
    encrypted_data: str,
    encryption_key: Optional[str] = None,
    api_key: str = Depends(get_api_key)
):
    """Decrypt sensitive data"""
    try:
        decryption_result = enterprise_security_service.decrypt_sensitive_data(
            encrypted_data,
            encryption_key
        )
        
        return {
            "status": "success",
            "decryption_result": decryption_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/audit-log")
def get_security_audit_log(
    user_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    api_key: str = Depends(get_api_key)
):
    """Get security audit log"""
    try:
        audit_log = enterprise_security_service.get_security_audit_log(
            user_id,
            event_type,
            limit
        )
        
        return {
            "status": "success",
            "audit_log": audit_log
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/dashboard")
def get_security_dashboard(api_key: str = Depends(get_api_key)):
    """Get security dashboard data"""
    try:
        dashboard = enterprise_security_service.get_security_dashboard()
        
        return {
            "status": "success",
            "security_dashboard": dashboard
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/policy")
def get_security_policy(api_key: str = Depends(get_api_key)):
    """Get current security policy configuration"""
    try:
        policy = enterprise_security_service.security_config
        
        return {
            "status": "success",
            "security_policy": policy
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/health")
def get_security_health(api_key: str = Depends(get_api_key)):
    """Get overall security health status"""
    try:
        dashboard_result = enterprise_security_service.get_security_dashboard()
        
        if "error" in dashboard_result:
            raise HTTPException(status_code=500, detail="Failed to get security dashboard")
        
        dashboard = dashboard_result["security_dashboard"]["security_dashboard"]
        
        health_status = {
            "overall_health": "healthy",
            "health_score": dashboard["security_health_score"],
            "active_sessions": dashboard["active_sessions"],
            "recent_events": dashboard["recent_security_events"],
            "failed_attempts": dashboard["failed_login_attempts"],
            "recommendations": [],
            "alerts": []
        }
        
        # Determine health status
        if dashboard["security_health_score"] >= 80:
            health_status["overall_health"] = "healthy"
        elif dashboard["security_health_score"] >= 60:
            health_status["overall_health"] = "warning"
        else:
            health_status["overall_health"] = "critical"
        
        # Generate recommendations
        if dashboard["failed_login_attempts"] > 10:
            health_status["recommendations"].append("High number of failed login attempts - investigate potential brute force attacks")
        
        if dashboard["active_sessions"] > 100:
            health_status["recommendations"].append("High number of active sessions - consider session cleanup")
        
        if dashboard["recent_security_events"] > 50:
            health_status["recommendations"].append("High security event volume - review recent activity")
        
        # Generate alerts
        if dashboard["failed_login_attempts"] > 20:
            health_status["alerts"].append("CRITICAL: Excessive failed login attempts detected")
        
        if dashboard["security_health_score"] < 50:
            health_status["alerts"].append("WARNING: Security health score below 50")
        
        return {
            "status": "success",
            "security_health": health_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/security/logout-session")
def logout_session(
    session_token: str,
    api_key: str = Depends(get_api_key)
):
    """Logout and invalidate session"""
    try:
        # Decode token to get session ID
        import jwt
        import os
        
        secret_key = os.getenv("JWT_SECRET_KEY", "default")
        payload = jwt.decode(session_token, secret_key, algorithms=["HS256"])
        session_id = payload.get("session_id")
        
        if session_id and session_id in enterprise_security_service.active_sessions:
            # Invalidate session
            enterprise_security_service.active_sessions[session_id]["is_active"] = False
            
            # Log logout
            enterprise_security_service._log_security_event("session_logout", {
                "session_id": session_id,
                "user_id": payload.get("user_id")
            })
            
            return {
                "status": "success",
                "message": "Session logged out successfully"
            }
        else:
            return {
                "status": "warning",
                "message": "Session not found or already inactive"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/user-sessions/{user_id}")
def get_user_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get all active sessions for a user"""
    try:
        user = get_or_create_default_user(db)
        
        if user_id != user.id:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_sessions = [
            {
                "session_id": session["session_id"],
                "created_at": session["created_at"].isoformat(),
                "last_activity": session["last_activity"].isoformat(),
                "expires_at": session["expires_at"].isoformat(),
                "ip_address": session["ip_address"],
                "user_agent": session["user_agent"],
                "is_active": session["is_active"]
            }
            for session in enterprise_security_service.active_sessions.values()
            if session["user_id"] == user_id
        ]
        
        return {
            "status": "success",
            "user_sessions": user_sessions,
            "total_sessions": len(user_sessions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/security/cleanup-sessions")
def cleanup_expired_sessions(api_key: str = Depends(get_api_key)):
    """Clean up expired sessions"""
    try:
        current_time = datetime.utcnow()
        expired_sessions = []
        
        for session_id, session in list(enterprise_security_service.active_sessions.items()):
            if current_time > session["expires_at"] or not session["is_active"]:
                expired_sessions.append(session_id)
                del enterprise_security_service.active_sessions[session_id]
        
        return {
            "status": "success",
            "cleaned_sessions": len(expired_sessions),
            "remaining_sessions": len(enterprise_security_service.active_sessions)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
