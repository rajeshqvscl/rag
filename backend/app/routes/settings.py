from fastapi import APIRouter, Query, Depends
from app.services.security_service import get_api_key
import os
import json

router = APIRouter()

SETTINGS_FILE = "app/data/settings.json"

def get_settings():
    """Load settings from file"""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {
        "api_key": "sk-ant-api03-****************",
        "active_model": "claude-3-sonnet-20240229"
    }

def save_settings(settings_data):
    """Save settings to file"""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings_data, f, indent=2)

@router.get("/settings")
def get_all_settings(api_key: str = Depends(get_api_key)):
    """Get all system settings"""
    settings = get_settings()
    return {
        "status": "success",
        "settings": settings
    }

@router.post("/settings/update")
def update_settings(
    api_key: str = Query(None, description="Anthropic API key"),
    model: str = Query(None, description="Active LLM model"),
    api_key_param: str = Depends(get_api_key)
):
    """Update system settings"""
    settings = get_settings()
    
    if api_key:
        settings["api_key"] = api_key
    if model:
        settings["active_model"] = model
    
    save_settings(settings)
    
    return {
        "status": "success",
        "message": "Settings updated successfully",
        "settings": settings
    }

