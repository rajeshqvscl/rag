"""
AI sentiment analysis and risk assessment routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.sentiment_service import sentiment_service
from app.models.database import User
from app.config.database import get_db
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class TextSentimentRequest(BaseModel):
    text: str

class CompanySentimentRequest(BaseModel):
    company: str
    user_id: Optional[int] = 1

class BatchSentimentRequest(BaseModel):
    companies: List[str]
    user_id: Optional[int] = 1

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

@router.post("/sentiment/analyze-text")
def analyze_text_sentiment(
    request: TextSentimentRequest,
    api_key: str = Depends(get_api_key)
):
    """Analyze sentiment of text content"""
    try:
        sentiment = sentiment_service.analyze_text_sentiment(request.text)
        
        if "error" in sentiment:
            raise HTTPException(status_code=500, detail=sentiment["error"])
        
        return {
            "status": "success",
            "text_length": len(request.text),
            "sentiment_analysis": sentiment
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sentiment/assess-risk")
def assess_financial_risk(
    request: TextSentimentRequest,
    api_key: str = Depends(get_api_key)
):
    """Assess financial risk indicators in text"""
    try:
        risk_assessment = sentiment_service.assess_financial_risk(request.text)
        
        if "error" in risk_assessment:
            raise HTTPException(status_code=500, detail=risk_assessment["error"])
        
        return {
            "status": "success",
            "text_length": len(request.text),
            "risk_assessment": risk_assessment
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sentiment/company-analysis")
def analyze_company_sentiment(
    request: CompanySentimentRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Analyze sentiment across all data for a company"""
    try:
        user = get_or_create_default_user(db)
        
        analysis = sentiment_service.analyze_company_sentiment(request.company, request.user_id)
        
        if "error" in analysis:
            raise HTTPException(status_code=404, detail=analysis["error"])
        
        return {
            "status": "success",
            "company_analysis": analysis
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sentiment/company/{company}")
def get_company_sentiment(
    company: str,
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get sentiment analysis for a company (GET endpoint)"""
    try:
        user = get_or_create_default_user(db)
        
        analysis = sentiment_service.analyze_company_sentiment(company, user_id)
        
        if "error" in analysis:
            raise HTTPException(status_code=404, detail=analysis["error"])
        
        return {
            "status": "success",
            "company_analysis": analysis
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sentiment/batch-analysis")
def batch_sentiment_analysis(
    request: BatchSentimentRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Perform sentiment analysis for multiple companies"""
    try:
        user = get_or_create_default_user(db)
        
        results = sentiment_service.batch_sentiment_analysis(request.companies, request.user_id)
        
        if "error" in results:
            raise HTTPException(status_code=500, detail=results["error"])
        
        return {
            "status": "success",
            "batch_results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sentiment/portfolio-overview")
def get_portfolio_sentiment_overview(
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get sentiment overview for entire portfolio"""
    try:
        user = get_or_create_default_user(db)
        
        # Get all unique companies from drafts and library
        from app.models.database import Draft, Library
        
        drafts = db.query(Draft).filter(Draft.user_id == user_id).all()
        library = db.query(Library).filter(Library.user_id == user_id).all()
        
        companies = set()
        for draft in drafts:
            companies.add(draft.company)
        
        for item in library:
            companies.add(item.company)
        
        companies = list(companies)
        
        # Perform batch analysis
        results = sentiment_service.batch_sentiment_analysis(companies, user_id)
        
        if "error" in results:
            raise HTTPException(status_code=500, detail=results["error"])
        
        # Generate portfolio insights
        portfolio_insights = {
            "total_companies": len(companies),
            "sentiment_distribution": results["sentiment_summary"],
            "risk_distribution": results["risk_summary"],
            "top_performers": [],
            "high_risk_companies": [],
            "recommendations": []
        }
        
        # Identify top performers and high risk companies
        for company, analysis in results["company_analyses"].items():
            sentiment = analysis.get("overall_sentiment", "neutral")
            risk_level = analysis.get("risk_assessment", {}).get("risk_level", "low")
            
            if sentiment == "positive" and risk_level == "low":
                portfolio_insights["top_performers"].append({
                    "company": company,
                    "sentiment_score": analysis.get("overall_score", 0),
                    "risk_score": analysis.get("risk_assessment", {}).get("overall_risk_score", 0)
                })
            
            if risk_level == "high":
                portfolio_insights["high_risk_companies"].append({
                    "company": company,
                    "risk_score": analysis.get("risk_assessment", {}).get("overall_risk_score", 0),
                    "sentiment": sentiment
                })
        
        # Sort top performers by sentiment score
        portfolio_insights["top_performers"].sort(
            key=lambda x: x["sentiment_score"], 
            reverse=True
        )
        
        # Sort high risk companies by risk score
        portfolio_insights["high_risk_companies"].sort(
            key=lambda x: x["risk_score"], 
            reverse=True
        )
        
        # Generate portfolio recommendations
        positive_count = results["sentiment_summary"]["positive"]
        total_count = sum(results["sentiment_summary"].values())
        
        if total_count > 0:
            positive_ratio = positive_count / total_count
            
            if positive_ratio > 0.7:
                portfolio_insights["recommendations"].append("Portfolio shows strong positive sentiment")
            elif positive_ratio < 0.3:
                portfolio_insights["recommendations"].append("Portfolio shows concerning negative sentiment")
            else:
                portfolio_insights["recommendations"].append("Portfolio shows mixed sentiment - review individual companies")
        
        high_risk_count = results["risk_summary"]["high"]
        if high_risk_count > total_count * 0.3:
            portfolio_insights["recommendations"].append("High number of high-risk companies - consider diversification")
        
        return {
            "status": "success",
            "portfolio_overview": portfolio_insights,
            "detailed_analyses": results["company_analyses"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sentiment/trends")
def get_sentiment_trends(
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get sentiment trends over time"""
    try:
        user = get_or_create_default_user(db)
        
        # Get recent drafts with timestamps
        from app.models.database import Draft
        from datetime import datetime, timedelta
        
        drafts = db.query(Draft).filter(Draft.user_id == user_id).order_by(Draft.created_at.desc()).limit(50).all()
        
        trends = {
            "time_series": [],
            "sentiment_trend": "stable",
            "risk_trend": "stable"
        }
        
        sentiment_scores = []
        risk_scores = []
        
        for draft in drafts:
            text_content = f"{draft.company} {draft.analysis or ''} {draft.email_draft or ''}"
            sentiment = sentiment_service.analyze_text_sentiment(text_content)
            risk = sentiment_service.assess_financial_risk(text_content)
            
            if "score" in sentiment and "overall_risk_score" in risk:
                sentiment_scores.append(sentiment["score"])
                risk_scores.append(risk["overall_risk_score"])
                
                trends["time_series"].append({
                    "date": draft.created_at.isoformat(),
                    "company": draft.company,
                    "sentiment_score": sentiment["score"],
                    "risk_score": risk["overall_risk_score"]
                })
        
        # Calculate trends
        if len(sentiment_scores) > 5:
            # Compare recent vs older sentiment
            recent_avg = np.mean(sentiment_scores[:5])  # Most recent
            older_avg = np.mean(sentiment_scores[-5:])  # Older
            
            if recent_avg > older_avg + 0.1:
                trends["sentiment_trend"] = "improving"
            elif recent_avg < older_avg - 0.1:
                trends["sentiment_trend"] = "declining"
        
        if len(risk_scores) > 5:
            recent_avg_risk = np.mean(risk_scores[:5])
            older_avg_risk = np.mean(risk_scores[-5:])
            
            if recent_avg_risk > older_avg_risk + 0.1:
                trends["risk_trend"] = "increasing"
            elif recent_avg_risk < older_avg_risk - 0.1:
                trends["risk_trend"] = "decreasing"
        
        return {
            "status": "success",
            "sentiment_trends": trends
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sentiment/alerts")
def get_sentiment_alerts(
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get sentiment-based alerts and warnings"""
    try:
        user = get_or_create_default_user(db)
        
        # Get portfolio overview
        portfolio_result = sentiment_service.batch_sentiment_analysis([], user_id)
        
        alerts = {
            "critical_alerts": [],
            "warnings": [],
            "notifications": [],
            "summary": {
                "total_alerts": 0,
                "alert_types": {"critical": 0, "warning": 0, "notification": 0}
            }
        }
        
        # Generate alerts based on portfolio analysis
        if "company_analyses" in portfolio_result:
            for company, analysis in portfolio_result["company_analyses"].items():
                sentiment = analysis.get("overall_sentiment", "neutral")
                risk_level = analysis.get("risk_assessment", {}).get("risk_level", "low")
                risk_score = analysis.get("risk_assessment", {}).get("overall_risk_score", 0)
                
                # Critical alerts
                if sentiment == "negative" and risk_level == "high":
                    alerts["critical_alerts"].append({
                        "company": company,
                        "message": "High risk company with negative sentiment detected",
                        "severity": "critical",
                        "risk_score": risk_score
                    })
                    alerts["summary"]["alert_types"]["critical"] += 1
                
                elif risk_score > 0.8:
                    alerts["critical_alerts"].append({
                        "company": company,
                        "message": f"Very high risk score ({risk_score:.2f}) detected",
                        "severity": "critical",
                        "risk_score": risk_score
                    })
                    alerts["summary"]["alert_types"]["critical"] += 1
                
                # Warnings
                elif sentiment == "negative" and risk_level == "medium":
                    alerts["warnings"].append({
                        "company": company,
                        "message": "Negative sentiment with medium risk",
                        "severity": "warning",
                        "risk_score": risk_score
                    })
                    alerts["summary"]["alert_types"]["warning"] += 1
                
                elif risk_score > 0.6:
                    alerts["warnings"].append({
                        "company": company,
                        "message": f"Elevated risk score ({risk_score:.2f})",
                        "severity": "warning",
                        "risk_score": risk_score
                    })
                    alerts["summary"]["alert_types"]["warning"] += 1
                
                # Notifications
                elif sentiment == "positive" and risk_level == "low":
                    alerts["notifications"].append({
                        "company": company,
                        "message": "Positive sentiment with low risk",
                        "severity": "info",
                        "risk_score": risk_score
                    })
                    alerts["summary"]["alert_types"]["notification"] += 1
        
        # Calculate total alerts
        alerts["summary"]["total_alerts"] = (
            alerts["summary"]["alert_types"]["critical"] +
            alerts["summary"]["alert_types"]["warning"] +
            alerts["summary"]["alert_types"]["notification"]
        )
        
        return {
            "status": "success",
            "sentiment_alerts": alerts
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
