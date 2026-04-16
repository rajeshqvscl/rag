"""
Email webhook routes for handling email events
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from app.services.security_service import get_api_key

router = APIRouter()

@router.post("/email-webhook/incoming")
def handle_incoming_email(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """Handle incoming email webhook"""
    try:
        return {
            "status": "success",
            "message": "Email webhook processed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/email-webhook/status")
def get_webhook_status(
    api_key: str = Depends(get_api_key)
):
    """Get webhook status"""
    try:
        return {
            "status": "success",
            "webhook_enabled": True,
            "last_event": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
