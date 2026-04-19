"""Mock data service for testing when external APIs are rate limited"""

import json
from typing import List, Dict

def get_mock_company_data(symbol: str) -> List[Dict]:
    """Return mock financial data for common stock symbols"""
    
    mock_data = {
        "AAPL": {
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "market_cap": "3.2T",
            "revenue_2023": "383.3B",
            "revenue_2022": "394.3B",
            "net_income_2023": "99.8B",
            "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide."
        },
        "MSFT": {
            "name": "Microsoft Corporation",
            "sector": "Technology",
            "industry": "Software",
            "market_cap": "3.1T",
            "revenue_2023": "211.9B",
            "revenue_2022": "198.3B",
            "net_income_2023": "72.4B",
            "description": "Microsoft Corporation develops, licenses, and supports software, services, devices, and solutions worldwide."
        },
        "GOOGL": {
            "name": "Alphabet Inc.",
            "sector": "Technology",
            "industry": "Internet Services",
            "market_cap": "2.1T",
            "revenue_2023": "307.4B",
            "revenue_2022": "282.8B",
            "net_income_2023": "73.8B",
            "description": "Alphabet Inc. provides online advertising services in the United States, Europe, the Middle East, Africa, the Asia-Pacific, Canada, and Latin America."
        },
        "AMZN": {
            "name": "Amazon.com, Inc.",
            "sector": "Consumer Cyclical",
            "industry": "Internet Retail",
            "market_cap": "1.9T",
            "revenue_2023": "574.8B",
            "revenue_2022": "514.0B",
            "net_income_2023": "30.4B",
            "description": "Amazon.com, Inc. engages in the retail sale of consumer products and subscriptions in North America and internationally."
        },
        "NVDA": {
            "name": "NVIDIA Corporation",
            "sector": "Technology",
            "industry": "Semiconductors",
            "market_cap": "2.2T",
            "revenue_2023": "60.9B",
            "revenue_2022": "26.9B",
            "net_income_2023": "29.8B",
            "description": "NVIDIA Corporation designs and markets computer graphics processors, chipsets, and related multimedia software."
        },
        "TSLA": {
            "name": "Tesla, Inc.",
            "sector": "Consumer Cyclical",
            "industry": "Auto Manufacturers",
            "market_cap": "800B",
            "revenue_2023": "96.8B",
            "revenue_2022": "81.5B",
            "net_income_2023": "15.0B",
            "description": "Tesla, Inc. designs, develops, manufactures, leases, and sells electric vehicles, and energy generation and storage systems."
        }
    }
    
    data = mock_data.get(symbol, {
        "name": f"{symbol} Corporation",
        "sector": "Technology",
        "industry": "General",
        "market_cap": "Unknown",
        "revenue_2023": "Unknown",
        "revenue_2022": "Unknown",
        "net_income_2023": "Unknown",
        "description": f"{symbol} is a publicly traded company with limited data available."
    })
    
    docs = []
    
    # Company info document
    company_text = f"{symbol}: {data['name']}. Sector: {data['sector']}. Industry: {data['industry']}. Market Cap: {data['market_cap']}. {data['description']}"
    docs.append({
        "text": company_text,
        "type": "company_info",
        "symbol": symbol
    })
    
    # Financial data document
    financial_text = f"{symbol} Financial Data - Revenue 2023: {data['revenue_2023']}, Revenue 2022: {data['revenue_2022']}, Net Income 2023: {data['net_income_2023']}"
    docs.append({
        "text": financial_text,
        "type": "financial_statement",
        "symbol": symbol,
        "statement": "summary"
    })
    
    # Analysis document
    analysis_text = f"{symbol} Analysis: The company operates in the {data['sector']} sector with a market capitalization of {data['market_cap']}. Recent financial performance shows revenue trends from {data['revenue_2022']} to {data['revenue_2023']}. Key metrics to monitor include profitability ratios, growth rates, and market position relative to competitors."
    docs.append({
        "text": analysis_text,
        "type": "analysis",
        "symbol": symbol
    })
    
    return docs

def get_mock_projections(symbol: str) -> List[Dict]:
    """Return mock financial projections"""
    
    return [
        {
            "metric": "Revenue",
            "period": "2024",
            "value": f"${hash(symbol) % 100 + 50}B",
            "source_context": "Analyst consensus estimates"
        },
        {
            "metric": "EPS",
            "period": "2024",
            "value": f"${(hash(symbol) % 10) + 1}.{hash(symbol) % 100}",
            "source_context": "Company guidance"
        },
        {
            "metric": "Revenue Growth",
            "period": "2024",
            "value": f"{hash(symbol) % 20 + 5}%",
            "source_context": "Industry analysis"
        }
    ]
