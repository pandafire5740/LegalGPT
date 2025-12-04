"""Extract endpoints for LegalGPT - extract terms from files in memory."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import io
import csv
import logging

from app.services.vector_store import VectorStore
from app.services.document_processor import DocumentProcessor
from app.services.llm_engine import LLMEngine
from app.dependencies import get_vector_store

router = APIRouter()
logger = logging.getLogger(__name__)


class ExtractFromMemoryRequest(BaseModel):
    """Request to extract terms from a file already in memory."""
    filename: str


@router.post("/")
async def extract_from_files(
    files: List[UploadFile] = File(...),
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Accept files, extract text, run clause extraction via shared LLM."""
    try:
        processor = DocumentProcessor(vector_store)

        rows: List[Dict[str, Any]] = []
        for up in files:
            content = await up.read()
            try:
                text = processor.extract_text(content, up.filename)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Text extract failed for {up.filename}: {e}")
                rows.append({
                    "filename": up.filename,
                    "counterparty": "",
                    "effective_date": "",
                    "expiration_or_renewal": "",
                    "payment_terms": "",
                    "status": "Error",
                })
                continue

            # Invoke LLM clause extraction
            items = []
            try:
                items = LLMEngine.extract_terms(text)
            except Exception as e:  # noqa: BLE001
                logger.error(f"LLM extract failed for {up.filename}: {e}")

            # Map to expected columns (best-effort)
            def find_field(name: str) -> str:
                for it in items:
                    if it.get("field") and name.lower() in it["field"].lower():
                        return str(it.get("value", ""))
                return ""

            rows.append({
                "filename": up.filename,
                "counterparty": find_field("counterparty"),
                "effective_date": find_field("effective date"),
                "expiration_or_renewal": find_field("expiration") or find_field("renewal"),
                "payment_terms": find_field("payment"),
                "status": "Success",
            })

        return {"status": "success", "rows": rows}

    except Exception as e:  # noqa: BLE001
        logger.error(f"Extract API failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-memory")
async def extract_from_memory(
    request: ExtractFromMemoryRequest,
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """Extract key terms from a file already indexed in vector store."""
    try:
        
        # Get all chunks for this file
        chunks = vector_store.search_by_file(request.filename)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"File '{request.filename}' not found in memory")
        
        # Reconstruct full text from chunks (sorted by chunk_index if available)
        def get_chunk_index(chunk):
            md = chunk.get("metadata", {})
            return md.get("chunk_index", 0)
        
        chunks_sorted = sorted(chunks, key=get_chunk_index)
        full_text = "\n\n".join([c.get("content", "") for c in chunks_sorted])
        
        logger.info(f"Extracting terms from {request.filename}, text length: {len(full_text)}")
        
        # Extract key terms using GPT-4o with improved prompt
        terms = LLMEngine.extract_terms(full_text, expected_fields=[
            "parties", "counterparty", "effective_date", "expiration_date", 
            "renewal_terms", "termination_clause", "payment_terms", 
            "governing_law", "confidentiality", "liability_cap", "indemnification"
        ])
        
        # Analyze contract sentiment
        sentiment = None
        try:
            sentiment = LLMEngine.analyze_contract_sentiment(full_text, terms)
            logger.info(f"Sentiment analysis completed: score={sentiment.get('score')}, label={sentiment.get('label')}")
        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            # Continue without sentiment if analysis fails
        
        response = {
            "status": "success",
            "filename": request.filename,
            "terms": terms,
            "text_length": len(full_text),
            "chunks_count": len(chunks)
        }
        
        if sentiment:
            response["sentiment"] = sentiment
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"Extract from memory failed for {request.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files-in-memory")
async def list_files_in_memory(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """List all files available for extraction (indexed in vector store)."""
    try:
        all_docs = vector_store.collection.get(limit=1000, include=['metadatas'])
        
        # Get unique filenames
        unique_files = set()
        for metadata in all_docs.get('metadatas', []):
            if metadata and 'file_name' in metadata:
                unique_files.add(metadata['file_name'])
        
        files = sorted(list(unique_files))
        
        return {
            "status": "success",
            "files": files,
            "total_count": len(files)
        }
        
    except Exception as e:  # noqa: BLE001
        logger.error(f"List files failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ExportRequest(BaseModel):
    """Request body for CSV export."""
    rows: List[Dict[str, Any]]


@router.post("/export")
async def export_rows(request: ExportRequest) -> StreamingResponse:
    """Return CSV file from provided rows."""
    try:
        rows = request.rows
        if not rows:
            raise HTTPException(status_code=400, detail="No rows to export")
        
        # Determine fieldnames dynamically from all rows
        all_fieldnames = set()
        for row in rows:
            all_fieldnames.update(row.keys())
        
        # Always include filename first, then sort the rest
        fieldnames = ["filename"] + sorted([f for f in all_fieldnames if f != "filename"])
        
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        buffer.seek(0)
        return StreamingResponse(
            io.BytesIO(buffer.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=extraction_results.csv"},
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/")
async def get_prompt_templates() -> Dict[str, Any]:
    """Get prompt templates (returns empty array if no templates configured)."""
    try:
        # Return empty templates array for now
        # TODO: Load from prompts/prompts.json if needed
        return {
            "status": "success",
            "templates": []
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get prompt templates: {e}")
        return {
            "status": "success",
            "templates": []
        }


