"""Health check API endpoints."""
from fastapi import APIRouter, Depends
from typing import Dict, Any
import logging

from app.services.vector_store import VectorStore
from app.dependencies import get_vector_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "Legal Knowledge Platform",
        "version": "1.0.0"
    }


@router.get("/detailed")
async def detailed_health_check(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Detailed health check including service dependencies."""
    health_status = {
        "status": "healthy",
        "service": "Legal Knowledge Platform",
        "version": "1.0.0",
        "checks": {}
    }
    
    try:
        # Check vector store
        try:
            stats = vector_store.get_collection_stats()
            health_status["checks"]["vector_store"] = {
                "status": "healthy",
                "stats": stats
            }
        except Exception as e:
            health_status["checks"]["vector_store"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        # SharePoint check removed in minimal local mode
        
    except Exception as e:
        logger.error(f"Health check failed, error: {str(e)}")
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
    
    return health_status
