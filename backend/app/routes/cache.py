"""
Cache management routes for performance optimization
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.security_service import get_api_key
from app.services.cache_service_lru import cache_service, invalidate_user_cache, invalidate_company_cache, warm_cache, BatchCache
from typing import Dict, Any, Optional

router = APIRouter()

@router.get("/cache/stats")
def get_cache_stats(api_key: str = Depends(get_api_key)):
    """Get cache performance statistics"""
    try:
        stats = cache_service.get_stats()
        
        return {
            "status": "success",
            "cache_stats": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/clear")
def clear_cache(
    pattern: Optional[str] = None,
    api_key: str = Depends(get_api_key)
):
    """Clear cache entries"""
    try:
        success = cache_service.clear(pattern)
        
        if pattern:
            return {
                "status": "success",
                "message": f"Cache entries matching '{pattern}' cleared successfully"
            }
        else:
            return {
                "status": "success",
                "message": "All cache entries cleared successfully"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cache/{key}")
def delete_cache_key(
    key: str,
    api_key: str = Depends(get_api_key)
):
    """Delete specific cache key"""
    try:
        success = cache_service.delete(key)
        
        if success:
            return {
                "status": "success",
                "message": f"Cache key '{key}' deleted successfully"
            }
        else:
            return {
                "status": "warning",
                "message": f"Cache key '{key}' not found or already deleted"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/{key}")
def get_cache_value(
    key: str,
    api_key: str = Depends(get_api_key)
):
    """Get value from cache"""
    try:
        value = cache_service.get(key)
        
        if value is not None:
            return {
                "status": "success",
                "key": key,
                "value": value,
                "found": True
            }
        else:
            return {
                "status": "success",
                "key": key,
                "value": None,
                "found": False
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/{key}")
def set_cache_value(
    key: str,
    value: Any,
    ttl: int = 300,
    api_key: str = Depends(get_api_key)
):
    """Set value in cache"""
    try:
        success = cache_service.set(key, value, ttl)
        
        if success:
            return {
                "status": "success",
                "message": f"Cache key '{key}' set successfully",
                "ttl": ttl
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to set cache value")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/warm")
def warm_cache_data(api_key: str = Depends(get_api_key)):
    """Warm up cache with frequently accessed data"""
    try:
        success = warm_cache()
        
        if success:
            return {
                "status": "success",
                "message": "Cache warming completed successfully"
            }
        else:
            return {
                "status": "warning",
                "message": "Cache warming completed with some issues"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/invalidate/user/{user_id}")
def invalidate_user_cache_endpoint(
    user_id: int,
    api_key: str = Depends(get_api_key)
):
    """Invalidate cache entries for a specific user"""
    try:
        success = invalidate_user_cache(user_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Cache invalidated for user {user_id}"
            }
        else:
            return {
                "status": "warning",
                "message": f"Cache invalidation completed with issues for user {user_id}"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cache/invalidate/company/{company}")
def invalidate_company_cache_endpoint(
    company: str,
    api_key: str = Depends(get_api_key)
):
    """Invalidate cache entries for a specific company"""
    try:
        success = invalidate_company_cache(company)
        
        if success:
            return {
                "status": "success",
                "message": f"Cache invalidated for company {company}"
            }
        else:
            return {
                "status": "warning",
                "message": f"Cache invalidation completed with issues for company {company}"
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/health")
def cache_health_check(api_key: str = Depends(get_api_key)):
    """Check cache health and performance"""
    try:
        stats = cache_service.get_stats()
        
        # Determine health status
        health_status = "healthy"
        issues = []
        
        # Check hit rate
        if stats["hit_rate"] < 50 and (stats["hits"] + stats["misses"]) > 100:
            health_status = "degraded"
            issues.append("Low cache hit rate")
        
        # Check Redis connection
        if not stats["redis_connected"]:
            health_status = "degraded"
            issues.append("Redis not connected, using local cache")
        
        # Check cache size
        if stats["local_cache_size"] > 10000:
            health_status = "warning"
            issues.append("Large local cache size")
        
        return {
            "status": "success",
            "health_status": health_status,
            "issues": issues,
            "cache_stats": stats,
            "recommendations": _get_cache_recommendations(stats)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/config")
def get_cache_config(api_key: str = Depends(get_api_key)):
    """Get cache configuration"""
    try:
        stats = cache_service.get_stats()
        
        config = {
            "cache_type": stats["cache_type"],
            "redis_connected": stats["redis_connected"],
            "default_ttl": 300,
            "max_local_cache_size": 10000,
            "cleanup_interval": 300,
            "features": {
                "redis_fallback": True,
                "local_cache": True,
                "cache_decorators": True,
                "batch_operations": True,
                "auto_cleanup": True
            }
        }
        
        return {
            "status": "success",
            "cache_config": config
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def _get_cache_recommendations(stats: Dict) -> list:
    """Get cache optimization recommendations"""
    recommendations = []
    
    if stats["hit_rate"] < 50:
        recommendations.append("Consider increasing cache TTL for frequently accessed data")
        recommendations.append("Review cache key patterns to improve hit rates")
    
    if not stats["redis_connected"]:
        recommendations.append("Consider setting up Redis for better cache performance")
        recommendations.append("Redis provides better memory management and persistence")
    
    if stats["local_cache_size"] > 5000:
        recommendations.append("Consider reducing local cache size or implementing LRU eviction")
        recommendations.append("Large local cache may impact memory usage")
    
    if stats["sets"] > stats["hits"] * 2:
        recommendations.append("High cache turnover - consider adjusting TTL values")
        recommendations.append("Some data may not benefit from caching")
    
    return recommendations

@router.post("/cache/batch")
def batch_cache_operations(
    operations: list,
    api_key: str = Depends(get_api_key)
):
    """Execute batch cache operations"""
    try:
        batch = BatchCache(cache_service)
        
        # Process operations
        for op in operations:
            op_type = op.get("type")
            
            if op_type == "get":
                batch.get(op["key"])
            elif op_type == "set":
                batch.set(op["key"], op["value"], op.get("ttl", 300))
            elif op_type == "delete":
                batch.delete(op["key"])
        
        # Execute all operations
        results = batch.execute()
        
        return {
            "status": "success",
            "batch_results": results,
            "operations_processed": len(operations)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/monitor")
def cache_monitoring(api_key: str = Depends(get_api_key)):
    """Get detailed cache monitoring data"""
    try:
        stats = cache_service.get_stats()
        
        monitoring_data = {
            "performance_metrics": {
                "hit_rate": stats["hit_rate"],
                "total_requests": stats["hits"] + stats["misses"],
                "cache_efficiency": "good" if stats["hit_rate"] > 70 else "fair" if stats["hit_rate"] > 50 else "poor"
            },
            "cache_utilization": {
                "local_cache_size": stats["local_cache_size"],
                "cache_type": stats["cache_type"],
                "redis_available": stats["redis_connected"]
            },
            "operation_counts": {
                "gets": stats["hits"] + stats["misses"],
                "sets": stats["sets"],
                "deletes": stats["deletes"]
            },
            "trends": {
                "hourly_stats": "N/A",  # Would require historical data
                "daily_stats": "N/A"
            },
            "alerts": []
        }
        
        # Generate alerts
        if stats["hit_rate"] < 30:
            monitoring_data["alerts"].append("Very low cache hit rate detected")
        
        if not stats["redis_connected"]:
            monitoring_data["alerts"].append("Redis connection lost")
        
        if stats["local_cache_size"] > 8000:
            monitoring_data["alerts"].append("Local cache size approaching limits")
        
        return {
            "status": "success",
            "monitoring_data": monitoring_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
