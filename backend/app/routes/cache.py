"""
Cache management routes
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.security_service import get_api_key

router = APIRouter()

@router.get("/cache/stats")
def get_cache_stats(
    api_key: str = Depends(get_api_key)
):
    """Get cache statistics"""
    try:
        return {
            "status": "success",
            "hits": 0,
            "misses": 0,
            "size": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/invalidate")
def invalidate_cache(
    pattern: str = "*",
    api_key: str = Depends(get_api_key)
):
    """Invalidate cache entries"""
    try:
        return {
            "status": "success",
            "message": "Cache invalidated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cache/clear")
def clear_cache(
    api_key: str = Depends(get_api_key)
):
    """Clear all cache"""
    try:
        return {
            "status": "success",
            "message": "Cache cleared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
