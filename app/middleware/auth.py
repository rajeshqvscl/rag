"""
API Key Authentication Middleware
Provides API key verification for protecting sensitive endpoints
"""
import os
import time
from collections import defaultdict
from functools import wraps
from typing import Optional, List
from fastapi import HTTPException, Header, Depends
from dotenv import load_dotenv

load_dotenv()


class AuthConfig:
    """Authentication configuration"""

    # Main API key for system access
    INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

    # Optional: Multiple API keys for different clients
    ALLOWED_API_KEYS = [
        os.getenv("API_KEY_1", ""),
        os.getenv("API_KEY_2", ""),
        os.getenv("API_KEY_3", "")
    ]

    # Endpoints that require authentication
    PROTECTED_ENDPOINTS = [
        "/process",
        "/send-email",
        "/library",
        "/config",
        "/admin"
    ]

    # Endpoints that are public (no auth required)
    PUBLIC_ENDPOINTS = [
        "/health",
        "/",
        "/test",
        "/metrics",
        "/favicon.ico",
        "/workflows"
    ]

    # Read-only endpoints (optional auth with rate limiting)
    OPTIONAL_AUTH_ENDPOINTS = [
        "/ask",
        "/documents",
        "/insights"
    ]

    @classmethod
    def is_valid_key(cls, api_key: str) -> bool:
        """Check if API key is valid"""
        if not api_key:
            return False

        if cls.INTERNAL_API_KEY and api_key == cls.INTERNAL_API_KEY:
            return True

        for key in cls.ALLOWED_API_KEYS:
            if key and api_key == key:
                return True

        return False


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """
    Dependency for verifying API key in FastAPI routes

    Usage:
        @app.post("/process")
        async def process(payload: ProcessPayload, api_key: str = Depends(verify_api_key)):
            ...
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Include X-API-Key header."
        )

    if not AuthConfig.is_valid_key(x_api_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return x_api_key


def optional_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> Optional[str]:
    """
    Dependency for optional API key verification
    Returns None if no key provided, otherwise validates

    Usage:
        @app.get("/ask")
        async def ask(query: str, api_key: Optional[str] = Depends(optional_api_key)):
            # Higher rate limit if api_key provided
            ...
    """
    if not x_api_key:
        return None

    if AuthConfig.is_valid_key(x_api_key):
        return x_api_key

    return None


def require_auth(func):
    """
    Decorator for protecting functions with API key

    Usage:
        @require_auth
        async def sensitive_operation(...):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        api_key = kwargs.get('x_api_key')
        if not api_key or not AuthConfig.is_valid_key(api_key):
            raise HTTPException(401, "Invalid or missing API key")
        return await func(*args, **kwargs)
    return wrapper


class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(self):
        self.requests = defaultdict(list)
        self.api_key_tiers = {
            # No key: basic limit
            None: {"requests": 10, "window": 60},
            # With valid key: higher limit
            "default": {"requests": 100, "window": 60},
            # Premium tier
            "premium": {"requests": 500, "window": 60}
        }

    def check_rate_limit(self, api_key: Optional[str], client_id: str = "default") -> bool:
        """
        Check if request is within rate limit

        Args:
            api_key: API key (if provided)
            client_id: Client identifier for tracking

        Returns:
            True if within limit, False if exceeded
        """
        tier = "premium" if api_key and AuthConfig.is_valid_key(api_key) else ("default" if api_key else None)
        config = self.api_key_tiers.get(tier, self.api_key_tiers[None])

        now = time.time()
        window_start = now - config["window"]

        # Clean old entries
        self.requests[client_id] = [
            ts for ts in self.requests[client_id]
            if ts > window_start
        ]

        if len(self.requests[client_id]) >= config["requests"]:
            return False

        self.requests[client_id].append(now)
        return True

    def get_remaining(self, api_key: Optional[str], client_id: str = "default") -> int:
        """Get remaining requests in current window"""
        tier = "premium" if api_key and AuthConfig.is_valid_key(api_key) else ("default" if api_key else None)
        config = self.api_key_tiers.get(tier, self.api_key_tiers[None])

        now = time.time()
        window_start = now - config["window"]

        recent_requests = [
            ts for ts in self.requests.get(client_id, [])
            if ts > window_start
        ]

        return max(0, config["requests"] - len(recent_requests))


# Global rate limiter instance
rate_limiter = RateLimiter()


def check_rate_limit(
    api_key: Optional[str] = Depends(optional_api_key),
    client_id: str = "default"
) -> str:
    """
    Dependency for rate limiting

    Usage:
        @app.post("/ask")
        async def ask(query: str, _ = Depends(check_rate_limit)):
            ...
    """
    if not rate_limiter.check_rate_limit(api_key, client_id):
        remaining = rate_limiter.get_remaining(api_key, client_id)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. {remaining} requests remaining."
        )
    return api_key or "anonymous"


def get_client_tier(api_key: Optional[str] = Depends(optional_api_key)) -> str:
    """Get client's tier based on API key"""
    if not api_key:
        return "free"
    if AuthConfig.is_valid_key(api_key):
        return "premium"
    return "free"


def get_system_status() -> dict:
    """Get system authentication and security status"""
    return {
        "auth_enabled": bool(AuthConfig.INTERNAL_API_KEY),
        "api_keys_configured": sum(1 for k in [
            AuthConfig.INTERNAL_API_KEY,
            *AuthConfig.ALLOWED_API_KEYS
        ] if k),
        "protected_endpoints": len(AuthConfig.PROTECTED_ENDPOINTS),
        "public_endpoints": len(AuthConfig.PUBLIC_ENDPOINTS),
        "rate_limit_tiers": list(RateLimiter().api_key_tiers.keys())
    }