"""System Context Assembler for LegalGPT.

Assembles inventory, index stats, schemas (if available), and retrieved chunks
to support intent-aware prompting for Chat and Search.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import logging
import os
import re

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


def _normalize_fragment(value: str) -> str:
    """Normalize text for fuzzy filename matching."""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _generate_aliases(filename: str) -> List[str]:
    """Generate matchable aliases (with/without extension, separators) for a filename."""
    base, ext = os.path.splitext(filename)
    variants = {
        filename.lower(),
        base.lower(),
        re.sub(r"[_\-]+", " ", base.lower()).strip(),
    }
    compact = re.sub(r"[^a-z0-9]", "", base.lower())
    if compact:
        variants.add(compact)
    variants = {v for v in variants if v}
    return list(variants)


def _detect_file_targets(
    query: str,
    inventory: List[Dict[str, Any]],
    max_matches: int = 4,
) -> Tuple[List[str], Dict[str, float]]:
    """Return filenames referenced in the query with a basic confidence score."""
    if not query or not inventory:
        return [], {}

    lowered_query = query.lower()
    normalized_query = _normalize_fragment(query)
    query_tokens = set(normalized_query.split()) if normalized_query else set()

    # Capture quoted fragments as strong hints ("contract name", etc.)
    quoted_fragments: List[str] = []
    for match in re.findall(r'"([^"]+)"|\'([^\']+)\'|`([^`]+)`', query):
        fragment = next((m for m in match if m), "")
        if fragment:
            normalized = _normalize_fragment(fragment)
            if normalized:
                quoted_fragments.append(normalized)

    scored: List[Tuple[float, str]] = []
    for item in inventory:
        filename = (item or {}).get("filename")
        if not filename:
            continue

        aliases = _generate_aliases(filename)
        best_score = 0.0
        for alias in aliases:
            alias_norm = _normalize_fragment(alias)
            if not alias_norm:
                continue

            # Direct substring match on raw query (handles full filename with extension)
            if alias in lowered_query:
                best_score = max(best_score, len(alias) + 10)
                continue

            # Substring match on normalized query (handles spaces vs underscores)
            if alias_norm and alias_norm in normalized_query:
                best_score = max(best_score, len(alias_norm) + 5)

            alias_tokens = [tok for tok in alias_norm.split() if len(tok) > 2]
            if alias_tokens and all(tok in query_tokens for tok in alias_tokens):
                best_score = max(best_score, 5.0 * len(alias_tokens))

            if alias_norm in quoted_fragments:
                best_score = max(best_score, len(alias_norm) + 15)

        # Avoid spurious matches on very short names (e.g., NDA -> 3 chars)
        if best_score > 0 and len(filename) >= 4:
            scored.append((best_score, filename))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[:max_matches]
    scores = {name: score for score, name in top}
    return [name for _, name in top], scores


def assemble_context(query: str, n_results: int = 10, require_keyword: bool = True) -> Dict[str, Any]:
    """Build context for a query suitable for inventory or RAG answering.

    Returns keys: inventory, index_stats, schemas, retrieved_chunks
    """
    vs = VectorStore()
    inventory = _gather_inventory(vs)
    idx_stats = _index_stats(vs)
    # Schemas: placeholder for future discovery; return [] gracefully
    schemas: List[Dict[str, Any]] = []
    targeted_filenames, match_scores = _detect_file_targets(query, inventory)
    processed_query = query.strip()
    if targeted_filenames:
        hints = []
        for fname in targeted_filenames:
            score = match_scores.get(fname, 0)
            hints.append(f"focus:{fname} (confidence={score:.1f})")
        hint_block = "\n".join(hints)
        processed_query = (
            "Respond using structured sections. Give concise bullet lists with blank lines between topics.\n" \
            "Report how findings relate to each targeted file.\n" \
            "Mention if a requested file is missing.\n" \
            f"Targets:\n{hint_block}\n\nUser question:\n{query}"
        )

    retrieved: List[Dict[str, Any]] = []
    targeted_chunks: List[Dict[str, Any]] = []
    targeted_found: set[str] = set()
    missing_filenames: List[str] = []
    seen_chunk_ids: set[str] = set()

    # Retrieve targeted documents first so they are prioritized in the RAG context
    if targeted_filenames:
        for filename in targeted_filenames:
            try:
                chunks = vs.search_by_file(filename)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Targeted retrieval failed for {filename}: {exc}")
                chunks = []

            if not chunks:
                missing_filenames.append(filename)
                continue

            targeted_found.add(filename)
            for chunk in chunks:
                chunk_id = str(chunk.get("id")) if chunk.get("id") is not None else None
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)
                targeted_chunks.append(chunk)

    retrieved.extend(targeted_chunks)

    # General retrieval fallback (hybrid search)
    try:
        general_results = vs.hybrid_search(query, n_results=n_results, require_keyword=require_keyword)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Retrieval failed: {e}")
        general_results = []

    max_total = max(n_results, len(targeted_chunks))
    for chunk in general_results:
        chunk_id = str(chunk.get("id")) if chunk.get("id") is not None else None
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        retrieved.append(chunk)
        if len(retrieved) >= max_total:
            break

    return {
        "inventory": inventory,
        "index_stats": idx_stats,
        "schemas": schemas,
        "retrieved_chunks": retrieved,
        "targeted_filenames": targeted_filenames,
        "targeted_matches": match_scores,
        "targeted_found": sorted(targeted_found),
        "missing_filenames": missing_filenames,
        "targeted_chunks": targeted_chunks,
    }


