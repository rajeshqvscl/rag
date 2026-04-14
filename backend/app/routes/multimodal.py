"""
Multi-modal analysis routes for pitch deck processing
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.multimodal_service import multimodal_service
from app.models.database import Library, User
from app.config.database import get_db
from typing import List, Dict, Optional
from pydantic import BaseModel
import os
import shutil
from datetime import datetime

router = APIRouter()

class MultiModalAnalysisRequest(BaseModel):
    company: str
    file_path: str

class MultiModalResponse(BaseModel):
    status: str
    company: str
    analysis: Dict
    insights: Dict
    processed_at: str

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

@router.post("/multimodal/analyze")
def analyze_multimodal(
    request: MultiModalAnalysisRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Perform multi-modal analysis on uploaded file"""
    try:
        # Check if file exists
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Perform multi-modal analysis
        analysis = multimodal_service.process_pitch_deck_multimodal(
            request.file_path, 
            request.company
        )
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        # Generate insights
        insights = multimodal_service.generate_insights_from_multimodal(analysis)
        
        # Update library entry with multimodal analysis
        user = get_or_create_default_user(db)
        library_entry = db.query(Library).filter(
            Library.file_path == request.file_path,
            Library.user_id == user.id
        ).first()
        
        if library_entry:
            if not library_entry.metadata:
                library_entry.metadata = {}
            
            library_entry.metadata["multimodal_analysis"] = analysis
            library_entry.metadata["multimodal_insights"] = insights
            library_entry.metadata["multimodal_processed_at"] = datetime.utcnow().isoformat()
            
            # Add multimodal tag
            if not library_entry.tags:
                library_entry.tags = []
            if "multimodal" not in library_entry.tags:
                library_entry.tags.append("multimodal")
            
            db.commit()
        
        return MultiModalResponse(
            status="success",
            company=request.company,
            analysis=analysis,
            insights=insights,
            processed_at=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/multimodal/upload-analyze")
async def upload_and_analyze(
    company: str = Form(..., description="Company name"),
    file: UploadFile = File(..., description="File to analyze"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Upload file and perform multi-modal analysis"""
    try:
        user = get_or_create_default_user(db)
        
        # Create upload directory
        upload_dir = "data/multimodal_uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save uploaded file
        file_path = os.path.join(upload_dir, file.filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Add to library
        library_entry = Library(
            user_id=user.id,
            company=company,
            file_name=file.filename,
            file_path=file_path,
            file_size=os.path.getsize(file_path),
            file_type=file.content_type or "application/octet-stream",
            date_uploaded=datetime.utcnow(),
            confidence="High",
            tags=["multimodal", "uploaded"],
            metadata={"upload_type": "multimodal"}
        )
        
        db.add(library_entry)
        db.commit()
        db.refresh(library_entry)
        
        # Perform multi-modal analysis
        analysis = multimodal_service.process_pitch_deck_multimodal(file_path, company)
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        # Generate insights
        insights = multimodal_service.generate_insights_from_multimodal(analysis)
        
        # Update library entry with analysis results
        library_entry.metadata["multimodal_analysis"] = analysis
        library_entry.metadata["multimodal_insights"] = insights
        library_entry.metadata["multimodal_processed_at"] = datetime.utcnow().isoformat()
        db.commit()
        
        return {
            "status": "success",
            "message": f"File uploaded and analyzed: {file.filename}",
            "library_id": library_entry.id,
            "company": company,
            "analysis": analysis,
            "insights": insights,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/multimodal/analysis/{library_id}")
def get_multimodal_analysis(
    library_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get multi-modal analysis for a library item"""
    try:
        user = get_or_create_default_user(db)
        
        library_entry = db.query(Library).filter(
            Library.id == library_id,
            Library.user_id == user.id
        ).first()
        
        if not library_entry:
            raise HTTPException(status_code=404, detail="Library item not found")
        
        metadata = library_entry.metadata or {}
        
        return {
            "status": "success",
            "library_id": library_id,
            "company": library_entry.company,
            "file_name": library_entry.file_name,
            "multimodal_analysis": metadata.get("multimodal_analysis"),
            "multimodal_insights": metadata.get("multimodal_insights"),
            "processed_at": metadata.get("multimodal_processed_at"),
            "has_analysis": "multimodal_analysis" in metadata
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/multimodal/summary")
def get_multimodal_summary(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get summary of all multi-modal analyses"""
    try:
        user = get_or_create_default_user(db)
        
        # Get all library items with multimodal analysis
        library_items = db.query(Library).filter(
            Library.user_id == user.id,
            Library.metadata["multimodal_analysis"].isnot(None)
        ).all()
        
        summary = {
            "total_analyzed": len(library_items),
            "companies": [],
            "total_charts_found": 0,
            "total_financial_terms": set(),
            "analysis_types": {}
        }
        
        for item in library_items:
            metadata = item.metadata or {}
            analysis = metadata.get("multimodal_analysis", {})
            
            # Company info
            if item.company not in summary["companies"]:
                summary["companies"].append(item.company)
            
            # Charts count
            if "summary" in analysis:
                summary["total_charts_found"] += analysis["summary"].get("charts_found", 0)
                
                # Financial terms
                financial_terms = analysis["summary"].get("financial_terms_found", [])
                summary["total_financial_terms"].update(financial_terms)
            
            # Analysis types
            file_ext = os.path.splitext(item.file_name)[1].lower()
            if file_ext not in summary["analysis_types"]:
                summary["analysis_types"][file_ext] = 0
            summary["analysis_types"][file_ext] += 1
        
        summary["total_financial_terms"] = list(summary["total_financial_terms"])
        
        return {
            "status": "success",
            "summary": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/multimodal/insights/{company}")
def get_company_insights(
    company: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get multi-modal insights for a specific company"""
    try:
        user = get_or_create_default_user(db)
        
        # Get all library items for the company with multimodal analysis
        library_items = db.query(Library).filter(
            Library.user_id == user.id,
            Library.company == company,
            Library.metadata["multimodal_analysis"].isnot(None)
        ).all()
        
        if not library_items:
            raise HTTPException(status_code=404, detail="No multi-modal analysis found for this company")
        
        company_insights = {
            "company": company,
            "total_files": len(library_items),
            "insights": [],
            "common_themes": {},
            "recommendations": []
        }
        
        all_insights = []
        all_financial_terms = set()
        
        for item in library_items:
            metadata = item.metadata or {}
            insights = metadata.get("multimodal_insights", {})
            
            if insights:
                all_insights.append(insights)
                
                # Collect financial indicators
                financial_indicators = insights.get("financial_indicators", [])
                for indicator in financial_indicators:
                    all_financial_terms.add(indicator.get("term", ""))
                
                # Collect recommendations
                recommendations = insights.get("recommendations", [])
                company_insights["recommendations"].extend(recommendations)
        
        # Analyze common themes
        if all_financial_terms:
            company_insights["common_themes"]["financial_terms"] = list(all_financial_terms)
        
        # Generate company-level recommendations
        if len(library_items) > 1:
            company_insights["recommendations"].append(f"Comprehensive analysis across {len(library_items)} documents")
        
        company_insights["insights"] = all_insights
        
        return {
            "status": "success",
            "company_insights": company_insights
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/multimodal/reanalyze/{library_id}")
def reanalyze_file(
    library_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Re-analyze a file with multi-modal analysis"""
    try:
        user = get_or_create_default_user(db)
        
        library_entry = db.query(Library).filter(
            Library.id == library_id,
            Library.user_id == user.id
        ).first()
        
        if not library_entry:
            raise HTTPException(status_code=404, detail="Library item not found")
        
        # Perform new analysis
        analysis = multimodal_service.process_pitch_deck_multimodal(
            library_entry.file_path,
            library_entry.company
        )
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        # Generate new insights
        insights = multimodal_service.generate_insights_from_multimodal(analysis)
        
        # Update library entry
        if not library_entry.metadata:
            library_entry.metadata = {}
        
        library_entry.metadata["multimodal_analysis"] = analysis
        library_entry.metadata["multimodal_insights"] = insights
        library_entry.metadata["multimodal_processed_at"] = datetime.utcnow().isoformat()
        
        db.commit()
        
        return {
            "status": "success",
            "message": f"Re-analyzed file: {library_entry.file_name}",
            "analysis": analysis,
            "insights": insights,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
