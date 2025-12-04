"""
LegalGPT - AI-Powered Legal Document Platform

Main FastAPI application entry point with startup/shutdown lifecycle management.
Provides REST API for document upload, search, chat, and contract extraction.
"""
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.api import router
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import VectorStore

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LegalGPT - AI Legal Document Platform",
    description="Upload, search, chat, and extract terms from legal documents using OpenAI GPT-4o",
    version="2.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS middleware for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# Serve static files for web frontend
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
async def startup_event():
    """
    Initialize services on application startup.
    
    - Initializes ChromaDB vector store with OpenAI embeddings
    - Sets up document processor for file ingestion
    """
    logger.info("🚀 Starting LegalGPT Platform")
    
    # Initialize vector store (ChromaDB + OpenAI embeddings)
    vector_store = VectorStore()
    app.state.vector_store = vector_store
    logger.info("✅ Vector store initialized")
    
    # Initialize document processor
    document_processor = DocumentProcessor(vector_store)
    app.state.document_processor = document_processor
    logger.info("✅ Document processor ready")
    
    logger.info("🎉 LegalGPT ready at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on application shutdown."""
    logger.info("👋 Shutting down LegalGPT")


@app.get("/")
async def root():
    """Root endpoint serving the web application."""
    from fastapi.responses import FileResponse
    return FileResponse("app/static/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/api/info")
async def platform_info():
    """Platform information endpoint."""
    return {"message": "Legal Knowledge Retrieval Platform", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
