"""
Multi-file upload routes for batch processing
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.models.database import Library, User
from app.config.database import get_db
from app.tasks import process_file_task
import os
import shutil
import json
from datetime import datetime
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class BatchUploadResponse(BaseModel):
    status: str
    message: str
    uploaded_files: List[Dict]
    failed_files: List[Dict]
    total_files: int
    success_count: int
    failure_count: int

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

@router.post("/upload/batch", response_model=BatchUploadResponse)
async def batch_upload(
    background_tasks: BackgroundTasks,
    company: str = Form(..., description="Company name"),
    files: List[UploadFile] = File(..., description="Files to upload"),
    process_immediately: bool = Form(True, description="Process files immediately"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Upload multiple files at once"""
    try:
        user = get_or_create_default_user(db)
        
        # Create upload directory
        upload_dir = f"data/uploads/{company}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(upload_dir, exist_ok=True)
        
        uploaded_files = []
        failed_files = []
        
        for file in files:
            try:
                # Validate file
                if not file.filename:
                    failed_files.append({
                        "filename": "unknown",
                        "error": "No filename provided"
                    })
                    continue
                
                # Check file size (max 50MB)
                file_content = await file.read()
                if len(file_content) > 50 * 1024 * 1024:
                    failed_files.append({
                        "filename": file.filename,
                        "error": "File too large (max 50MB)"
                    })
                    continue
                
                # Save file
                file_path = os.path.join(upload_dir, file.filename)
                with open(file_path, "wb") as f:
                    f.write(file_content)
                
                # Add to library
                library_entry = Library(
                    user_id=user.id,
                    company=company,
                    file_name=file.filename,
                    file_path=file_path,
                    file_size=len(file_content),
                    file_type=file.content_type or "application/octet-stream",
                    date_uploaded=datetime.utcnow(),
                    confidence="High",
                    tags=["batch_upload"],
                    metadata={
                        "upload_batch": upload_dir.split("/")[-1],
                        "original_filename": file.filename,
                        "content_type": file.content_type
                    }
                )
                
                db.add(library_entry)
                db.commit()
                db.refresh(library_entry)
                
                uploaded_files.append({
                    "filename": file.filename,
                    "size": len(file_content),
                    "path": file_path,
                    "library_id": library_entry.id,
                    "content_type": file.content_type
                })
                
                # Process file in background if requested
                if process_immediately:
                    background_tasks.add_task(
                        process_file_task,
                        file_path=file_path,
                        file_name=file.filename,
                        company=company
                    )
                
            except Exception as e:
                failed_files.append({
                    "filename": file.filename if file.filename else "unknown",
                    "error": str(e)
                })
                continue
        
        return BatchUploadResponse(
            status="success",
            message=f"Batch upload completed. {len(uploaded_files)} files uploaded, {len(failed_files)} failed.",
            uploaded_files=uploaded_files,
            failed_files=failed_files,
            total_files=len(files),
            success_count=len(uploaded_files),
            failure_count=len(failed_files)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload/status/{batch_id}")
def get_batch_status(
    batch_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get status of batch upload processing"""
    try:
        user = get_or_create_default_user(db)
        
        # Get files from this batch
        batch_files = db.query(Library).filter(
            and_(
                Library.user_id == user.id,
                Library.metadata['upload_batch'].astext == batch_id
            )
        ).all()
        
        processed_files = []
        pending_files = []
        
        for file in batch_files:
            file_info = {
                "id": file.id,
                "filename": file.file_name,
                "size": file.file_size,
                "upload_time": file.date_uploaded.isoformat()
            }
            
            # Check if file has been processed (has analysis results)
            if file.metadata and "processed" in file.metadata:
                processed_files.append(file_info)
            else:
                pending_files.append(file_info)
        
        return {
            "status": "success",
            "batch_id": batch_id,
            "total_files": len(batch_files),
            "processed_files": processed_files,
            "pending_files": pending_files,
            "completion_percentage": (len(processed_files) / len(batch_files) * 100) if batch_files else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload/process/{file_id}")
def process_uploaded_file(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Process a single uploaded file"""
    try:
        user = get_or_create_default_user(db)
        
        file_record = db.query(Library).filter(
            and_(Library.id == file_id, Library.user_id == user.id)
        ).first()
        
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Process file in background
        background_tasks.add_task(
            process_file_task,
            file_path=file_record.file_path,
            file_name=file_record.file_name,
            company=file_record.company
        )
        
        # Mark as being processed
        if not file_record.metadata:
            file_record.metadata = {}
        file_record.metadata["processing_started"] = datetime.utcnow().isoformat()
        db.commit()
        
        return {
            "status": "success",
            "message": f"Processing started for {file_record.file_name}",
            "file_id": file_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
