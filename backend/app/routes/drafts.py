from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.cache_service_lru import cache_service
from app.models.database import Draft, User
from app.config.database import get_db
from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()

# Pydantic models for API
class DraftCreate(BaseModel):
    company: str
    status: str = "Draft"
    confidence: str = "Medium"
    analysis: Optional[str] = ""
    email_draft: Optional[str] = ""
    revenue_data: Optional[List[Dict]] = []
    files: Optional[List[Dict]] = []
    tags: Optional[List[str]] = []

class DraftResponse(BaseModel):
    id: int
    company: str
    date: str
    status: str
    confidence: str
    analysis: Optional[str]
    email_draft: Optional[str]
    revenue_data: Optional[List[Dict]]
    files: Optional[List[Dict]]
    tags: Optional[List[str]]
    created_at: str
    updated_at: str

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

@router.get("/drafts")
def get_drafts(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Get all pitch deck analysis drafts (with caching)"""
    try:
        user = get_or_create_default_user(db)
        
        # Check cache first
        cached = cache_service.get_cached_drafts(user.id)
        if cached:
            return {
                "status": "success",
                "drafts": cached,
                "cached": True
            }
        
        # Fetch from database
        drafts = db.query(Draft).filter(Draft.user_id == user.id).order_by(Draft.created_at.desc()).all()
        
        draft_list = []
        for draft in drafts:
            draft_list.append({
                "id": draft.id,
                "company": draft.company,
                "date": draft.date.strftime("%Y-%m-%d") if draft.date else "",
                "status": draft.status,
                "confidence": draft.confidence,
                "analysis": draft.analysis,
                "email_draft": draft.email_draft,
                "revenue_data": draft.revenue_data or [],
                "files": draft.files or [],
                "tags": draft.tags or [],
                "created_at": draft.created_at.isoformat(),
                "updated_at": draft.updated_at.isoformat()
            })
        
        # Cache the results
        cache_service.cache_draft_list(user.id, draft_list)
        
        return {
            "status": "success",
            "drafts": draft_list,
            "cached": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/drafts")
def create_draft(
    draft: DraftCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Create a new draft"""
    try:
        user = get_or_create_default_user(db)
        
        new_draft = Draft(
            user_id=user.id,
            company=draft.company,
            date=datetime.utcnow(),
            status=draft.status,
            confidence=draft.confidence,
            analysis=draft.analysis,
            email_draft=draft.email_draft,
            revenue_data=draft.revenue_data,
            files=draft.files,
            tags=draft.tags
        )
        
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        
        # Invalidate cache
        cache_service.invalidate_drafts(user.id)
        
        return {
            "status": "success",
            "message": f"Created draft for {draft.company}",
            "draft": {
                "id": new_draft.id,
                "company": new_draft.company,
                "date": new_draft.date.strftime("%Y-%m-%d"),
                "status": new_draft.status,
                "confidence": new_draft.confidence,
                "analysis": new_draft.analysis,
                "email_draft": new_draft.email_draft,
                "revenue_data": new_draft.revenue_data,
                "files": new_draft.files,
                "tags": new_draft.tags,
                "created_at": new_draft.created_at.isoformat(),
                "updated_at": new_draft.updated_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/drafts/{draft_id}")
def update_draft(
    draft_id: int,
    draft: DraftCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Update an existing draft"""
    try:
        user = get_or_create_default_user(db)
        
        existing_draft = db.query(Draft).filter(
            Draft.id == draft_id,
            Draft.user_id == user.id
        ).first()
        
        if not existing_draft:
            return {
                "status": "error",
                "message": f"Draft {draft_id} not found"
            }
        
        existing_draft.company = draft.company
        existing_draft.status = draft.status
        existing_draft.confidence = draft.confidence
        existing_draft.analysis = draft.analysis
        existing_draft.email_draft = draft.email_draft
        existing_draft.revenue_data = draft.revenue_data
        existing_draft.files = draft.files
        existing_draft.tags = draft.tags
        existing_draft.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing_draft)
        
        # Invalidate cache
        cache_service.invalidate_drafts(user.id)
        
        return {
            "status": "success",
            "message": f"Updated draft {draft_id}",
            "draft": {
                "id": existing_draft.id,
                "company": existing_draft.company,
                "date": existing_draft.date.strftime("%Y-%m-%d"),
                "status": existing_draft.status,
                "confidence": existing_draft.confidence,
                "analysis": existing_draft.analysis,
                "email_draft": existing_draft.email_draft,
                "revenue_data": existing_draft.revenue_data,
                "files": existing_draft.files,
                "tags": existing_draft.tags,
                "created_at": existing_draft.created_at.isoformat(),
                "updated_at": existing_draft.updated_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/drafts/{draft_id}")
def delete_draft(
    draft_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Delete a draft"""
    try:
        user = get_or_create_default_user(db)
        
        draft = db.query(Draft).filter(
            Draft.id == draft_id,
            Draft.user_id == user.id
        ).first()
        
        if draft:
            user_id = draft.user_id
            db.delete(draft)
            db.commit()
            
            # Invalidate cache
            cache_service.invalidate_drafts(user_id)
            
            return {
                "status": "success",
                "message": f"Deleted draft {draft_id}"
            }
        else:
            return {
                "status": "error",
                "message": f"Draft {draft_id} not found"
            }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Helper functions for email webhook integration
def save_drafts(drafts_data):
    """Save drafts data to file (legacy function for compatibility)"""
    import json
    import os
    drafts_file = "data/drafts.json"
    os.makedirs(os.path.dirname(drafts_file), exist_ok=True)
    
    existing_drafts = load_drafts()
    existing_drafts.extend(drafts_data)
    
    with open(drafts_file, "w") as f:
        json.dump(existing_drafts, f, indent=2)

def load_drafts():
    """Load drafts data from file (legacy function for compatibility)"""
    import json
    import os
    drafts_file = "data/drafts.json"
    
    if os.path.exists(drafts_file):
        with open(drafts_file, "r") as f:
            return json.load(f)
    return []
