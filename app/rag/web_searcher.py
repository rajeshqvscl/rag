"""
Web-Augmented RAG - Combine local documents with live web search
Uses DuckDuckGo (free, no API key required)
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import time
import re


def search_web(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search using multiple free APIs with fallback
    """
    results = _search_with_scrape(query, num_results)
    if results:
        return results
    
    results = _search_with_duckduckgo_html(query, num_results)
    if results:
        return results
    
    return get_demo_results(query, num_results)


def _search_with_scrape(query: str, num_results: int) -> List[Dict]:
    """Scrape Bing results via HTML"""
    from urllib.parse import quote
    
    url = f"https://www.bing.com/search?q={quote(query)}&count={num_results}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive"
    }
    
    try:
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        for item in soup.select(".b_algo")[:num_results]:
            title_elem = item.select_one("h2 a")
            snippet_elem = item.select_one("p")
            
            if title_elem:
                results.append({
                    "title": title_elem.get_text(strip=True),
                    "url": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    "source": "web"
                })
        
        return results
    except Exception as e:
        print(f"[BING SCRAPE ERROR] {e}")
        return []


def _search_with_duckduckgo_html(query: str, num_results: int) -> List[Dict]:
    """Try DuckDuckGo HTML scraping"""
    from urllib.parse import quote
    
    url = f"https://duckduckgo.com/html/?q={quote(query)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            
            for item in soup.select(".result")[:num_results]:
                title_elem = item.select_one(".result__title")
                link_elem = item.select_one(".result__url")
                snippet_elem = item.select_one(".result__snippet")
                
                if title_elem:
                    url_text = link_elem.get_text(strip=True) if link_elem else ""
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "url": url_text,
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "source": "web"
                    })
            
            return results
    except Exception as e:
        print(f"[DDG HTML ERROR] {e}")
        return []


def get_demo_results(query: str, num_results: int = 3) -> List[Dict[str, Any]]:
    """Fallback demo results when API is blocked"""
    return [
        {
            "title": f"Demo Result 1 for: {query}",
            "url": "https://example.com/1",
            "snippet": f"This is a demo result for '{query}'. The web search API is currently unavailable from server-side.",
            "source": "demo"
        },
        {
            "title": f"Demo Result 2 for: {query}",
            "url": "https://example.com/2",
            "snippet": f"Search functionality requires client-side integration or alternative API configuration.",
            "source": "demo"
        },
        {
            "title": f"Demo Result 3 for: {query}",
            "url": "https://example.com/3",
            "snippet": f"To enable live search, configure SerpAPI or use browser-side DuckDuckGo integration.",
            "source": "demo"
        }
    ][:num_results]


def extract_content_from_url(url: str) -> Dict[str, Any]:
    """Extract main content from a web page"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
        
        # Get title
        title = soup.title.string if soup.title else ""
        
        # Get main content (article or main)
        main_content = soup.find("article") or soup.find("main") or soup.find("body")
        text = main_content.get_text(separator="\n", strip=True) if main_content else ""
        
        # Limit text length
        text = text[:3000] + "..." if len(text) > 3000 else text
        
        return {
            "url": url,
            "title": title,
            "content": text,
            "success": True
        }
        
    except Exception as e:
        return {
            "url": url,
            "title": "",
            "content": "",
            "success": False,
            "error": str(e)
        }


def augment_with_web(query: str, local_chunks: List[str], local_sources: List[Dict], 
                     threshold: float = 0.6, max_web_results: int = 3) -> Dict[str, Any]:
    """
    Augment local RAG results with web search if needed
    
    Args:
        query: User query
        local_chunks: Already retrieved local chunks
        local_sources: Source metadata for local chunks
        threshold: If max local score < threshold, trigger web search
        max_web_results: Maximum web results to include
    
    Returns:
        {
            "chunks": [...],
            "sources": [...],
            "web_results": [...],
            "augmented": bool
        }
    """
    # Check if augmentation is needed
    needs_augmentation = False
    
    if not local_chunks:
        needs_augmentation = True
    else:
        # Check if local sources have low scores
        max_score = max([s.get("score", 0) for s in local_sources], default=0)
        if max_score < threshold:
            needs_augmentation = True
    
    if not needs_augmentation:
        return {
            "chunks": local_chunks,
            "sources": local_sources,
            "web_results": [],
            "augmented": False
        }
    
    # Perform web search
    web_results = search_web(query, num_results=max_web_results)
    
    if not web_results:
        return {
            "chunks": local_chunks,
            "sources": local_sources,
            "web_results": [],
            "augmented": False
        }
    
    # Extract content from top results
    web_contents = []
    for result in web_results[:2]:  # Get content from top 2
        if result.get("url"):
            content = extract_content_from_url(result["url"])
            if content.get("success"):
                web_contents.append(content)
                time.sleep(0.5)  # Be respectful
    
    # Add web content to chunks
    all_chunks = list(local_chunks)
    web_sources = []
    
    for i, content in enumerate(web_contents):
        all_chunks.append(f"[WEB] {content['title']}: {content['content']}")
        web_sources.append({
            "text": content["content"][:200],
            "score": 1.0,
            "doc_id": f"web_{i}",
            "domain": "web",
            "section": "web",
            "company": "Web Search",
            "source_url": content["url"]
        })
    
    return {
        "chunks": all_chunks,
        "sources": local_sources + web_sources,
        "web_results": web_results,
        "augmented": True
    }


def smart_search(query: str, local_retrieval_fn=None, use_web: bool = True, 
                 web_threshold: float = 0.6, namespace: str = None) -> Dict[str, Any]:
    """
    Smart search that combines local and web results
    
    Args:
        query: User query
        local_retrieval_fn: Function to call for local retrieval
        use_web: Whether to use web augmentation
        web_threshold: Threshold to trigger web search
        namespace: Namespace for data isolation
    """
    # First get local results
    if local_retrieval_fn:
        local_result = local_retrieval_fn(query)
    else:
        from .retriever import retrieve_with_sources
        local_result = retrieve_with_sources(query, namespace=namespace, top_k=5)
    
    if not use_web:
        return {
            **local_result,
            "web_results": [],
            "augmented": False
        }
    
    # Augment with web if needed
    return augment_with_web(
        query,
        local_result["chunks"],
        local_result["sources"],
        threshold=web_threshold
    )