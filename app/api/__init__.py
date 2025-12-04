"""API routes initialization."""
from fastapi import APIRouter
from typing import Dict, Any

from app.api import chat, documents, health, search
from app.api import legalgpt_extract

router = APIRouter()

# Include all API route modules
router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])

# Search endpoint
router.include_router(search.router, prefix="/search", tags=["search"])

# Legacy extract endpoints for compatibility
router.include_router(legalgpt_extract.router, prefix="/legalgpt/extract", tags=["extract"])

# Prompt templates endpoint - expose at /api/legalgpt/prompts/
@router.get("/legalgpt/prompts/")
async def get_prompt_templates() -> Dict[str, Any]:
    """Get prompt templates (returns empty array if no templates configured)."""
    try:
        # Return empty templates array for now
        # TODO: Load from prompts/prompts.json if needed
        return {
            "status": "success",
            "templates": []
        }
    except Exception as e:
        return {
            "status": "success",
            "templates": []
        }
