"""
Market data service for real-time financial information
"""
import os
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.config.database import get_db
from app.models.database import Analytics, User
import time

class MarketDataService:
    def __init__(self):
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY", "")
        self.finnhub_key = os.getenv("FINNHUB_KEY", "")
        self.polygon_key = os.getenv("POLYGON_KEY", "")
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes cache
        
    def get_cache_key(self, symbol: str, data_type: str) -> str:
        """Generate cache key for market data"""
        return f"{symbol}_{data_type}_{int(time.time() // self.cache_ttl)}"
    
    def get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Get data from cache if not expired"""
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return data
            else:
                del self.cache[cache_key]
        return None
    
    def set_cache(self, cache_key: str, data: Dict):
        """Set data in cache"""
        self.cache[cache_key] = (data, time.time())
    
    def get_stock_quote(self, symbol: str) -> Dict:
        """Get real-time stock quote with fallbacks"""
        cache_key = self.get_cache_key(symbol, "quote")
        cached_data = self.get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        # yfinance disabled - using Alpha Vantage or mock data
        # Try Alpha Vantage first
        if self.alpha_vantage_key:
            try:
                url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={self.alpha_vantage_key}"
                response = requests.get(url, timeout=10)
                data = response.json()
                
                if 'Global Quote' in data:
                    quote = data['Global Quote']
                    price = float(quote.get('05. price', 0))
                    change = float(quote.get('09. change', 0))
                    change_percent = float(quote.get('10. change percent', 0).replace('%', ''))
                    
                    result = {
                        "symbol": symbol,
                        "price": price,
                        "change": change,
                        "change_percent": change_percent,
                        "volume": int(quote.get('06. volume', 0)),
                        "market_cap": 0,
                        "pe_ratio": 0,
                        "high_52w": 0,
                        "low_52w": 0,
                        "updated": datetime.utcnow().isoformat(),
                        "source": "alpha_vantage"
                    }
                    self.set_cache(cache_key, result)
                    return result
            except Exception as e:
                print(f"Alpha Vantage failed for {symbol}: {e}")
        
        # Return mock data as last resort
        return self.get_mock_quote(symbol)
    
    def get_market_news(self, symbol: str = None, limit: int = 10) -> List[Dict]:
        """Get market news with fallbacks"""
        cache_key = self.get_cache_key(symbol or "market", "news")
        cached_data = self.get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        try:
            # Try Alpha Vantage news
            if self.alpha_vantage_key:
                url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&apikey={self.alpha_vantage_key}"
                response = requests.get(url, timeout=10)
                data = response.json()
                
                if 'feed' in data:
                    news = data['feed'][:limit]
                    result = [
                        {
                            "title": item.get('title', ''),
                            "url": item.get('url', ''),
                            "summary": item.get('summary', ''),
                            "source": item.get('source', ''),
                            "published": item.get('time_published', ''),
                            "sentiment": item.get('overall_sentiment_score', 0),
                            "symbols": item.get('ticker_sentiment', [])
                        }
                        for item in news
                    ]
                    self.set_cache(cache_key, result)
                    return result
        except Exception as e:
            print(f"Alpha Vantage news failed: {e}")
        
        # Return mock news
        return self.get_mock_news(symbol, limit)
    
    def get_sector_performance(self) -> List[Dict]:
        """Get sector performance data"""
        cache_key = self.get_cache_key("market", "sectors")
        cached_data = self.get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        sectors = [
            {"name": "Technology", "symbol": "XLK", "change": 0},
            {"name": "Healthcare", "symbol": "XLV", "change": 0},
            {"name": "Finance", "symbol": "XLF", "change": 0},
            {"name": "Energy", "symbol": "XLE", "change": 0},
            {"name": "Consumer Discretionary", "symbol": "XLY", "change": 0},
            {"name": "Consumer Staples", "symbol": "XLP", "change": 0},
            {"name": "Industrial", "symbol": "XLI", "change": 0},
            {"name": "Materials", "symbol": "XLB", "change": 0},
            {"name": "Real Estate", "symbol": "XLRE", "change": 0},
            {"name": "Utilities", "symbol": "XLU", "change": 0},
            {"name": "Communication", "symbol": "XLC", "change": 0}
        ]
        
        for sector in sectors:
            try:
                quote = self.get_stock_quote(sector["symbol"])
                sector["change"] = quote.get("change_percent", 0)
                sector["price"] = quote.get("price", 0)
            except:
                sector["change"] = 0
                sector["price"] = 0
        
        self.set_cache(cache_key, sectors)
        return sectors
    
    def get_market_indicators(self) -> Dict:
        """Get major market indicators"""
        indicators = {}
        
        major_indices = [
            {"name": "S&P 500", "symbol": "^GSPC"},
            {"name": "Dow Jones", "symbol": "^DJI"},
            {"name": "NASDAQ", "symbol": "^IXIC"},
            {"name": "VIX", "symbol": "^VIX"},
            {"name": "Gold", "symbol": "GC=F"},
            {"name": "Oil", "symbol": "CL=F"},
            {"name": "Bitcoin", "symbol": "BTC-USD"}
        ]
        
        for index in major_indices:
            try:
                quote = self.get_stock_quote(index["symbol"])
                indicators[index["symbol"]] = {
                    "name": index["name"],
                    "price": quote.get("price", 0),
                    "change": quote.get("change", 0),
                    "change_percent": quote.get("change_percent", 0)
                }
            except:
                indicators[index["symbol"]] = {
                    "name": index["name"],
                    "price": 0,
                    "change": 0,
                    "change_percent": 0
                }
        
        return indicators
    
    def get_mock_quote(self, symbol: str) -> Dict:
        """Generate mock quote data"""
        import random
        
        base_price = random.uniform(50, 500)
        change = random.uniform(-5, 5)
        change_percent = (change / base_price) * 100
        
        return {
            "symbol": symbol,
            "price": round(base_price, 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "volume": random.randint(100000, 10000000),
            "market_cap": random.randint(1000000000, 100000000000),
            "pe_ratio": random.uniform(10, 30),
            "high_52w": base_price * 1.2,
            "low_52w": base_price * 0.8,
            "updated": datetime.utcnow().isoformat(),
            "source": "mock"
        }
    
    def get_mock_news(self, symbol: str = None, limit: int = 10) -> List[Dict]:
        """Generate mock news data"""
        import random
        
        companies = ["Apple", "Microsoft", "Google", "Amazon", "Tesla", "Meta", "Netflix", "NVIDIA"]
        headlines = [
            "Stock reaches new heights amid strong earnings",
            "Analysts upgrade price target following positive report",
            "Company announces innovative new product line",
            "Market volatility concerns impact investor sentiment",
            "Quarterly results exceed expectations",
            "Strategic partnership announced with industry leader",
            "CEO outlines vision for future growth",
            "Regulatory approval received for key product"
        ]
        
        news = []
        for i in range(limit):
            company = random.choice(companies)
            headline = random.choice(headlines)
            
            news.append({
                "title": f"{company}: {headline}",
                "url": "https://example.com/news",
                "summary": f"Latest developments regarding {company}'s business operations and market performance.",
                "source": "Mock News Network",
                "published": (datetime.utcnow() - timedelta(hours=random.randint(1, 24))).isoformat(),
                "sentiment": random.uniform(-0.5, 0.5),
                "symbols": [company[:4].upper()]
            })
        
        return news
    
    def track_request(self, event_type: str, data: Dict):
        """Track market data requests for analytics"""
        try:
            db = next(get_db())
            user = db.query(User).filter_by(username="default").first()
            
            if user:
                analytics = Analytics(
                    user_id=user.id,
                    event_type=event_type,
                    event_data=data,
                    timestamp=datetime.utcnow(),
                    session_id="market_service"
                )
                db.add(analytics)
                db.commit()
        except Exception as e:
            print(f"Failed to track market request: {e}")
        finally:
            db.close()

# Global market service instance
market_service = MarketDataService()
