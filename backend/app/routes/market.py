"""
Market data routes
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.security_service import get_api_key

router = APIRouter()

@router.get("/market/stocks/{symbol}")
def get_stock_data(
    symbol: str,
    api_key: str = Depends(get_api_key)
):
    """Get stock market data"""
    try:
        return {
            "status": "success",
            "symbol": symbol,
            "price": 0.0,
            "change": 0.0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/news")
def get_market_news(
    limit: int = 10,
    api_key: str = Depends(get_api_key)
):
    """Get market news"""
    try:
        return {
            "status": "success",
            "news": []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
