"""
Advanced search routes with hybrid search capabilities
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional
from app.services.security_service import get_api_key
from app.services.search_service import search_service

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    search_type: str = "all"  # all, drafts, library, conversations
    search_method: str = "hybrid"  # keyword, semantic, hybrid
    filters: Optional[Dict] = None
    limit: int = 20

class SearchResponse(BaseModel):
    status: str
    query: str
    results: List[Dict]
    total_results: int
    search_method: str
    search_time: float

@router.post("/search", response_model=SearchResponse)
def advanced_search(
    request: SearchRequest,
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Perform advanced search with multiple methods"""
    import time
    start_time = time.time()
    
    try:
        # Validate search type
        valid_types = ["all", "drafts", "library", "conversations"]
        if request.search_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid search type. Must be one of: {valid_types}")
        
        # Validate search method
        valid_methods = ["keyword", "semantic", "hybrid"]
        if request.search_method not in valid_methods:
            raise HTTPException(status_code=400, detail=f"Invalid search method. Must be one of: {valid_methods}")
        
        # Perform search based on method
        if request.search_method == "keyword":
            results = search_service.keyword_search(request.query, request.search_type, user_id)
        elif request.search_method == "semantic":
            results = search_service.semantic_search(request.query, request.search_type, user_id, request.limit)
        else:  # hybrid
            results = search_service.hybrid_search(request.query, request.search_type, user_id, request.limit)
        
        # Apply filters if provided
        if request.filters and results:
            filtered_results = []
            for result in results:
                include = True
                
                # Date filter
                if "date_from" in request.filters:
                    from datetime import datetime
                    date_from = datetime.fromisoformat(request.filters["date_from"])
                    result_date = datetime.fromisoformat(result["date"])
                    if result_date < date_from:
                        include = False
                
                # Company filter
                if "company" in request.filters:
                    if request.filters["company"].lower() not in result["company"].lower():
                        include = False
                
                # Confidence filter
                if "confidence" in request.filters:
                    if result["confidence"] != request.filters["confidence"]:
                        include = False
                
                # Type filter
                if "type" in request.filters:
                    if result["type"] != request.filters["type"]:
                        include = False
                
                if include:
                    filtered_results.append(result)
            
            results = filtered_results
        
        search_time = time.time() - start_time
        
        return SearchResponse(
            status="success",
            query=request.query,
            results=results[:request.limit],
            total_results=len(results),
            search_method=request.search_method,
            search_time=search_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/quick")
def quick_search(
    q: str = Query(..., description="Search query"),
    type: str = Query("all", description="Search type"),
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Quick search endpoint for simple queries"""
    try:
        # Use hybrid search for quick search
        results = search_service.hybrid_search(q, type, user_id, 10)
        
        return {
            "status": "success",
            "query": q,
            "results": results,
            "total_results": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/suggestions")
def get_search_suggestions(
    q: str = Query(..., description="Partial query"),
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get search suggestions based on partial query"""
    try:
        suggestions = search_service.get_search_suggestions(q, user_id)
        
        return {
            "status": "success",
            "query": q,
            "suggestions": suggestions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/faceted")
def faceted_search(
    q: str = Query(..., description="Search query"),
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Get faceted search results with counts by type"""
    try:
        # Get results by type
        drafts_results = search_service.keyword_search(q, "drafts", user_id)
        library_results = search_service.keyword_search(q, "library", user_id)
        conversation_results = search_service.keyword_search(q, "conversations", user_id)
        
        # Get top companies
        companies = {}
        for result in drafts_results:
            company = result["company"]
            if company not in companies:
                companies[company] = 0
            companies[company] += 1
        
        for result in library_results:
            company = result["company"]
            if company not in companies:
                companies[company] = 0
            companies[company] += 1
        
        # Sort companies by count
        top_companies = sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "status": "success",
            "query": q,
            "facets": {
                "drafts": {
                    "count": len(drafts_results),
                    "results": drafts_results[:5]
                },
                "library": {
                    "count": len(library_results),
                    "results": library_results[:5]
                },
                "conversations": {
                    "count": len(conversation_results),
                    "results": conversation_results[:5]
                }
            },
            "top_companies": [{"company": company, "count": count} for company, count in top_companies]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search/similar")
def find_similar_content(
    content_id: int = Query(..., description="Content ID"),
    content_type: str = Query(..., description="Content type"),
    user_id: int = Query(1, description="User ID"),
    api_key: str = Depends(get_api_key)
):
    """Find similar content using semantic search"""
    try:
        from sqlalchemy.orm import Session
        from app.config.database import get_db
        from app.models.database import Draft, Library, Conversation
        
        db = next(get_db())
        try:
            # Get the original content
            original_content = None
            
            if content_type == "draft":
                original_content = db.query(Draft).filter(
                    Draft.id == content_id,
                    Draft.user_id == user_id
                ).first()
            elif content_type == "library":
                original_content = db.query(Library).filter(
                    Library.id == content_id,
                    Library.user_id == user_id
                ).first()
            elif content_type == "conversation":
                original_content = db.query(Conversation).filter(
                    Conversation.id == content_id,
                    Conversation.user_id == user_id
                ).first()
            
            if not original_content:
                raise HTTPException(status_code=404, detail="Content not found")
            
            # Extract text for semantic search
            if content_type == "draft":
                search_text = original_content.analysis or original_content.email_draft or ""
            elif content_type == "library":
                search_text = original_content.company + " " + original_content.file_name
            elif content_type == "conversation":
                search_text = original_content.query + " " + original_content.response
            else:
                search_text = ""
            
            # Perform semantic search
            similar_results = search_service.semantic_search(search_text, "all", user_id, 10)
            
            # Filter out the original content
            filtered_results = []
            for result in similar_results:
                if not (result["type"] == content_type and result["id"] == content_id):
                    filtered_results.append(result)
            
            return {
                "status": "success",
                "original_content": {
                    "id": content_id,
                    "type": content_type,
                    "title": f"{content_type.title()}: {content_id}"
                },
                "similar_results": filtered_results[:5]
            }
            
        finally:
            db.close()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
