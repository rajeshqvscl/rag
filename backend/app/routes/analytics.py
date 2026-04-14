"""
Analytics routes for dashboard and system metrics
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from app.services.security_service import get_api_key
from app.models.database import Draft, Library, Conversation, Memory, Analytics, User
from app.config.database import get_db
from datetime import datetime, timedelta
from typing import List, Dict, Optional

router = APIRouter()

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

@router.get("/analytics/dashboard")
def get_dashboard_analytics(
    days: int = Query(30, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get comprehensive dashboard analytics"""
    try:
        user = get_or_create_default_user(db)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Drafts analytics
        total_drafts = db.query(Draft).filter(Draft.user_id == user.id).count()
        recent_drafts = db.query(Draft).filter(
            and_(Draft.user_id == user.id, Draft.created_at >= start_date)
        ).count()
        
        # Library analytics
        total_library = db.query(Library).filter(Library.user_id == user.id).count()
        recent_library = db.query(Library).filter(
            and_(Library.user_id == user.id, Library.created_at >= start_date)
        ).count()
        
        # Conversation analytics
        total_conversations = db.query(Conversation).filter(Conversation.user_id == user.id).count()
        recent_conversations = db.query(Conversation).filter(
            and_(Conversation.user_id == user.id, Conversation.timestamp >= start_date)
        ).count()
        
        # Memory analytics
        total_memories = db.query(Memory).filter(Memory.user_id == user.id).count()
        
        # Activity timeline
        activity_data = []
        for i in range(days):
            date = start_date + timedelta(days=i)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            drafts_count = db.query(Draft).filter(
                and_(
                    Draft.user_id == user.id,
                    Draft.created_at >= day_start,
                    Draft.created_at <= day_end
                )
            ).count()
            
            conversations_count = db.query(Conversation).filter(
                and_(
                    Conversation.user_id == user.id,
                    Conversation.timestamp >= day_start,
                    Conversation.timestamp <= day_end
                )
            ).count()
            
            library_count = db.query(Library).filter(
                and_(
                    Library.user_id == user.id,
                    Library.created_at >= day_start,
                    Library.created_at <= day_end
                )
            ).count()
            
            activity_data.append({
                "date": date.strftime("%Y-%m-%d"),
                "drafts": drafts_count,
                "conversations": conversations_count,
                "library": library_count
            })
        
        # Top companies
        top_companies = db.query(
            Draft.company, func.count(Draft.id).label('count')
        ).filter(Draft.user_id == user.id).group_by(
            Draft.company
        ).order_by(desc('count')).limit(10).all()
        
        # Confidence distribution
        confidence_dist = db.query(
            Draft.confidence, func.count(Draft.id).label('count')
        ).filter(Draft.user_id == user.id).group_by(Draft.confidence).all()
        
        return {
            "status": "success",
            "summary": {
                "total_drafts": total_drafts,
                "recent_drafts": recent_drafts,
                "total_library": total_library,
                "recent_library": recent_library,
                "total_conversations": total_conversations,
                "recent_conversations": recent_conversations,
                "total_memories": total_memories
            },
            "activity_timeline": activity_data,
            "top_companies": [{"company": company, "count": count} for company, count in top_companies],
            "confidence_distribution": [{"confidence": conf, "count": count} for conf, count in confidence_dist]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/performance")
def get_performance_metrics(
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get system performance metrics"""
    try:
        user = get_or_create_default_user(db)
        
        # Database performance
        draft_count = db.query(Draft).filter(Draft.user_id == user.id).count()
        library_count = db.query(Library).filter(Library.user_id == user.id).count()
        conversation_count = db.query(Conversation).filter(Conversation.user_id == user.id).count()
        memory_count = db.query(Memory).filter(Memory.user_id == user.id).count()
        
        # Storage metrics
        total_files = db.query(Library).filter(Library.user_id == user.id).count()
        file_sizes = db.query(func.sum(Library.file_size)).filter(Library.user_id == user.id).scalar() or 0
        
        # Recent activity
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)
        
        hourly_drafts = db.query(Draft).filter(
            and_(Draft.user_id == user.id, Draft.created_at >= hour_ago)
        ).count()
        
        hourly_conversations = db.query(Conversation).filter(
            and_(Conversation.user_id == user.id, Conversation.timestamp >= hour_ago)
        ).count()
        
        daily_drafts = db.query(Draft).filter(
            and_(Draft.user_id == user.id, Draft.created_at >= day_ago)
        ).count()
        
        daily_conversations = db.query(Conversation).filter(
            and_(Conversation.user_id == user.id, Conversation.timestamp >= day_ago)
        ).count()
        
        return {
            "status": "success",
            "database": {
                "drafts": draft_count,
                "library": library_count,
                "conversations": conversation_count,
                "memories": memory_count
            },
            "storage": {
                "total_files": total_files,
                "total_size_bytes": file_sizes,
                "total_size_mb": round(file_sizes / (1024 * 1024), 2)
            },
            "activity": {
                "hourly_drafts": hourly_drafts,
                "hourly_conversations": hourly_conversations,
                "daily_drafts": daily_drafts,
                "daily_conversations": daily_conversations
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analytics/track")
def track_event(
    event_type: str,
    event_data: Dict,
    session_id: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Track analytics event"""
    try:
        user = get_or_create_default_user(db)
        
        event = Analytics(
            user_id=user.id,
            event_type=event_type,
            event_data=event_data,
            session_id=session_id or f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.utcnow()
        )
        
        db.add(event)
        db.commit()
        
        return {
            "status": "success",
            "message": f"Event {event_type} tracked successfully"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
