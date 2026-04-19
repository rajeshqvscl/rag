"""
Enterprise security service for advanced security features
"""
import os
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.database import User, Analytics
from app.config.database import get_db
import bcrypt
import logging
from functools import wraps

class EnterpriseSecurityService:
    def __init__(self):
        self.security_config = {
            "password_policy": {
                "min_length": 12,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_numbers": True,
                "require_special_chars": True,
                "max_age_days": 90
            },
            "session_policy": {
                "max_duration_hours": 8,
                "idle_timeout_minutes": 30,
                "max_concurrent_sessions": 3
            },
            "audit_policy": {
                "log_all_access": True,
                "log_failed_attempts": True,
                "retention_days": 365
            },
            "encryption_policy": {
                "data_at_rest": True,
                "data_in_transit": True,
                "key_rotation_days": 90
            }
        }
        
        self.audit_log = []
        self.failed_attempts = {}
        self.active_sessions = {}
        
    def validate_password_strength(self, password: str) -> Dict:
        """Validate password against enterprise security policy"""
        try:
            policy = self.security_config["password_policy"]
            validation_result = {
                "is_valid": True,
                "errors": [],
                "strength_score": 0,
                "recommendations": []
            }
            
            # Check minimum length
            if len(password) < policy["min_length"]:
                validation_result["is_valid"] = False
                validation_result["errors"].append(f"Password must be at least {policy['min_length']} characters long")
            else:
                validation_result["strength_score"] += 20
            
            # Check for uppercase letters
            if policy["require_uppercase"] and not any(c.isupper() for c in password):
                validation_result["is_valid"] = False
                validation_result["errors"].append("Password must contain at least one uppercase letter")
            else:
                validation_result["strength_score"] += 20
            
            # Check for lowercase letters
            if policy["require_lowercase"] and not any(c.islower() for c in password):
                validation_result["is_valid"] = False
                validation_result["errors"].append("Password must contain at least one lowercase letter")
            else:
                validation_result["strength_score"] += 20
            
            # Check for numbers
            if policy["require_numbers"] and not any(c.isdigit() for c in password):
                validation_result["is_valid"] = False
                validation_result["errors"].append("Password must contain at least one number")
            else:
                validation_result["strength_score"] += 20
            
            # Check for special characters
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if policy["require_special_chars"] and not any(c in special_chars for c in password):
                validation_result["is_valid"] = False
                validation_result["errors"].append("Password must contain at least one special character")
            else:
                validation_result["strength_score"] += 20
            
            # Additional strength checks
            if len(password) >= 16:
                validation_result["strength_score"] += 10
                validation_result["recommendations"].append("Good password length")
            
            # Check for common patterns
            if self._has_common_patterns(password):
                validation_result["strength_score"] -= 20
                validation_result["recommendations"].append("Avoid common patterns or dictionary words")
            
            return validation_result
            
        except Exception as e:
            return {"is_valid": False, "errors": [str(e)], "strength_score": 0, "recommendations": []}
    
    def _has_common_patterns(self, password: str) -> bool:
        """Check for common password patterns"""
        common_patterns = [
            "123456", "password", "qwerty", "admin", "letmein",
            "welcome", "monkey", "dragon", "master", "sunshine"
        ]
        
        password_lower = password.lower()
        return any(pattern in password_lower for pattern in common_patterns)
    
    def hash_password_bcrypt(self, password: str) -> str:
        """Hash password using bcrypt"""
        try:
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            raise Exception(f"Password hashing failed: {str(e)}")
    
    def verify_password_bcrypt(self, password: str, hashed_password: str) -> bool:
        """Verify password using bcrypt"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            return False
    
    def create_secure_session(self, user_id: int, user_agent: str, ip_address: str) -> Dict:
        """Create secure session with enterprise features"""
        try:
            session_id = secrets.token_urlsafe(32)
            session_token = self._generate_jwt_token(user_id, session_id)
            
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "user_agent": user_agent,
                "ip_address": ip_address,
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=self.security_config["session_policy"]["max_duration_hours"]),
                "is_active": True
            }
            
            self.active_sessions[session_id] = session_data
            
            # Log session creation
            self._log_security_event("session_created", {
                "user_id": user_id,
                "session_id": session_id,
                "ip_address": ip_address,
                "user_agent": user_agent
            })
            
            return {
                "session_token": session_token,
                "session_id": session_id,
                "expires_at": session_data["expires_at"].isoformat()
            }
            
        except Exception as e:
            raise Exception(f"Session creation failed: {str(e)}")
    
    def _generate_jwt_token(self, user_id: int, session_id: str) -> str:
        """Generate JWT token with enterprise claims"""
        try:
            payload = {
                "user_id": user_id,
                "session_id": session_id,
                "iat": datetime.utcnow(),
                "exp": datetime.utcnow() + timedelta(hours=8),
                "iss": "finrag-enterprise",
                "aud": "finrag-api"
            }
            
            secret_key = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
            token = jwt.encode(payload, secret_key, algorithm="HS256")
            
            return token
            
        except Exception as e:
            raise Exception(f"JWT token generation failed: {str(e)}")
    
    def validate_session(self, session_token: str, ip_address: str) -> Dict:
        """Validate session with enterprise security checks"""
        try:
            # Decode JWT token
            secret_key = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
            payload = jwt.decode(session_token, secret_key, algorithms=["HS256"])
            
            session_id = payload.get("session_id")
            user_id = payload.get("user_id")
            
            if not session_id or session_id not in self.active_sessions:
                self._log_security_event("invalid_session_token", {
                    "token": session_token[:20] + "...",
                    "ip_address": ip_address
                })
                return {"valid": False, "reason": "Invalid session token"}
            
            session_data = self.active_sessions[session_id]
            
            # Check if session is expired
            if datetime.utcnow() > session_data["expires_at"]:
                del self.active_sessions[session_id]
                self._log_security_event("session_expired", {
                    "session_id": session_id,
                    "user_id": user_id
                })
                return {"valid": False, "reason": "Session expired"}
            
            # Check idle timeout
            idle_time = datetime.utcnow() - session_data["last_activity"]
            if idle_time > timedelta(minutes=self.security_config["session_policy"]["idle_timeout_minutes"]):
                del self.active_sessions[session_id]
                self._log_security_event("session_idle_timeout", {
                    "session_id": session_id,
                    "user_id": user_id,
                    "idle_minutes": idle_time.total_seconds() / 60
                })
                return {"valid": False, "reason": "Session idle timeout"}
            
            # Check IP address (optional security feature)
            if session_data["ip_address"] != ip_address:
                self._log_security_event("ip_address_mismatch", {
                    "session_id": session_id,
                    "user_id": user_id,
                    "original_ip": session_data["ip_address"],
                    "current_ip": ip_address
                })
                # Could either reject or just log depending on policy
            
            # Update last activity
            session_data["last_activity"] = datetime.utcnow()
            
            return {
                "valid": True,
                "user_id": user_id,
                "session_id": session_id
            }
            
        except jwt.ExpiredSignatureError:
            return {"valid": False, "reason": "Token expired"}
        except jwt.InvalidTokenError:
            return {"valid": False, "reason": "Invalid token"}
        except Exception as e:
            return {"valid": False, "reason": str(e)}
    
    def _log_security_event(self, event_type: str, details: Dict):
        """Log security events for audit trail"""
        try:
            event = {
                "event_type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "details": details
            }
            
            self.audit_log.append(event)
            
            # Keep audit log size manageable
            if len(self.audit_log) > 10000:
                self.audit_log = self.audit_log[-5000:]
            
            # In production, this would log to a secure audit system
            logging.info(f"Security event: {event_type} - {details}")
            
        except Exception as e:
            logging.error(f"Failed to log security event: {str(e)}")
    
    def detect_suspicious_activity(self, user_id: int) -> Dict:
        """Detect suspicious activity patterns"""
        try:
            suspicious_indicators = {
                "failed_login_attempts": 0,
                "concurrent_sessions": 0,
                "unusual_ip_addresses": [],
                "rapid_session_creation": False,
                "risk_score": 0.0,
                "recommendations": []
            }
            
            # Check failed login attempts
            if user_id in self.failed_attempts:
                failed_attempts = self.failed_attempts[user_id]
                recent_failures = [
                    attempt for attempt in failed_attempts
                    if datetime.utcnow() - attempt["timestamp"] < timedelta(hours=1)
                ]
                suspicious_indicators["failed_login_attempts"] = len(recent_failures)
                
                if len(recent_failures) > 5:
                    suspicious_indicators["risk_score"] += 30
                    suspicious_indicators["recommendations"].append("Multiple failed login attempts detected")
            
            # Check concurrent sessions
            user_sessions = [
                session for session in self.active_sessions.values()
                if session["user_id"] == user_id and session["is_active"]
            ]
            suspicious_indicators["concurrent_sessions"] = len(user_sessions)
            
            if len(user_sessions) > self.security_config["session_policy"]["max_concurrent_sessions"]:
                suspicious_indicators["risk_score"] += 20
                suspicious_indicators["recommendations"].append("Excessive concurrent sessions")
            
            # Check for unusual IP addresses
            ip_addresses = set()
            for session in user_sessions:
                ip_addresses.add(session["ip_address"])
            
            if len(ip_addresses) > 3:
                suspicious_indicators["unusual_ip_addresses"] = list(ip_addresses)
                suspicious_indicators["risk_score"] += 25
                suspicious_indicators["recommendations"].append("Multiple IP addresses in use")
            
            # Determine overall risk level
            if suspicious_indicators["risk_score"] >= 50:
                risk_level = "high"
            elif suspicious_indicators["risk_score"] >= 25:
                risk_level = "medium"
            else:
                risk_level = "low"
            
            suspicious_indicators["risk_level"] = risk_level
            
            return suspicious_indicators
            
        except Exception as e:
            return {"error": str(e), "risk_score": 0.0}
    
    def enforce_rate_limiting(self, user_id: int, action: str, limit: int = 100, window_minutes: int = 60) -> Dict:
        """Enforce rate limiting for API actions"""
        try:
            rate_limit_key = f"{user_id}:{action}"
            current_time = datetime.utcnow()
            
            # Initialize rate limiting data if not exists
            if not hasattr(self, 'rate_limits'):
                self.rate_limits = {}
            
            if rate_limit_key not in self.rate_limits:
                self.rate_limits[rate_limit_key] = []
            
            # Clean old entries
            cutoff_time = current_time - timedelta(minutes=window_minutes)
            self.rate_limits[rate_limit_key] = [
                timestamp for timestamp in self.rate_limits[rate_limit_key]
                if timestamp > cutoff_time
            ]
            
            # Check if limit exceeded
            if len(self.rate_limits[rate_limit_key]) >= limit:
                self._log_security_event("rate_limit_exceeded", {
                    "user_id": user_id,
                    "action": action,
                    "attempts": len(self.rate_limits[rate_limit_key]),
                    "limit": limit
                })
                
                return {
                    "allowed": False,
                    "remaining": 0,
                    "reset_time": (self.rate_limits[rate_limit_key][0] + timedelta(minutes=window_minutes)).isoformat()
                }
            
            # Add current request
            self.rate_limits[rate_limit_key].append(current_time)
            
            return {
                "allowed": True,
                "remaining": max(0, limit - len(self.rate_limits[rate_limit_key])),
                "reset_time": (current_time + timedelta(minutes=window_minutes)).isoformat()
            }
            
        except Exception as e:
            return {"allowed": False, "error": str(e)}
    
    def encrypt_sensitive_data(self, data: str, encryption_key: str = None) -> Dict:
        """Encrypt sensitive data"""
        try:
            if not encryption_key:
                encryption_key = os.getenv("ENCRYPTION_KEY", secrets.token_urlsafe(32))
            
            # Simple XOR encryption for demo (use proper encryption in production)
            key_bytes = encryption_key.encode()
            data_bytes = data.encode()
            
            encrypted_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes)])
            encrypted_data = encrypted_bytes.hex()
            
            return {
                "encrypted_data": encrypted_data,
                "encryption_method": "XOR",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def decrypt_sensitive_data(self, encrypted_data: str, encryption_key: str = None) -> Dict:
        """Decrypt sensitive data"""
        try:
            if not encryption_key:
                encryption_key = os.getenv("ENCRYPTION_KEY", secrets.token_urlsafe(32))
            
            key_bytes = encryption_key.encode()
            encrypted_bytes = bytes.fromhex(encrypted_data)
            
            decrypted_bytes = bytes([b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(encrypted_bytes)])
            decrypted_data = decrypted_bytes.decode()
            
            return {
                "decrypted_data": decrypted_data,
                "decryption_method": "XOR",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_security_audit_log(self, user_id: int = None, event_type: str = None, limit: int = 100) -> Dict:
        """Get security audit log"""
        try:
            filtered_log = self.audit_log
            
            # Filter by user ID
            if user_id:
                filtered_log = [
                    event for event in filtered_log
                    if event["details"].get("user_id") == user_id
                ]
            
            # Filter by event type
            if event_type:
                filtered_log = [
                    event for event in filtered_log
                    if event["event_type"] == event_type
                ]
            
            # Sort by timestamp (most recent first)
            filtered_log.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # Limit results
            filtered_log = filtered_log[:limit]
            
            return {
                "status": "success",
                "audit_log": filtered_log,
                "total_events": len(filtered_log),
                "filters_applied": {
                    "user_id": user_id,
                    "event_type": event_type,
                    "limit": limit
                }
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_security_dashboard(self) -> Dict:
        """Get security dashboard data"""
        try:
            current_time = datetime.utcnow()
            
            dashboard = {
                "active_sessions": len([s for s in self.active_sessions.values() if s["is_active"]]),
                "recent_security_events": len([
                    event for event in self.audit_log
                    if datetime.fromisoformat(event["timestamp"]) > current_time - timedelta(hours=24)
                ]),
                "failed_login_attempts": len(self.failed_attempts),
                "security_events_by_type": {},
                "high_risk_users": [],
                "security_health_score": 0
            }
            
            # Count events by type
            for event in self.audit_log:
                event_type = event["event_type"]
                if event_type not in dashboard["security_events_by_type"]:
                    dashboard["security_events_by_type"][event_type] = 0
                dashboard["security_events_by_type"][event_type] += 1
            
            # Calculate security health score
            health_score = 100
            
            # Deduct for failed attempts
            if dashboard["failed_login_attempts"] > 10:
                health_score -= 20
            elif dashboard["failed_login_attempts"] > 5:
                health_score -= 10
            
            # Deduct for excessive active sessions
            if dashboard["active_sessions"] > 100:
                health_score -= 15
            elif dashboard["active_sessions"] > 50:
                health_score -= 5
            
            dashboard["security_health_score"] = max(0, health_score)
            
            return {
                "status": "success",
                "security_dashboard": dashboard,
                "generated_at": current_time.isoformat()
            }
            
        except Exception as e:
            return {"error": str(e)}

# Global enterprise security service instance
enterprise_security_service = EnterpriseSecurityService()
