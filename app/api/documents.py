"""Document management API endpoints."""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, UploadFile, File, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import unquote

from app.config import settings
from app.services.document_processor import DocumentProcessor
from app.services.vector_store import VectorStore
from app.services.llm_engine import LLMEngine
from app.dependencies import get_vector_store

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/list")
async def list_documents(
    folder_path: Optional[str] = Query(None, description="(deprecated) SharePoint folder path"),
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """List all documents known to the local vector store (SharePoint removed)."""
    try:
        all_docs = vector_store.collection.get(limit=1000, include=['metadatas'])
        unique_files = {}
        for md in all_docs.get('metadatas') or []:
            name = md.get('file_name', 'Unknown')
            if name not in unique_files:
                unique_files[name] = {
                    "name": name,
                    "file_path": md.get('file_path', ''),
                    "time_modified": md.get('time_modified', ''),
                    "author": md.get('author', 'Unknown'),
                    "chunk_count": 1
                }
            else:
                unique_files[name]["chunk_count"] += 1
        return {
            "status": "success",
            "files": list(unique_files.values()),
            "total_count": len(unique_files)
        }
    except Exception as e:
        logger.error(f"Failed to list documents, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.get("/search")
async def search_documents(
    query: str = Query(..., description="Search query"),
    n_results: int = Query(10, description="Number of results to return"),
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Search documents using vector similarity."""
    try:
        results = vector_store.hybrid_search(query, n_results=n_results)
        
        return {
            "status": "success",
            "query": query,
            "results": results,
            "total_results": len(results)
        }
        
    except Exception as e:
        logger.error(f"Failed to search documents, query: {query, error: {str(e)}}")
        raise HTTPException(status_code=500, detail=f"Document search failed: {str(e)}")


@router.get("/{file_name}/info")
async def get_document_info(
    file_name: str,
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Get detailed information about a specific document from local vector store."""
    try:
        chunks = vector_store.search_by_file(file_name)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"Document '{file_name}' not found in vector database")
        md = chunks[0]['metadata'] if chunks else {}
        file_info = {
            "name": file_name,
            "server_relative_url": md.get('file_path', ''),
            "time_last_modified": md.get('time_modified', ''),
            "author": md.get('author', 'Unknown'),
            "length": md.get('file_size', 0),
            "chunks_in_vector_store": len(chunks),
            "is_processed": len(chunks) > 0
        }
        return {"status": "success", "file_info": file_info}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document info, file_name: {file_name, error: {str(e)}}")
        raise HTTPException(status_code=500, detail=f"Failed to get document info: {str(e)}")


@router.get("/{file_name}/summary")
async def get_document_summary(
    file_name: str,
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Get AI-generated summary of a document using GPT-4o."""
    try:
        chunks = vector_store.search_by_file(file_name)
        
        if not chunks:
            raise HTTPException(status_code=404, detail=f"Document '{file_name}' not found")
        
        # Reconstruct text from chunks
        full_text = "\n\n".join([c.get("content", "") for c in chunks[:10]])
        
        # Generate summary using LLMEngine
        summary = LLMEngine.summarize_text(file_name, full_text, max_words=100)
        
        return {
            "status": "success",
            "file_name": file_name,
            "summary": summary,
            "chunks_analyzed": len(chunks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate summary, file_name: {file_name}, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


@router.post("/sync")
async def sync_documents(
    background_tasks: BackgroundTasks,
    force_refresh: bool = Query(False, description="(deprecated) Force refresh of all documents")
) -> Dict[str, Any]:
    """SharePoint sync removed; endpoint retained for compatibility."""
    return {
        "status": "success",
        "message": "SharePoint synchronization is disabled in this build. Use local upload.",
        "force_refresh": False
    }


@router.post("/{file_name}/process")
async def process_document(
    file_name: str,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Process a specific document and add to vector database."""
    try:
        # Start background processing
        background_tasks.add_task(
            _process_document_background,
            file_name=file_name
        )
        
        return {
            "status": "success",
            "message": f"Processing '{file_name}' started in background",
            "file_name": file_name
        }
        
    except Exception as e:
        logger.error(f"Failed to start document processing, file_name: {file_name, error: {str(e)}}")
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@router.delete("/{file_name}")
async def delete_document_from_vector_store(
    file_name: str,
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Remove a document from the vector database (not from Sharepoint)."""
    try:
        # URL decode the file name in case it's encoded
        from urllib.parse import unquote
        decoded_file_name = unquote(file_name)
        
        logger.info(f"Attempting to delete document: {decoded_file_name} (original: {file_name})")
        deleted_count = vector_store.delete_document_chunks(decoded_file_name)
        
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"Document '{decoded_file_name}' not found in vector database")
        
        logger.info(f"Successfully deleted {deleted_count} chunks for document: {decoded_file_name}")
        return {
            "status": "success",
            "message": f"Removed '{decoded_file_name}' from vector database",
            "deleted_chunks": deleted_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document, file_name: {file_name}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


class RenameRequest(BaseModel):
    new_name: str


@router.put("/{file_name}/rename")
async def rename_document(
    file_name: str,
    request: RenameRequest,
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Rename a document in the vector database."""
    try:
        # URL decode the file name
        from urllib.parse import unquote
        decoded_file_name = unquote(file_name)
        new_name = request.new_name.strip()
        
        # Validate new name
        if not new_name:
            raise HTTPException(status_code=400, detail="New file name cannot be empty")
        
        # Validate file name follows typical document naming conventions
        # Prevent path traversal, null bytes, and other dangerous characters
        invalid_chars = ['/', '\\', '\x00', '<', '>', ':', '"', '|', '?', '*']
        if any(char in new_name for char in invalid_chars):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file name. Cannot contain: {', '.join(invalid_chars)}"
            )
        
        # Check if new name already exists
        existing = vector_store.collection.get(
            where={"file_name": new_name}
        )
        if existing.get('ids') and len(existing['ids']) > 0:
            raise HTTPException(
                status_code=409, 
                detail=f"File '{new_name}' already exists in vector database"
            )
        
        # Check if old file exists
        old_file = vector_store.collection.get(
            where={"file_name": decoded_file_name}
        )
        if not old_file.get('ids') or len(old_file['ids']) == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"Document '{decoded_file_name}' not found in vector database"
            )
        
        logger.info(f"Attempting to rename document: {decoded_file_name} -> {new_name}")
        updated_count = vector_store.rename_document(decoded_file_name, new_name)
        
        if updated_count == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"Document '{decoded_file_name}' not found in vector database"
            )
        
        logger.info(f"Successfully renamed document: {decoded_file_name} -> {new_name}, chunks_updated: {updated_count}")
        return {
            "status": "success",
            "message": f"Renamed '{decoded_file_name}' to '{new_name}'",
            "old_name": decoded_file_name,
            "new_name": new_name,
            "chunks_updated": updated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rename document, file_name: {file_name}, new_name: {request.new_name}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rename document: {str(e)}")


@router.get("/stats")
async def get_document_stats(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Get statistics about the document collection (SharePoint removed)."""
    try:
        stats = vector_store.get_collection_stats()
        
        # SharePoint stats removed
        stats["sharepoint"] = {
            "total_files": 0,
            "file_types": {},
            "disabled": True
        }
        
        return {
            "status": "success",
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get document stats, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/stats/simple")
async def get_simple_stats(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Get simple document statistics without SharePoint dependency."""
    try:
        
        # Get all documents from vector store
        all_docs = vector_store.collection.get(
            limit=1000,
            include=['metadatas']
        )
        
        # Count unique documents
        unique_files = set()
        for metadata in all_docs['metadatas']:
            if metadata and 'file_name' in metadata:
                unique_files.add(metadata['file_name'])
        
        # Count total chunks
        total_chunks = len(all_docs['metadatas']) if all_docs['metadatas'] else 0
        
        return {
            "status": "success",
            "document_count": len(unique_files),
            "chunk_count": total_chunks,
            "files": list(unique_files)
        }
        
    except Exception as e:
        logger.error(f"Failed to get simple stats, error: {str(e)}")
        return {
            "status": "success",
            "document_count": 0,
            "chunk_count": 0,
            "files": []
        }


@router.post("/reset")
async def reset_documents_index(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Clear all indexed files and reset counters (vector store recreation)."""
    try:
        result = vector_store.reset_store()
        return {
            "status": "success",
            "message": "Vector store reset successfully",
            "stats": result
        }
    except Exception as e:
        logger.error(f"Failed to reset vector store, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset index: {str(e)}")


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Upload and process a local document."""
    try:
        # Validate file type
        allowed_extensions = {'.pdf', '.docx', '.doc', '.txt', '.rtf'}
        file_extension = os.path.splitext(file.filename)[1].lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"File type {file_extension} not supported. Allowed types: {', '.join(allowed_extensions)}"
            )
        
        # Ensure uploads directory exists
        uploads_dir = Path(settings.uploads_directory)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        
        # Check duplicates ONLY in vector store ("in memory"); allow overwriting disk file if not in memory
        file_path = uploads_dir / file.filename
        try:
            existing = vector_store.collection.get(where={"file_name": file.filename}, include=["ids"])
            if existing and existing.get("ids"):
                return {
                    "status": "exists",
                    "detail": f"File '{file.filename}' is already in memory.",
                    "file_name": file.filename
                }
        except Exception:
            # Non-fatal; continue with upload if vector store check fails
            pass

        # Read file content
        file_content = await file.read()
        
        # Save (or overwrite) file on disk; dedupe is enforced by vector store only
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"Saved uploaded file to: {file_path}")
        
        # Create file info metadata
        file_info = {
            "name": file.filename,
            "server_relative_url": f"/uploads/{file.filename}",
            "file_path": str(file_path),
            "time_last_modified": datetime.now().isoformat(),
            "author": "Local Upload",
            "length": len(file_content),
            "content_type": file.content_type
        }
        
        # Start background processing
        # Pass vector_store to background task to use the same instance
        background_tasks.add_task(
            _process_uploaded_document_background,
            file_content=file_content,
            file_info=file_info,
            vector_store=vector_store
        )
        
        # Generate quick LLM summary (<50 words) from raw text for UI feedback
        try:
            processor = DocumentProcessor(vector_store)
            extracted_text = processor.extract_text(file_content, file.filename)
            short_summary = LLMEngine.summarize_text(file.filename, extracted_text, max_words=50) if extracted_text else ""
        except Exception:
            short_summary = ""
        
        return {
            "status": "success",
            "message": f"Document '{file.filename}' uploaded and saved to {file_path}",
            "file_name": file.filename,
            "file_size": len(file_content),
            "file_path": str(file_path),
            "llm_summary": short_summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload document, filename: {file.filename if file else 'unknown'}, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.get("/local")
async def list_local_documents(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """List all locally uploaded documents."""
    try:
        
        # Get all documents and filter for local ones
        all_docs = vector_store.collection.get(
            limit=1000,
            include=['metadatas', 'documents']
        )
        
        # Filter for local/uploaded documents and group by file name
        unique_docs = {}
        for i, metadata in enumerate(all_docs['metadatas']):
            file_path = metadata.get('file_path', '')
            server_url = metadata.get('server_relative_url', '')
            # Accept both old /local/ format and new /uploads/ format
            if file_path.startswith('/local/') or server_url.startswith('/uploads/') or 'uploads' in file_path:
                file_name = metadata.get('file_name', 'Unknown')
                if file_name not in unique_docs:
                    unique_docs[file_name] = {
                        "name": file_name,
                        "file_path": metadata.get('file_path', file_path),
                        "time_last_modified": metadata.get('time_last_modified', metadata.get('time_modified', '')),
                        "author": metadata.get('author', 'Unknown'),
                        "file_size": metadata.get('file_size', 0),
                        "chunk_count": 1
                    }
                else:
                    unique_docs[file_name]["chunk_count"] += 1
        
        return {
            "status": "success",
            "files": list(unique_docs.values()),
            "total_count": len(unique_docs)
        }
        
    except Exception as e:
        logger.error(f"Failed to list local documents, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list local documents: {str(e)}")


@router.get("/{file_name}/download")
async def download_document(
    file_name: str,
    vector_store: VectorStore = Depends(get_vector_store)
):
    """
    Download a document file.
    
    First checks if the file exists in the uploads directory.
    If not found, tries to get the path from vector store metadata.
    """
    try:
        # URL decode the file name
        decoded_file_name = unquote(file_name)
        
        # Check if file exists in uploads directory
        uploads_dir = Path(settings.uploads_directory)
        file_path = uploads_dir / decoded_file_name
        
        if not file_path.exists():
            # Try to get file_path from vector store metadata
            chunks = vector_store.search_by_file(decoded_file_name)
            if chunks and chunks[0].get('metadata', {}).get('file_path'):
                metadata_path = chunks[0]['metadata']['file_path']
                # Handle both absolute and relative paths
                if os.path.isabs(metadata_path):
                    file_path = Path(metadata_path)
                else:
                    # Try relative to uploads directory
                    file_path = uploads_dir / metadata_path
                
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail=f"File '{decoded_file_name}' not found")
            else:
                raise HTTPException(status_code=404, detail=f"File '{decoded_file_name}' not found")
        
        # Determine media type based on file extension
        media_type_map = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain',
            '.rtf': 'application/rtf'
        }
        file_ext = file_path.suffix.lower()
        media_type = media_type_map.get(file_ext, 'application/octet-stream')
        
        return FileResponse(
            path=str(file_path),
            filename=decoded_file_name,
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download document, file_name: {decoded_file_name if 'decoded_file_name' in locals() else file_name}, error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download document: {str(e)}")


# Background task functions
async def _sync_documents_background(force_refresh: bool = False):
    """No-op: SharePoint sync removed."""
    logger.info("_sync_documents_background called, but SharePoint is disabled.")


async def _process_document_background(file_name: str):
    """Background task to process a specific document."""
    logger.info(f"_process_document_background called for {file_name}, but SharePoint is disabled.")


async def _process_uploaded_document_background(file_content: bytes, file_info: Dict[str, Any], vector_store: VectorStore):
    """Background task to process an uploaded document."""
    try:
        logger.info(f"Processing uploaded document, file_name: {file_info['name']}")
        
        document_processor = DocumentProcessor(vector_store)
        
        # Process the document
        result = document_processor.process_document(file_content, file_info)
        
        logger.info(f"Uploaded document processing completed, file_name: {file_info['name']}, result: {result['status']}")
        
    except Exception as e:
        logger.error(f"Uploaded document processing failed, file_name: {file_info['name']}, error: {str(e)}")
