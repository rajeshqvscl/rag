from fastapi import APIRouter, Query, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.cache_service_lru import cache_service
from app.models.database import Library, User
from app.config.database import get_db
import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

# Pydantic models for API
class LibraryCreate(BaseModel):
    company: str
    file_name: str
    file_type: Optional[str] = "unknown"
    confidence: Optional[str] = "High"
    tags: Optional[List[str]] = []
    metadata: Optional[Dict] = {}

class LibraryResponse(BaseModel):
    id: int
    company: str
    file_name: str
    file_path: str
    file_size: Optional[int]
    file_type: Optional[str]
    date_uploaded: str
    confidence: str
    tags: Optional[List[str]]
    metadata: Optional[Dict]
    created_at: str

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

@router.get("/library")
def get_library_data(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Get all processed documents in library (with caching)"""
    try:
        user = get_or_create_default_user(db)
        
        # Check cache first
        cached = cache_service.get_cached_library(user.id)
        if cached:
            return {
                "status": "success",
                "library": cached,
                "cached": True
            }
        
        # Fetch from database
        library = db.query(Library).filter(Library.user_id == user.id).order_by(Library.date_uploaded.desc()).all()
        
        library_list = []
        for item in library:
            library_list.append({
                "id": item.id,
                "company": item.company,
                "file_name": item.file_name,
                "file_path": item.file_path,
                "file_size": item.file_size,
                "file_type": item.file_type,
                "date_uploaded": item.date_uploaded.strftime("%Y-%m-%d %H:%M:%S"),
                "confidence": item.confidence,
                "tags": item.tags or [],
                "metadata": item.file_metadata or {}  # Keep as 'metadata' for frontend compatibility
            })
        
        # Cache the results
        cache_service.cache_library(user.id, library_list)
        
        return {
            "status": "success",
            "library": library_list,
            "cached": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/library/add")
def add_to_library(
    company: str = Query(..., description="Company name"),
    file_name: str = Query(..., description="File name"),
    confidence: str = Query(..., description="Confidence score"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Add processed document to library"""
    try:
        user = get_or_create_default_user(db)
        
        new_entry = Library(
            user_id=user.id,
            company=company,
            file_name=file_name,
            file_path="",  # Will be set in upload
            file_size=0,
            file_type="unknown",
            date_uploaded=datetime.utcnow(),
            confidence=confidence,
            tags=[],
            metadata={}
        )
        
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)
        
        return {
            "status": "success",
            "message": f"Added {company} to library",
            "entry": {
                "id": new_entry.id,
                "company": new_entry.company,
                "file_name": new_entry.file_name,
                "date_uploaded": new_entry.date_uploaded.strftime("%Y-%m-%d %H:%M:%S"),
                "confidence": new_entry.confidence
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/library/upload")
async def upload_to_library(
    company: str = Form(..., description="Company name"),
    file: UploadFile = File(..., description="PDF file to upload"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Upload PDF to pitch deck library"""
    try:
        user = get_or_create_default_user(db)
        
        # Create library directory if it doesn't exist
        library_dir = "data/library_files"
        os.makedirs(library_dir, exist_ok=True)
        
        # Save uploaded file
        file_path = os.path.join(library_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Add to library database
        new_entry = Library(
            user_id=user.id,
            company=company,
            file_name=file.filename,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            file_type=file.content_type or "application/pdf",
            date_uploaded=datetime.utcnow(),
            confidence="High",
            tags=[],
            metadata={"original_filename": file.filename}
        )
        
        db.add(new_entry)
        db.commit()
        db.refresh(new_entry)
        
        return {
            "status": "success",
            "message": f"Uploaded {file.filename} for {company}",
            "entry": {
                "id": new_entry.id,
                "company": new_entry.company,
                "file_name": new_entry.file_name,
                "file_path": new_entry.file_path,
                "file_size": new_entry.file_size,
                "date_uploaded": new_entry.date_uploaded.strftime("%Y-%m-%d %H:%M:%S"),
                "confidence": new_entry.confidence
            }
        }
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Upload failed: {str(e)}"
        }

@router.delete("/library/{company}")
def remove_from_library(
    company: str, 
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Remove document from library"""
    try:
        user = get_or_create_default_user(db)
        
        # Delete from database
        items = db.query(Library).filter(
            Library.company == company,
            Library.user_id == user.id
        ).all()
        
        for item in items:
            db.delete(item)
        
        db.commit()
        
        # Invalidate cache
        cache_service.invalidate_library(user.id)
        
        return {
            "status": "success",
            "message": f"Removed {company} from library ({len(items)} items)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
def get_cache_stats(api_key: str = Depends(get_api_key)):
    """Get cache statistics"""
    return {
        "status": "success",
        "cache_stats": cache_service.get_stats()
    }


@router.post("/cache/invalidate")
def invalidate_all_cache(api_key: str = Depends(get_api_key)):
    """Invalidate all caches (admin operation)"""
    cache_service.lru.clear()
    return {
        "status": "success",
        "message": "All caches invalidated"
    }

# Helper functions for email webhook integration
def get_library():
    """Load library data from file (legacy function for compatibility)"""
    import json
    import os
    library_file = "data/library.json"
    
    if os.path.exists(library_file):
        with open(library_file, "r") as f:
            return json.load(f)
    return []

def save_library(library_data):
    """Save library data to file (legacy function for compatibility)"""
    import json
    import os
    library_file = "data/library.json"
    os.makedirs(os.path.dirname(library_file), exist_ok=True)
    
    with open(library_file, "w") as f:
        json.dump(library_data, f, indent=2)
