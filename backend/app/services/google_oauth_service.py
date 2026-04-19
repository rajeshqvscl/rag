"""
Google OAuth service for authentication
"""
import os
import requests
from typing import Optional, Dict

class GoogleOAuthService:
    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:9000/auth/google/callback")
        self.scope = "openid email profile"
        
        # OAuth endpoints
        self.authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_endpoint = "https://oauth2.googleapis.com/token"
        self.userinfo_endpoint = "https://openidconnect.googleapis.com/v1/userinfo"
    
    def is_configured(self) -> bool:
        """Check if Google OAuth is properly configured"""
        return bool(self.client_id and self.client_secret)
    
    def get_authorization_url(self) -> str:
        """Generate Google OAuth authorization URL"""
        if not self.is_configured():
            raise ValueError("Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "access_type": "offline",
            "prompt": "consent",
            "state": "finrag_auth"  # Should be random in production
        }
        
        from urllib.parse import urlencode
        auth_url = f"{self.authorization_endpoint}?{urlencode(params)}"
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> Optional[Dict]:
        """Exchange authorization code for access token"""
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code"
        }
        
        response = requests.post(self.token_endpoint, data=data)
        
        if response.status_code != 200:
            print(f"Token exchange failed: {response.text}")
            return None
        
        return response.json()
    
    def get_user_info(self, code: str) -> Optional[Dict]:
        """Get user info from Google using authorization code"""
        # First exchange code for token
        token_data = self.exchange_code_for_token(code)
        
        if not token_data or "access_token" not in token_data:
            return None
        
        access_token = token_data["access_token"]
        
        # Get user info
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(self.userinfo_endpoint, headers=headers)
        
        if response.status_code != 200:
            print(f"Failed to get user info: {response.text}")
            return None
        
        user_info = response.json()
        
        # Map Google user info to standard format
        return {
            "id": user_info.get("sub"),
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture"),
            "verified_email": user_info.get("email_verified", False)
        }

# Global instance
google_oauth_service = GoogleOAuthService()
