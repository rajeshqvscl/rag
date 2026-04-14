from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.services.security_service import get_api_key
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import secrets
import time
from datetime import datetime

router = APIRouter()

# OAuth state storage (in production, use Redis)
oauth_states = {}

# Integration configurations with OAuth settings
INTEGRATION_CONFIGS = {
    "hubspot": {
        "name": "HubSpot",
        "oauth_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write"],
        "client_id": "hubspot_client_id_placeholder",
        "fields": ["api_key", "portal_id"]
    },
    "salesforce": {
        "name": "Salesforce",
        "oauth_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "scopes": ["api", "refresh_token"],
        "client_id": "salesforce_client_id_placeholder",
        "fields": ["username", "password", "security_token"]
    },
    "slack": {
        "name": "Slack",
        "oauth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": ["chat:write", "channels:read"],
        "client_id": "slack_client_id_placeholder",
        "fields": ["webhook_url"]
    },
    "gmail": {
        "name": "Gmail",
        "oauth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/gmail.send"],
        "client_id": "gmail_client_id_placeholder",
        "fields": ["email", "app_password"]
    },
    "github": {
        "name": "GitHub",
        "oauth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["repo", "read:user"],
        "client_id": "github_client_id_placeholder",
        "fields": ["token"]
    }
}

# Integration storage with credentials (encrypted in production)
INTEGRATIONS = {}

# Initialize all integrations as disconnected
for key in INTEGRATION_CONFIGS.keys():
    INTEGRATIONS[key] = {
        "status": "disconnected",
        "last_sync": None,
        "connected_at": None,
        "credentials": {},
        "settings": {},
        "sync_enabled": False
    }


class ConnectCredentials(BaseModel):
    credentials: Dict[str, Any]


class IntegrationSettings(BaseModel):
    sync_enabled: bool
    settings: Optional[Dict[str, Any]] = {}


@router.get("/integrations")
def get_all_integrations(api_key: str = Depends(get_api_key)):
    """Get all integration statuses"""
    return {
        "status": "success",
        "integrations": {
            k: {
                "status": v["status"],
                "last_sync": v["last_sync"],
                "connected_at": v["connected_at"],
                "sync_enabled": v["sync_enabled"],
                "name": INTEGRATION_CONFIGS.get(k, {}).get("name", k.title())
            }
            for k, v in INTEGRATIONS.items()
        }
    }


@router.get("/integrations/{integration_name}")
def get_integration_status(integration_name: str, api_key: str = Depends(get_api_key)):
    """Get detailed status of specific integration"""
    integration = INTEGRATIONS.get(integration_name.lower())
    config = INTEGRATION_CONFIGS.get(integration_name.lower())
    
    if not integration or not config:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    return {
        "status": "success",
        "integration": {
            **integration,
            "name": config["name"],
            "oauth_available": True,
            "fields": config["fields"]
        }
    }


@router.post("/integrations/{integration_name}/connect")
def connect_integration(
    integration_name: str,
    creds: ConnectCredentials,
    api_key: str = Depends(get_api_key)
):
    """Connect an integration with API credentials"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    # Validate required fields
    config = INTEGRATION_CONFIGS[name]
    provided_fields = set(creds.credentials.keys())
    required_fields = set(config["fields"])
    
    missing = required_fields - provided_fields
    if missing:
        raise HTTPException(
            status_code=400, 
            detail=f"Missing required fields: {', '.join(missing)}"
        )
    
    # In production, validate credentials with the actual service
    # For demo, we simulate a successful connection
    
    INTEGRATIONS[name] = {
        "status": "connected",
        "last_sync": None,
        "connected_at": datetime.now().isoformat(),
        "credentials": creds.credentials,  # In production: encrypt these
        "settings": {},
        "sync_enabled": False
    }
    
    return {
        "status": "success",
        "message": f"Connected to {config['name']}",
        "integration": {
            "name": config["name"],
            "status": "connected",
            "connected_at": INTEGRATIONS[name]["connected_at"]
        }
    }


@router.post("/integrations/{integration_name}/disconnect")
def disconnect_integration(integration_name: str, api_key: str = Depends(get_api_key)):
    """Disconnect an integration and clear credentials"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    config = INTEGRATION_CONFIGS[name]
    
    # Clear all connection data
    INTEGRATIONS[name] = {
        "status": "disconnected",
        "last_sync": None,
        "connected_at": None,
        "credentials": {},
        "settings": {},
        "sync_enabled": False
    }
    
    return {
        "status": "success",
        "message": f"Disconnected from {config['name']}"
    }


@router.get("/integrations/{integration_name}/oauth/initiate")
def initiate_oauth(integration_name: str, redirect_uri: str, api_key: str = Depends(get_api_key)):
    """Initiate OAuth flow for an integration - redirects to themed sign-in page"""
    name = integration_name.lower()
    
    if name not in INTEGRATION_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    config = INTEGRATION_CONFIGS[name]
    
    # Generate state token
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {
        "integration": name,
        "redirect_uri": redirect_uri,
        "created_at": time.time()
    }
    
    # Build our mock OAuth provider URL with themed sign-in page
    # In production, this would be the real OAuth URL from the provider
    provider_url = f"{redirect_uri.replace('/oauth-callback.html', '')}/oauth-provider.html"
    
    oauth_params = {
        "integration": name,
        "state": state,
        "redirect_uri": redirect_uri,
        "client_id": config["client_id"]
    }
    
    # Build URL with all params
    oauth_url = provider_url + "?" + "&".join([f"{k}={v}" for k, v in oauth_params.items()])
    
    return {
        "status": "success",
        "oauth_url": oauth_url,
        "state": state,
        "integration": name,
        "provider": config["name"]
    }


@router.post("/integrations/oauth/callback")
def oauth_callback(
    state: str,
    code: str,
    api_key: str = Depends(get_api_key)
):
    """Handle OAuth callback with full token exchange"""
    if state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    
    state_data = oauth_states[state]
    integration = state_data["integration"]
    config = INTEGRATION_CONFIGS[integration]
    
    # In production: make actual token exchange request to provider
    # POST to config["token_url"] with code, client_id, client_secret, redirect_uri
    # For demo: simulate successful token exchange
    
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    expires_in = 3600  # 1 hour
    expires_at = datetime.now().timestamp() + expires_in
    
    # Store complete OAuth credentials
    INTEGRATIONS[integration] = {
        "status": "connected",
        "last_sync": None,
        "connected_at": datetime.now().isoformat(),
        "credentials": {
            "type": "oauth",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "expires_in": expires_in,
            "token_type": "Bearer",
            "scope": " ".join(config["scopes"])
        },
        "settings": {},
        "sync_enabled": False
    }
    
    # Clean up state
    del oauth_states[state]
    
    return {
        "status": "success",
        "message": f"Connected via OAuth to {config['name']}",
        "integration": integration,
        "token": access_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "refresh_token": refresh_token[:10] + "..."  # Partial for security
    }


@router.post("/integrations/{integration_name}/oauth/refresh")
def refresh_oauth_token(integration_name: str, api_key: str = Depends(get_api_key)):
    """Refresh OAuth access token using refresh token"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    integration = INTEGRATIONS[name]
    
    if integration["status"] != "connected":
        raise HTTPException(status_code=400, detail="Integration is not connected")
    
    credentials = integration.get("credentials", {})
    
    if credentials.get("type") != "oauth":
        raise HTTPException(status_code=400, detail="Integration is not using OAuth")
    
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token available")
    
    # In production: make actual refresh request to provider
    # POST to config["token_url"] with refresh_token, grant_type=refresh_token
    # For demo: simulate successful refresh
    
    new_access_token = secrets.token_urlsafe(32)
    new_refresh_token = secrets.token_urlsafe(32)
    expires_in = 3600
    expires_at = datetime.now().timestamp() + expires_in
    
    # Update stored credentials
    INTEGRATIONS[name]["credentials"]["access_token"] = new_access_token
    INTEGRATIONS[name]["credentials"]["refresh_token"] = new_refresh_token
    INTEGRATIONS[name]["credentials"]["expires_at"] = expires_at
    INTEGRATIONS[name]["credentials"]["expires_in"] = expires_in
    
    return {
        "status": "success",
        "message": "Token refreshed successfully",
        "token": new_access_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "refresh_token": new_refresh_token[:10] + "..."
    }


@router.get("/integrations/{integration_name}/oauth/status")
def get_oauth_status(integration_name: str, api_key: str = Depends(get_api_key)):
    """Get OAuth token status and expiration"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    integration = INTEGRATIONS[name]
    credentials = integration.get("credentials", {})
    
    if credentials.get("type") != "oauth":
        return {
            "status": "info",
            "message": "Integration is using API credentials, not OAuth",
            "auth_type": "api_key"
        }
    
    expires_at = credentials.get("expires_at", 0)
    now = datetime.now().timestamp()
    is_expired = now > expires_at
    expires_in = max(0, expires_at - now)
    
    return {
        "status": "success",
        "auth_type": "oauth",
        "token_type": credentials.get("token_type", "Bearer"),
        "expires_at": expires_at,
        "expires_in": int(expires_in),
        "is_expired": is_expired,
        "scope": credentials.get("scope", ""),
        "refresh_token_available": bool(credentials.get("refresh_token"))
    }


@router.get("/integrations/{integration_name}/settings")
def get_integration_settings(integration_name: str, api_key: str = Depends(get_api_key)):
    """Get integration-specific settings"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    integration = INTEGRATIONS[name]
    
    return {
        "status": "success",
        "settings": integration.get("settings", {}),
        "sync_enabled": integration.get("sync_enabled", False),
        "credentials_configured": bool(integration.get("credentials"))
    }


@router.post("/integrations/{integration_name}/settings")
def update_integration_settings(
    integration_name: str,
    settings: IntegrationSettings,
    api_key: str = Depends(get_api_key)
):
    """Update integration settings"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    INTEGRATIONS[name]["sync_enabled"] = settings.sync_enabled
    INTEGRATIONS[name]["settings"] = settings.settings or {}
    
    return {
        "status": "success",
        "message": "Settings updated"
    }


@router.post("/integrations/{integration_name}/sync")
def trigger_sync(
    integration_name: str,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key)
):
    """Trigger a manual sync for an integration"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    integration = INTEGRATIONS[name]
    
    if integration["status"] != "connected":
        raise HTTPException(status_code=400, detail="Integration is not connected")
    
    # In production: add actual sync task to background
    # For demo: just update last_sync
    integration["last_sync"] = datetime.now().isoformat()
    
    return {
        "status": "success",
        "message": f"Sync triggered for {INTEGRATION_CONFIGS[name]['name']}",
        "last_sync": integration["last_sync"]
    }


@router.post("/integrations/{integration_name}/webhook")
def handle_webhook(
    integration_name: str,
    payload: Dict[str, Any],
    api_key: str = Depends(get_api_key)
):
    """Receive webhooks from integrations"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    # In production: process webhook payload
    # For demo: just acknowledge receipt
    
    return {
        "status": "success",
        "message": f"Webhook received for {INTEGRATION_CONFIGS.get(name, {}).get('name', name)}"
    }


@router.get("/integrations/{integration_name}/test")
def test_connection(integration_name: str, api_key: str = Depends(get_api_key)):
    """Test if an integration connection is working"""
    name = integration_name.lower()
    
    if name not in INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Integration {integration_name} not found")
    
    integration = INTEGRATIONS[name]
    
    if integration["status"] != "connected":
        return {
            "status": "error",
            "connected": False,
            "message": "Integration is not connected"
        }
    
    # In production: make actual API call to test
    # For demo: simulate success
    
    return {
        "status": "success",
        "connected": True,
        "message": f"Connection to {INTEGRATION_CONFIGS[name]['name']} is working"
    }
