"""System Context Assembler for LegalGPT.

Assembles inventory, index stats, schemas (if available), and retrieved chunks
to support intent-aware prompting for Chat and Search.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import logging
import os
import re
import tiktoken

from app.services.vector_store import VectorStore
from app.config import settings

logger = logging.getLogger(__name__)

# Token encoder for GPT-4o (cl100k_base encoding)
_token_encoder = None


def _get_token_encoder():
    """Get or create the token encoder (singleton)."""
    global _token_encoder
    if _token_encoder is None:
        _token_encoder = tiktoken.get_encoding("cl100k_base")
    return _token_encoder


def _count_tokens(text: str) -> int:
    """Count tokens in text using GPT-4o encoding."""
    if not text:
        return 0
    try:
        encoder = _get_token_encoder()
        return len(encoder.encode(text))
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, falling back to character estimate")
        # Fallback: approximate 1 token = 4 characters
        return len(text) // 4


def _truncate_chunk_content(chunk: Dict[str, Any], max_chars: int = 1000) -> Dict[str, Any]:
    """
    Truncate chunk content to max_chars while preserving structure.
    
    Args:
        chunk: Chunk dictionary with 'content' key
        max_chars: Maximum characters to keep
        
    Returns:
        Modified chunk with truncated content
    """
    content = chunk.get("content", "")
    if len(content) <= max_chars:
        return chunk
    
    # Truncate at word boundary if possible
    truncated = content[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.9:  # If we're close to a word boundary
        truncated = truncated[:last_space]
    
    result = chunk.copy()
    result["content"] = truncated + "..."
    return result


def _prioritize_and_limit_chunks(
    chunks: List[Dict[str, Any]], 
    max_chunks: int = 12,
    max_total_tokens: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Prioritize chunks by relevance score and limit to max_chunks.
    
    Args:
        chunks: List of chunk dictionaries
        max_chunks: Maximum number of chunks to return
        max_total_tokens: Optional maximum total tokens across all chunks
        
    Returns:
        Prioritized and limited list of chunks
    """
    if not chunks:
        return []
    
    # Sort by relevance score (final_score > similarity_score > 0)
    def get_score(chunk: Dict[str, Any]) -> float:
        return (
            chunk.get("final_score", 0.0) or
            chunk.get("similarity_score", 0.0) or
            0.0
        )
    
    sorted_chunks = sorted(chunks, key=get_score, reverse=True)
    
    # Limit by chunk count
    limited = sorted_chunks[:max_chunks]
    
    # Optionally limit by total tokens
    if max_total_tokens:
        result = []
        total_tokens = 0
        for chunk in limited:
            content = chunk.get("content", "")
            chunk_tokens = _count_tokens(content)
            if total_tokens + chunk_tokens <= max_total_tokens:
                result.append(chunk)
                total_tokens += chunk_tokens
            else:
                break
        return result
    
    return limited


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


def assemble_context(vs: VectorStore, query: str, n_results: int = 10, require_keyword: bool = True) -> Dict[str, Any]:
    """Build context for a query suitable for inventory or RAG answering.

    Args:
        vs: VectorStore instance to use for queries
        query: User query string
        n_results: Number of results to retrieve
        require_keyword: Whether to require keyword matches

    Returns keys: inventory, index_stats, schemas, retrieved_chunks
    """
    try:
        inventory = vs.get_inventory()
    except Exception as e:
        logger.warning(f"Inventory fetch failed: {e}")
        inventory = []
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
    # Limit targeted chunks to prevent context window pollution
    max_targeted_chunks_per_file = 5  # Limit chunks per targeted file
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
            # Limit chunks per file and truncate content
            limited_chunks = chunks[:max_targeted_chunks_per_file]
            for chunk in limited_chunks:
                chunk_id = str(chunk.get("id")) if chunk.get("id") is not None else None
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)
                # Truncate chunk content to prevent context pollution
                truncated_chunk = _truncate_chunk_content(chunk, max_chars=1000)
                targeted_chunks.append(truncated_chunk)

    retrieved.extend(targeted_chunks)

    # General retrieval fallback (hybrid search)
    # Request more results than needed since we'll prioritize and limit
    try:
        general_results = vs.hybrid_search(query, n_results=n_results * 2, require_keyword=require_keyword)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Retrieval failed: {e}")
        general_results = []

    # Add general results, avoiding duplicates and truncating content
    for chunk in general_results:
        chunk_id = str(chunk.get("id")) if chunk.get("id") is not None else None
        if chunk_id and chunk_id in seen_chunk_ids:
            continue
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        # Truncate chunk content
        truncated_chunk = _truncate_chunk_content(chunk, max_chars=1000)
        retrieved.append(truncated_chunk)

    # Prioritize by relevance score and limit total chunks
    # Use max 12 chunks total (targeted + general) to stay within context window
    max_total_chunks = 12
    retrieved = _prioritize_and_limit_chunks(retrieved, max_chunks=max_total_chunks)
    
    # Log context window usage for monitoring
    total_chars = sum(len(chunk.get("content", "")) for chunk in retrieved)
    total_tokens = sum(_count_tokens(chunk.get("content", "")) for chunk in retrieved)
    logger.info(
        f"Context assembled: {len(retrieved)} chunks, "
        f"{total_chars} chars, ~{total_tokens} tokens"
    )

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


