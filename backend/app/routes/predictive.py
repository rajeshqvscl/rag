"""
Predictive analytics routes for financial forecasting and insights
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.security_service import get_api_key
from app.services.predictive_service import predictive_service
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class ActivityTrendRequest(BaseModel):
    user_id: Optional[int] = 1
    days_ahead: int = 30

class CompanyPerformanceRequest(BaseModel):
    company: str
    user_id: Optional[int] = 1

class RevenueGrowthRequest(BaseModel):
    company: str
    user_id: Optional[int] = 1

@router.post("/predictive/activity-trends")
def predict_activity_trends(
    request: ActivityTrendRequest,
    api_key: str = Depends(get_api_key)
):
    """Predict activity trends for the next N days"""
    try:
        predictions = predictive_service.predict_activity_trends(
            request.user_id, 
            request.days_ahead
        )
        
        if "error" in predictions:
            raise HTTPException(status_code=500, detail=predictions["error"])
        
        return {
            "status": "success",
            "predictions": predictions,
            "forecast_period": f"{request.days_ahead} days",
            "generated_at": predictions.get("generated_at", "N/A")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/activity-trends")
def get_activity_trends(
    days_ahead: int = Query(30, description="Number of days to predict"),
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get activity trends prediction (GET endpoint)"""
    try:
        predictions = predictive_service.predict_activity_trends(user_id, days_ahead)
        
        if "error" in predictions:
            raise HTTPException(status_code=500, detail=predictions["error"])
        
        return {
            "status": "success",
            "predictions": predictions,
            "forecast_period": f"{days_ahead} days"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predictive/company-performance")
def predict_company_performance(
    request: CompanyPerformanceRequest,
    api_key: str = Depends(get_api_key)
):
    """Predict company performance based on historical data"""
    try:
        performance = predictive_service.predict_company_performance(
            request.company,
            request.user_id
        )
        
        if "error" in performance:
            raise HTTPException(status_code=404, detail=performance["error"])
        
        return {
            "status": "success",
            "company": request.company,
            "performance_prediction": performance
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/company-performance/{company}")
def get_company_performance(
    company: str,
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get company performance prediction (GET endpoint)"""
    try:
        performance = predictive_service.predict_company_performance(company, user_id)
        
        if "error" in performance:
            raise HTTPException(status_code=404, detail=performance["error"])
        
        return {
            "status": "success",
            "company": company,
            "performance_prediction": performance
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predictive/revenue-growth")
def predict_revenue_growth(
    request: RevenueGrowthRequest,
    api_key: str = Depends(get_api_key)
):
    """Predict revenue growth based on pitch deck data"""
    try:
        revenue_prediction = predictive_service.predict_revenue_growth(
            request.company,
            request.user_id
        )
        
        if "error" in revenue_prediction:
            raise HTTPException(status_code=404, detail=revenue_prediction["error"])
        
        return {
            "status": "success",
            "company": request.company,
            "revenue_prediction": revenue_prediction
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/revenue-growth/{company}")
def get_revenue_growth(
    company: str,
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get revenue growth prediction (GET endpoint)"""
    try:
        revenue_prediction = predictive_service.predict_revenue_growth(company, user_id)
        
        if "error" in revenue_prediction:
            raise HTTPException(status_code=404, detail=revenue_prediction["error"])
        
        return {
            "status": "success",
            "company": company,
            "revenue_prediction": revenue_prediction
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/market-insights")
def get_market_insights(
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Generate market insights based on portfolio analysis"""
    try:
        insights = predictive_service.generate_market_insights(user_id)
        
        if "error" in insights:
            raise HTTPException(status_code=500, detail=insights["error"])
        
        return {
            "status": "success",
            "market_insights": insights
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/portfolio-analysis")
def get_portfolio_analysis(
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get comprehensive portfolio analysis"""
    try:
        # Get market insights
        insights = predictive_service.generate_market_insights(user_id)
        
        if "error" in insights:
            raise HTTPException(status_code=500, detail=insights["error"])
        
        # Get activity trends
        activity_trends = predictive_service.predict_activity_trends(user_id, 30)
        
        # Combine into portfolio analysis
        portfolio_analysis = {
            "portfolio_summary": {
                "total_companies": insights.get("total_companies", 0),
                "top_performers": insights.get("top_performers", []),
                "risk_distribution": insights.get("risk_assessment", {}).get("risk_distribution", {}),
                "recommendations": insights.get("recommendations", [])
            },
            "activity_forecast": activity_trends,
            "risk_assessment": insights.get("risk_assessment", {}),
            "investment_opportunities": [],
            "generated_at": "N/A"
        }
        
        # Identify investment opportunities
        top_performers = insights.get("top_performers", [])
        for performer in top_performers:
            if performer.get("confidence_ratio", 0) > 0.7:
                portfolio_analysis["investment_opportunities"].append({
                    "company": performer["company"],
                    "confidence_ratio": performer["confidence_ratio"],
                    "recommendation": "Consider increasing investment",
                    "risk_level": "Low"
                })
        
        # High-risk opportunities
        high_risk = insights.get("risk_assessment", {}).get("high_risk", [])
        for company in high_risk:
            portfolio_analysis["investment_opportunities"].append({
                "company": company,
                "confidence_ratio": 0,
                "recommendation": "Monitor closely - high risk",
                "risk_level": "High"
            })
        
        return {
            "status": "success",
            "portfolio_analysis": portfolio_analysis
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/summary")
def get_predictive_summary(
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get summary of all predictive analytics"""
    try:
        summary = {
            "activity_trends": {},
            "market_insights": {},
            "portfolio_health": {},
            "recommendations": []
        }
        
        # Get market insights
        insights = predictive_service.generate_market_insights(user_id)
        
        if "error" not in insights:
            summary["market_insights"] = {
                "total_companies": insights.get("total_companies", 0),
                "top_performer": insights.get("top_performers", [{}])[0].get("company", "N/A"),
                "risk_distribution": insights.get("risk_assessment", {}).get("risk_distribution", {})
            }
            
            # Add recommendations
            summary["recommendations"].extend(insights.get("recommendations", []))
        
        # Get activity trends
        activity_trends = predictive_service.predict_activity_trends(user_id, 7)  # 7 days
        
        if "error" not in activity_trends:
            summary["activity_trends"] = {
                "forecast_available": True,
                "trend_direction": "increasing" if len(activity_trends.get("overall_trend", [])) > 0 else "stable",
                "predicted_activity": sum(t.get("predicted_activity", 0) for t in activity_trends.get("overall_trend", []))
            }
        
        # Portfolio health assessment
        risk_dist = insights.get("risk_assessment", {}).get("risk_distribution", {})
        total_companies = sum(risk_dist.values())
        
        if total_companies > 0:
            low_risk_percentage = (risk_dist.get("low", 0) / total_companies) * 100
            
            if low_risk_percentage > 70:
                health_status = "Excellent"
            elif low_risk_percentage > 50:
                health_status = "Good"
            elif low_risk_percentage > 30:
                health_status = "Moderate"
            else:
                health_status = "Poor"
            
            summary["portfolio_health"] = {
                "status": health_status,
                "low_risk_percentage": low_risk_percentage,
                "total_companies": total_companies
            }
        
        return {
            "status": "success",
            "predictive_summary": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictive/model-status")
def get_model_status(api_key: str = Depends(get_api_key)):
    """Get status of predictive models"""
    try:
        model_status = {
            "available_models": ["linear", "random_forest"],
            "active_models": ["linear"],
            "model_performance": {
                "activity_trends": "Good",
                "company_performance": "Fair",
                "revenue_growth": "Good",
                "market_insights": "Good"
            },
            "data_requirements": {
                "activity_trends": "Minimum 2 data points",
                "company_performance": "Minimum 1 data point",
                "revenue_growth": "Minimum 2 revenue data points",
                "market_insights": "Minimum 1 company"
            },
            "limitations": [
                "Predictions are based on historical data patterns",
                "External market factors not considered",
                "Accuracy depends on data quality and quantity",
                "Models should be retrained periodically"
            ],
            "last_updated": "N/A"
        }
        
        return {
            "status": "success",
            "model_status": model_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
