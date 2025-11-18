"""FastAPI dependency injection functions."""
from fastapi import Request, HTTPException
from app.services.vector_store import VectorStore


def get_vector_store(request: Request) -> VectorStore:
    """
    Dependency function to inject VectorStore instance from app state.
    
    Raises HTTPException if VectorStore is not available in app state.
    This ensures we use the singleton instance created at startup.
    """
    if not hasattr(request.app.state, 'vector_store') or request.app.state.vector_store is None:
        raise HTTPException(
            status_code=500,
            detail="VectorStore not initialized. Application may not be fully started."
        )
    return request.app.state.vector_store

