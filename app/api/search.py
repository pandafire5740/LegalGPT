"""
New search API endpoint with grouped results and AI summaries.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from functools import lru_cache
import time
from collections import defaultdict

from app.services import search_query
from app.services.llm_engine import LLMEngine

logger = logging.getLogger(__name__)

router = APIRouter()

# Simple in-memory cache (query -> (results, summary, timestamp))
_cache = {}
CACHE_TTL = 600  # 10 minutes

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k_groups: int = Field(6, ge=1, le=20, description="Number of file groups to return")
    max_snippets_per_group: int = Field(3, ge=1, le=5, description="Max snippets per file")

class Snippet(BaseModel):
    text: str
    position: int
    score: float

class FileGroup(BaseModel):
    file_id: str
    filename: str
    doc_score: float
    snippets: List[Snippet]

class SearchResponse(BaseModel):
    summary: str
    groups: List[FileGroup]
    query: str
    total_groups: int

class IndexedDocument(BaseModel):
    file_id: str
    filename: str
    chunk_count: int
    source: str  # "local" or "sharepoint"

class IndexStatusResponse(BaseModel):
    status: str
    total_files: int
    total_chunks: int
    documents: List[IndexedDocument]

@router.post("/", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """
    Search documents with grouped results and AI summary.
    
    Returns up to `top_k_groups` file groups, each with up to `max_snippets_per_group` snippets.
    Includes a brief AI-generated summary (≤50 words).
    """
    try:
        start_time = time.time()
        logger.info(f"Search request: query='{request.query}', top_k={request.top_k_groups}")
        
        # Check cache
        cache_key = f"{request.query}|{request.top_k_groups}|{request.max_snippets_per_group}"
        if cache_key in _cache:
            cached_results, cached_summary, cached_time = _cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                logger.info(f"Cache hit for query: {request.query}")
                return SearchResponse(
                    summary=cached_summary,
                    groups=[FileGroup(**group) for group in cached_results],
                    query=request.query,
                    total_groups=len(cached_results)
                )
        
        # Perform search
        groups = search_query.search_and_group(
            query=request.query,
            top_k_groups=request.top_k_groups,
            max_snippets_per_group=request.max_snippets_per_group
        )
        
        # Generate summary via shared LLM
        if groups:
            # Flatten top snippets across groups for context
            top_chunks = []
            for g in groups[: request.top_k_groups]:
                for sn in g.get("snippets", [])[: request.max_snippets_per_group]:
                    top_chunks.append({
                        "content": sn.get("text", ""),
                        "metadata": {"file_name": g.get("filename", "Unknown")},
                    })
            summary = LLMEngine.summarize(request.query, top_chunks, max_words=75)
        else:
            summary = "No matching results found."
        
        # Cache results
        _cache[cache_key] = (groups, summary, time.time())
        
        # Clean old cache entries (simple cleanup)
        if len(_cache) > 100:
            cutoff = time.time() - CACHE_TTL
            _cache.clear()  # Simple approach: clear all when too large
        
        elapsed = time.time() - start_time
        logger.info(f"Search completed in {elapsed:.2f}s, found {len(groups)} groups")
        
        return SearchResponse(
            summary=summary,
            groups=[FileGroup(**group) for group in groups],
            query=request.query,
            total_groups=len(groups)
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.post("/rebuild")
async def rebuild_index():
    """
    Rebuild the search index from all uploaded documents.
    This should be called after uploading new documents.
    """
    try:
        from app.services import search_ingest
        from app.api import documents
        import tempfile
        import shutil
        from pathlib import Path
        
        logger.info("Starting index rebuild...")
        
        # Clear existing index
        search_ingest.clear_index()
        
        # Get all documents from ChromaDB
        from app.services.vector_store import VectorStore
        vector_store = VectorStore()
        
        # Get all unique files
        all_docs = vector_store.collection.get(include=['metadatas', 'documents'])
        
        if not all_docs['metadatas']:
            logger.warning("No documents found to index")
            return {"status": "success", "message": "No documents to index", "indexed_files": 0}
        
        # Group by file
        files_seen = set()
        all_chunks = []
        
        for metadata, content in zip(all_docs['metadatas'], all_docs['documents']):
            file_name = metadata.get('file_name', 'Unknown')
            file_path = metadata.get('file_path', '')
            
            if file_name not in files_seen:
                files_seen.add(file_name)
                
                # For each unique file, chunk it with the new strategy
                file_id = f"f_{len(files_seen)}"
                chunks = search_ingest.chunk_text(content, file_id, file_name)
                all_chunks.extend(chunks)
        
        if not all_chunks:
            logger.warning("No chunks created")
            return {"status": "success", "message": "No chunks created", "indexed_files": 0}
        
        # Generate embeddings
        logger.info(f"Generating embeddings for {len(all_chunks)} chunks...")
        embeddings = search_ingest.embed_chunks(all_chunks)
        
        # Build index
        search_ingest.build_index(all_chunks, embeddings)
        
        # Save to disk
        search_ingest.save_index()
        
        # Clear cache
        _cache.clear()
        
        logger.info(f"Index rebuild complete: {len(files_seen)} files, {len(all_chunks)} chunks")
        return {
            "status": "success",
            "message": "Index rebuilt successfully",
            "indexed_files": len(files_seen),
            "total_chunks": len(all_chunks)
        }
        
    except Exception as e:
        logger.error(f"Index rebuild failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Index rebuild failed: {str(e)}")

@router.get("/status", response_model=IndexStatusResponse)
async def get_index_status():
    """
    Get the current status of the search index, including all indexed documents.
    """
    try:
        from app.services import search_ingest
        
        chunks = search_ingest.get_chunks()
        
        if not chunks:
            return IndexStatusResponse(
                status="empty",
                total_files=0,
                total_chunks=0,
                documents=[]
            )
        
        # Group chunks by file
        file_groups = defaultdict(list)
        for chunk in chunks:
            file_id = chunk.get("file_id", "unknown")
            filename = chunk.get("filename", "Unknown")
            file_groups[(file_id, filename)].append(chunk)
        
        # Build document list
        documents = []
        for (file_id, filename), file_chunks in file_groups.items():
            # Determine source based on metadata
            source = "local"  # Default
            if file_chunks and "source" in file_chunks[0]:
                source = file_chunks[0]["source"]
            
            documents.append(IndexedDocument(
                file_id=file_id,
                filename=filename,
                chunk_count=len(file_chunks),
                source=source
            ))
        
        # Sort by filename
        documents.sort(key=lambda d: d.filename)
        
        return IndexStatusResponse(
            status="ready",
            total_files=len(documents),
            total_chunks=len(chunks),
            documents=documents
        )
        
    except Exception as e:
        logger.error(f"Failed to get index status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get index status: {str(e)}")


