"""
Email reply generation routes
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.security_service import get_api_key
from pydantic import BaseModel

router = APIRouter()

class EmailReplyRequest(BaseModel):
    company: str
    context: str
    tone: str = "professional"

@router.post("/email-reply/generate")
def generate_email_reply(
    request: EmailReplyRequest,
    api_key: str = Depends(get_api_key)
):
    """Generate an email reply"""
    try:
        return {
            "status": "success",
            "reply": "Generated email reply content",
            "draft_id": "new-draft-id"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/email-reply/drafts")
def get_email_reply_drafts(
    limit: int = 10,
    api_key: str = Depends(get_api_key)
):
    """Get email reply drafts"""
    try:
        return {
            "status": "success",
            "drafts": []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
