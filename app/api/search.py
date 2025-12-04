"""
Search API endpoint with clause-level hybrid search and AI summaries.

Returns clause-centric results grouped by file, with optional per-clause summaries.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time
from collections import defaultdict

from app.services import search_query
from app.services.llm_engine import LLMEngine
from app.services.vector_store import VectorStore
from app.dependencies import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter()

# Simple in-memory cache (query -> (results, summary, timestamp))
_cache = {}
CACHE_TTL = 600  # 10 minutes

# ============================================================================
# Request/Response Models
# ============================================================================

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k_groups: int = Field(6, ge=1, le=20, description="Number of file groups to return")
    max_snippets_per_group: int = Field(3, ge=1, le=5, description="Max clauses per file group")
    enable_clause_summaries: bool = Field(False, description="Generate LLM summaries for top clauses (costly)")

class ClauseHit(BaseModel):
    """A single clause/chunk match from search."""
    file_name: str
    file_path: Optional[str] = None
    section_title: Optional[str] = None
    clause_text: str
    clause_snippet: str = Field(..., description="Markdown snippet with highlighted query terms")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Hybrid similarity score")
    match_type: str = Field(..., description="'semantic' or 'semantic+keyword'")
    chunk_index: Optional[int] = None
    clause_summary: Optional[str] = Field(None, description="Optional LLM-generated 1-2 sentence summary")
    display_clause_score: Optional[float] = Field(None, description="Optional clause score for UI display (same as similarity_score)")
    clause_type: Optional[str] = Field(None, description="Primary clause type (e.g., 'Termination', 'Payment', 'Governing Law')")

class FileSearchResult(BaseModel):
    """Search results for a single file, containing multiple clause hits."""
    file_name: str
    file_path: Optional[str] = None
    doc_score: float = Field(..., ge=0.0, le=1.0, description="Document-level relevance score")
    keyword_summary: str = Field(..., description="AI-generated summary explaining keyword context in this file (always present)")
    clauses: List[ClauseHit]

class SearchResponse(BaseModel):
    """Complete search response with overall summary and file-grouped clause results."""
    overall_summary: str = Field(..., description="AI-generated overall search summary (≤75 words)")
    total_matches: int = Field(..., description="Total number of clause matches across all files")
    query: str
    files: List[FileSearchResult]

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

# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    vector_store: VectorStore = Depends(get_vector_store)
):
    """
    Clause-level hybrid search with grouped results and AI summaries.
    
    Performs semantic vector search + keyword matching, groups results by file,
    and generates:
    - Per-file keyword summaries (≤40 words)
    - Overall search summary (≤75 words)
    - Optional per-clause summaries (if enable_clause_summaries=True)
    
    Returns clause-centric results with rich metadata (file_path, section_title, etc.).
    """
    try:
        start_time = time.time()
        logger.info(f"Search request: query='{request.query}', top_k={request.top_k_groups}, clause_summaries={request.enable_clause_summaries}")
        
        # Check cache
        cache_key = f"{request.query}|{request.top_k_groups}|{request.max_snippets_per_group}|{request.enable_clause_summaries}"
        if cache_key in _cache:
            cached_results, cached_summary, cached_time = _cache[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                logger.info(f"Cache hit for query: {request.query}")
                return SearchResponse(
                    overall_summary=cached_summary,
                    total_matches=sum(len(f.get("clauses", [])) for f in cached_results),
                    query=request.query,
                    files=[FileSearchResult(**file_data) for file_data in cached_results]
                )
        
        # Perform clause-level search
        logger.info(f"Starting clause-level search for query: '{request.query}'")
        file_groups = search_query.search_and_group(
            vector_store=vector_store,
            query=request.query,
            top_k_groups=request.top_k_groups,
            max_snippets_per_group=request.max_snippets_per_group,
            enable_clause_summaries=request.enable_clause_summaries
        )
        
        logger.info(f"Search returned {len(file_groups)} file groups")
        if not file_groups:
            logger.warning(f"No groups found for query: '{request.query}' - check similarity threshold and vector store content")
        
        # Generate per-file keyword context summaries (REQUIRED for all files)
        for group in file_groups:
            filename = group.get("filename", "Unknown")
            clauses = group.get("clauses", [])
            
            # Ensure keyword_summary exists (generate if missing)
            if not group.get("keyword_summary") or not group.get("keyword_summary").strip():
                # Convert clauses to chunk format for LLM summary
                # Use original content (before truncation) if available for better summaries
                chunks_for_summary = []
                for clause in clauses[:3]:  # Use top 3 clauses for context
                    # Prefer original content for summaries, fallback to truncated or snippet
                    clause_text = clause.get("_original_content") or clause.get("clause_text", "") or clause.get("clause_snippet", "")
                    if clause_text:
                        chunks_for_summary.append({
                            "content": clause_text,
                            "metadata": {"file_name": filename}
                        })
                
                # Generate AI summary for this file's keyword context
                try:
                    if chunks_for_summary:
                        # Use more words for better summaries (60 instead of 40)
                        keyword_summary = LLMEngine.summarize_file_keyword_context(
                            filename=filename,
                            keyword=request.query,
                            chunks=chunks_for_summary,
                            max_words=60  # Increased from 40 for more detailed summaries
                        )
                        # Log the generated summary for debugging
                        logger.info(f"Generated keyword summary for {filename}: {keyword_summary[:150]}...")
                    else:
                        # Fallback if no clause text available
                        keyword_summary = LLMEngine.summarize_file_keyword_context(
                            filename=filename,
                            keyword=request.query,
                            chunks=[{"content": f"Document: {filename}", "metadata": {"file_name": filename}}],
                            max_words=60
                        )
                    
                    # Only set if summary is not empty and not generic
                    if keyword_summary and keyword_summary.strip():
                        # Check if it's the generic fallback message
                        generic_phrases = [
                            "relevant content found",
                            "no relevant content",
                            "relevance to the query"
                        ]
                        is_generic = any(phrase in keyword_summary.lower() for phrase in generic_phrases)
                        
                        if not is_generic:
                            group["keyword_summary"] = keyword_summary
                        else:
                            logger.warning(f"Generated summary appears generic for {filename}: {keyword_summary[:100]}...")
                            # Still use it, but log the issue
                            group["keyword_summary"] = keyword_summary
                    else:
                        logger.error(f"Generated summary was empty for {filename}")
                        group["keyword_summary"] = f"Relevant content found for '{request.query}' in this document."
                except Exception as e:
                    logger.error(f"Failed to generate keyword summary for {filename}: {e}", exc_info=True)
                    # Fallback summary only on exception
                    group["keyword_summary"] = f"Relevant content found for '{request.query}' in this document."
        
        # Generate overall summary via shared LLM
        if file_groups:
            # Flatten top clauses across groups for context
            top_chunks = []
            for g in file_groups[:request.top_k_groups]:
                for clause in g.get("clauses", [])[:request.max_snippets_per_group]:
                    top_chunks.append({
                        "content": clause.get("clause_snippet", clause.get("clause_text", "")),
                        "metadata": {"file_name": g.get("filename", "Unknown")},
                    })
            summary = LLMEngine.summarize(request.query, top_chunks, max_words=75)
        else:
            summary = "No matching clauses found."
        
        # Calculate total matches
        total_matches = sum(len(g.get("clauses", [])) for g in file_groups)
        
        # Cache results
        _cache[cache_key] = (file_groups, summary, time.time())
        
        # Clean old cache entries (simple cleanup)
        if len(_cache) > 100:
            _cache.clear()  # Simple approach: clear all when too large
        
        elapsed = time.time() - start_time
        logger.info(f"Search completed in {elapsed:.2f}s, found {len(file_groups)} file groups with {total_matches} total clauses")
        
        # Log final response details
        if file_groups:
            logger.info(f"Returning {len(file_groups)} file groups with {total_matches} total clause matches")
            for i, group in enumerate(file_groups, 1):
                logger.debug(f"  Group {i}: {group.get('filename')} - {len(group.get('clauses', []))} clauses, doc_score={group.get('doc_score', 0):.3f}")
        else:
            logger.warning(f"Returning empty results for query: '{request.query}'")
        
        # Convert to response models
        file_results = []
        for group in file_groups:
            clause_hits = []
            for clause_data in group.get("clauses", []):
                clause_hits.append(ClauseHit(
                    file_name=clause_data.get("file_name", group.get("filename", "Unknown")),
                    file_path=clause_data.get("file_path"),
                    section_title=clause_data.get("section_title"),
                    clause_text=clause_data.get("clause_text", ""),
                    clause_snippet=clause_data.get("clause_snippet", ""),
                    similarity_score=clause_data.get("similarity_score", 0.0),
                    match_type=clause_data.get("match_type", "semantic"),
                    chunk_index=clause_data.get("chunk_index"),
                    clause_summary=clause_data.get("clause_summary"),
                    display_clause_score=clause_data.get("display_clause_score"),
                    clause_type=clause_data.get("clause_type")
                ))
            
            # Ensure keyword_summary is always present
            keyword_summary = group.get("keyword_summary", "")
            if not keyword_summary or not keyword_summary.strip():
                keyword_summary = f"Relevant content found for '{request.query}' in this document."
            
            file_results.append(FileSearchResult(
                file_name=group.get("filename", "Unknown"),
                file_path=group.get("file_path"),
                doc_score=group.get("doc_score", 0.0),
                keyword_summary=keyword_summary,
                clauses=clause_hits
            ))
        
        return SearchResponse(
            overall_summary=summary,
            total_matches=total_matches,
            query=request.query,
            files=file_results
        )
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/status", response_model=IndexStatusResponse)
async def get_index_status(
    vector_store: VectorStore = Depends(get_vector_store)
):
    """
    Get the current status of the search index, including all indexed documents.
    """
    try:
        
        # Get all documents from ChromaDB
        all_docs = vector_store.collection.get(include=['metadatas'])
        
        if not all_docs.get('metadatas'):
            return IndexStatusResponse(
                status="empty",
                total_files=0,
                total_chunks=0,
                documents=[]
            )
        
        # Group chunks by file
        file_groups = defaultdict(list)
        for metadata in all_docs['metadatas']:
            file_name = metadata.get('file_name', 'Unknown')
            file_id = metadata.get('file_id', file_name)
            file_groups[(file_id, file_name)].append(metadata)
        
        # Build document list
        documents = []
        for (file_id, filename), file_metadatas in file_groups.items():
            # Determine source based on metadata
            source = "local"  # Default
            if file_metadatas and "source" in file_metadatas[0]:
                source = file_metadatas[0]["source"]
            
            documents.append(IndexedDocument(
                file_id=file_id,
                filename=filename,
                chunk_count=len(file_metadatas),
                source=source
            ))
        
        # Sort by filename
        documents.sort(key=lambda d: d.filename)
        
        return IndexStatusResponse(
            status="ready",
            total_files=len(documents),
            total_chunks=len(all_docs['metadatas']),
            documents=documents
        )
        
    except Exception as e:
        logger.error(f"Failed to get index status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get index status: {str(e)}")
