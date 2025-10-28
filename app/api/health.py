"""Health check API endpoints."""
from fastapi import APIRouter, Depends
from typing import Dict, Any
import logging

from app.services.vector_store import VectorStore
from app.services import ai_service

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
async def detailed_health_check() -> Dict[str, Any]:
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
            vector_store = VectorStore()
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


@router.get("/models")
async def model_status() -> Dict[str, Any]:
    """Check status of the chat model (Phi-3 only)."""
    try:
        model_info = {
            "phi": {
                "name": "Phi-3-mini-4k-instruct",
                "size": "~2GB",
                "status": ai_service._loading_status.get("phi", "not_loaded"),
                "loaded": "phi" in ai_service._chat_pipelines
            }
        }
        return {
            "status": "success",
            "models": model_info,
            "total_loaded": len(ai_service._chat_pipelines)
        }
    except Exception as e:
        logger.error(f"Model status check failed: {e}")
        return {"status": "error", "error": str(e)}
