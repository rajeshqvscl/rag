"""
Market data routes for real-time financial information
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.security_service import get_api_key
from app.services.market_service import market_service
from typing import List, Dict, Optional

router = APIRouter()

@router.get("/market/quote/{symbol}")
def get_stock_quote(
    symbol: str,
    api_key: str = Depends(get_api_key)
):
    """Get real-time stock quote"""
    try:
        quote = market_service.get_stock_quote(symbol.upper())
        market_service.track_request("stock_quote", {"symbol": symbol, "success": True})
        return {
            "status": "success",
            "quote": quote
        }
    except Exception as e:
        market_service.track_request("stock_quote", {"symbol": symbol, "success": False, "error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/quotes")
def get_multiple_quotes(
    symbols: str = Query(..., description="Comma-separated stock symbols"),
    api_key: str = Depends(get_api_key)
):
    """Get multiple stock quotes"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        quotes = {}
        
        for symbol in symbol_list:
            try:
                quotes[symbol] = market_service.get_stock_quote(symbol)
            except Exception as e:
                quotes[symbol] = {"error": str(e)}
        
        market_service.track_request("multiple_quotes", {"symbols": symbol_list, "count": len(quotes)})
        return {
            "status": "success",
            "quotes": quotes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/news")
def get_market_news(
    symbol: Optional[str] = Query(None, description="Filter news by symbol"),
    limit: int = Query(10, description="Number of news items"),
    api_key: str = Depends(get_api_key)
):
    """Get market news"""
    try:
        news = market_service.get_market_news(symbol, limit)
        market_service.track_request("market_news", {"symbol": symbol, "limit": limit, "count": len(news)})
        return {
            "status": "success",
            "news": news
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/sectors")
def get_sector_performance(api_key: str = Depends(get_api_key)):
    """Get sector performance data"""
    try:
        sectors = market_service.get_sector_performance()
        market_service.track_request("sectors", {"count": len(sectors)})
        return {
            "status": "success",
            "sectors": sectors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/indicators")
def get_market_indicators(api_key: str = Depends(get_api_key)):
    """Get major market indicators"""
    try:
        indicators = market_service.get_market_indicators()
        market_service.track_request("indicators", {"count": len(indicators)})
        return {
            "status": "success",
            "indicators": indicators
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/watchlist")
def get_watchlist_data(
    symbols: str = Query("AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA", description="Watchlist symbols"),
    api_key: str = Depends(get_api_key)
):
    """Get watchlist data with quotes and news"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        
        # Get quotes for all symbols
        quotes = {}
        for symbol in symbol_list:
            try:
                quotes[symbol] = market_service.get_stock_quote(symbol)
            except Exception as e:
                quotes[symbol] = {"error": str(e)}
        
        # Get general market news
        news = market_service.get_market_news(limit=5)
        
        # Get sector performance
        sectors = market_service.get_sector_performance()
        
        market_service.track_request("watchlist", {"symbols": symbol_list, "count": len(quotes)})
        return {
            "status": "success",
            "quotes": quotes,
            "news": news,
            "sectors": sectors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/alerts")
def get_market_alerts(
    watchlist: str = Query("AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA", description="Watchlist symbols"),
    api_key: str = Depends(get_api_key)
):
    """Get market alerts based on watchlist"""
    try:
        symbol_list = [s.strip().upper() for s in watchlist.split(",") if s.strip()]
        alerts = []
        
        for symbol in symbol_list:
            try:
                quote = market_service.get_stock_quote(symbol)
                
                # Generate alerts based on conditions
                if abs(quote.get("change_percent", 0)) > 5:  # Large price movement
                    alerts.append({
                        "type": "price_movement",
                        "symbol": symbol,
                        "message": f"{symbol} moved {quote.get('change_percent', 0):.2f}%",
                        "severity": "high" if abs(quote.get("change_percent", 0)) > 10 else "medium",
                        "data": quote
                    })
                
                if quote.get("volume", 0) > 10000000:  # High volume
                    alerts.append({
                        "type": "high_volume",
                        "symbol": symbol,
                        "message": f"{symbol} has unusually high volume",
                        "severity": "medium",
                        "data": quote
                    })
                
                # Check if near 52-week high
                if quote.get("price", 0) >= quote.get("high_52w", 0) * 0.95:
                    alerts.append({
                        "type": "near_high",
                        "symbol": symbol,
                        "message": f"{symbol} is near 52-week high",
                        "severity": "low",
                        "data": quote
                    })
                
                # Check if near 52-week low
                if quote.get("price", 0) <= quote.get("low_52w", 0) * 1.05:
                    alerts.append({
                        "type": "near_low",
                        "symbol": symbol,
                        "message": f"{symbol} is near 52-week low",
                        "severity": "low",
                        "data": quote
                    })
                    
            except Exception as e:
                continue
        
        # Sort alerts by severity
        severity_order = {"high": 3, "medium": 2, "low": 1}
        alerts.sort(key=lambda x: severity_order.get(x["severity"], 0), reverse=True)
        
        market_service.track_request("alerts", {"symbols": symbol_list, "alerts": len(alerts)})
        return {
            "status": "success",
            "alerts": alerts[:20]  # Limit to 20 alerts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
