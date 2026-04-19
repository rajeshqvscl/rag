"""
Collaboration routes for team features
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.security_service import get_api_key

router = APIRouter()

@router.get("/collaboration/team")
def get_team_members(
    api_key: str = Depends(get_api_key)
):
    """Get team members"""
    try:
        return {
            "status": "success",
            "members": []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collaboration/share")
def share_document(
    document_id: str,
    user_ids: list[str],
    api_key: str = Depends(get_api_key)
):
    """Share document with team"""
    try:
        return {
            "status": "success",
            "message": "Document shared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
