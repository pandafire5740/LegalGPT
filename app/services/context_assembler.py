"""System Context Assembler for LegalGPT.

Assembles inventory, index stats, schemas (if available), and retrieved chunks
to support intent-aware prompting for Chat and Search.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from app.services.vector_store import VectorStore
from app.config import settings

logger = logging.getLogger(__name__)


def _safe_iso(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        # pass-through if already iso-like
        datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return ts
    except Exception:
        return str(ts)


def _gather_inventory(vs: VectorStore) -> List[Dict[str, Any]]:
    try:
        data = vs.collection.get(limit=10000, include=["metadatas"])  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning(f"Inventory fetch failed: {e}")
        return []
    inv: Dict[str, Dict[str, Any]] = {}
    for md in (data.get("metadatas") or []):
        if not md:
            continue
        fname = md.get("file_name")
        if not fname:
            continue
        item = inv.get(fname)
        if not item:
            item = {
                "filename": fname,
                "chunks_or_pages": 0,
                "last_indexed": _safe_iso(md.get("time_modified")),
                "size": md.get("file_size") or 0,
            }
            inv[fname] = item
        item["chunks_or_pages"] = int(item.get("chunks_or_pages", 0)) + 1
        # Update last_indexed to the most recent if available
        lm = md.get("time_modified")
        if lm:
            cur = item.get("last_indexed")
            if not cur:
                item["last_indexed"] = _safe_iso(lm)
    return list(inv.values())


def _index_stats(vs: VectorStore) -> Dict[str, Any]:
    try:
        stats = vs.get_collection_stats()
    except Exception as e:
        logger.warning(f"Index stats fetch failed: {e}")
        stats = {"total_chunks": 0, "unique_files": 0}
    try:
        emb_name = getattr(vs.embedding_model, "__class__", type(vs.embedding_model)).__name__
    except Exception:
        emb_name = "unknown"
    return {
        "total_files": stats.get("unique_files", 0),
        "total_chunks": stats.get("total_chunks", 0),
        "embedding_model": emb_name,
        "index_path": settings.chroma_persist_directory,
    }


def assemble_context(query: str, n_results: int = 10, require_keyword: bool = True) -> Dict[str, Any]:
    """Build context for a query suitable for inventory or RAG answering.

    Returns keys: inventory, index_stats, schemas, retrieved_chunks
    """
    vs = VectorStore()
    inventory = _gather_inventory(vs)
    idx_stats = _index_stats(vs)
    # Schemas: placeholder for future discovery; return [] gracefully
    schemas: List[Dict[str, Any]] = []
    # Retrieval for RAG
    try:
        retrieved = vs.hybrid_search(query, n_results=n_results, require_keyword=require_keyword)
    except Exception as e:
        logger.warning(f"Retrieval failed: {e}")
        retrieved = []
    return {
        "inventory": inventory,
        "index_stats": idx_stats,
        "schemas": schemas,
        "retrieved_chunks": retrieved,
    }


