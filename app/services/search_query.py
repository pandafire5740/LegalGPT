"""
Search query processing: ChromaDB search, keyword boost, grouping, and snippet extraction.
Uses OpenAI embeddings (text-embedding-3-small).
"""
import re
import logging
from typing import List, Dict, Any
from collections import defaultdict

from app.services.vector_store import VectorStore
from app.config import settings

logger = logging.getLogger(__name__)


def apply_keyword_boost(query: str, chunk_text: str, base_score: float) -> float:
    """
    Apply light keyword boost if exact query phrase appears in chunk.
    +0.05 to score if query phrase is found (case-insensitive).
    """
    query_lower = query.lower()
    chunk_lower = chunk_text.lower()
    
    if query_lower in chunk_lower:
        return base_score + 0.05
    return base_score


def group_by_file(chunks_with_scores: List[Dict[str, Any]], max_snippets_per_file: int = 3) -> List[Dict[str, Any]]:
    """
    Group chunks by file and keep top N per file.
    Calculate doc_score = max(snippet_scores) + 0.02 * min(2, num_snippets)
    """
    # Group by file_name
    file_groups = defaultdict(list)
    for chunk in chunks_with_scores:
        file_name = chunk.get("metadata", {}).get("file_name", "Unknown")
        file_id = chunk.get("id", "")
        score = chunk.get("similarity_score", 0.0)
        file_groups[file_name].append({
            "chunk": chunk,
            "score": score,
            "file_id": file_id
        })
    
    logger.debug(f"Grouped chunks into {len(file_groups)} unique files")
    
    # Process each file group
    groups = []
    for file_name, file_chunks in file_groups.items():
        # Sort by score and keep top N
        file_chunks.sort(key=lambda x: x["score"], reverse=True)
        original_count = len(file_chunks)
        file_chunks = file_chunks[:max_snippets_per_file]
        
        # Calculate doc_score
        scores = [fc["score"] for fc in file_chunks]
        max_score = max(scores) if scores else 0.0
        num_snippets = len(file_chunks)
        doc_score = max_score + 0.02 * min(2, num_snippets)
        
        logger.debug(f"File '{file_name}': {original_count} chunks -> {num_snippets} kept, max_score={max_score:.3f}, doc_score={doc_score:.3f}")
        
        # Get file_id from metadata (use first chunk's file_id or filename)
        file_id = file_chunks[0]["chunk"].get("metadata", {}).get("file_id", file_name) if file_chunks else file_name
        
        groups.append({
            "file_id": file_id,
            "filename": file_name,
            "doc_score": doc_score,
            "chunks": file_chunks
        })
    
    # Sort groups by doc_score
    groups.sort(key=lambda x: x["doc_score"], reverse=True)
    
    logger.info(f"Grouped {len(chunks_with_scores)} chunks into {len(groups)} file groups")
    return groups


def extract_snippet(chunk_text: str, query: str, chunk_position: int = 0) -> Dict[str, Any]:
    """
    Extract a 2-3 sentence snippet around the best match.
    Bold exact query matches.
    """
    # Split into sentences (simple approach)
    sentences = re.split(r'(?<=[.!?])\s+', chunk_text)
    
    # Find sentence(s) containing query terms
    query_words = set(query.lower().split())
    best_sent_idx = 0
    best_match_count = 0
    
    for i, sent in enumerate(sentences):
        sent_lower = sent.lower()
        match_count = sum(1 for word in query_words if word in sent_lower)
        if match_count > best_match_count:
            best_match_count = match_count
            best_sent_idx = i
    
    # Extract 2-3 sentences around the best match
    start_idx = max(0, best_sent_idx - 1)
    end_idx = min(len(sentences), best_sent_idx + 2)
    snippet_sentences = sentences[start_idx:end_idx]
    snippet_text = " ".join(snippet_sentences).strip()
    
    # Bold exact matches (case-insensitive)
    for word in query_words:
        if len(word) > 2:  # Only bold meaningful words
            pattern = re.compile(fr'(\b{re.escape(word)}\b)', re.IGNORECASE)
            snippet_text = pattern.sub(r'**\1**', snippet_text)
    
    return {
        "text": snippet_text,
        "position": chunk_position
    }


def search_and_group(vector_store: VectorStore, query: str, top_k_groups: int = 6, max_snippets_per_group: int = 3) -> List[Dict[str, Any]]:
    """
    Main search flow:
    1. Search ChromaDB (get enough results for grouping)
    2. Apply keyword boost
    3. Group by file (top N per file)
    4. Return top K groups with snippets
    
    Args:
        vector_store: VectorStore instance to use for search
        query: Search query string
        top_k_groups: Number of file groups to return
        max_snippets_per_group: Maximum snippets per file group
    """
    logger.info(f"=== SEARCH START: query='{query}', top_k_groups={top_k_groups}, max_snippets_per_group={max_snippets_per_group}")
    
    # Get more results than needed to account for grouping and filtering
    # We want top_k_groups * max_snippets_per_group, but get more for diversity
    n_results = top_k_groups * max_snippets_per_group * 3  # Get extra for diversity
    logger.debug(f"Requesting {n_results} results from vector store")
    
    # 1. Search ChromaDB
    search_results = vector_store.search_similar(query, n_results=n_results)
    
    if not search_results:
        logger.warning(f"No search results found for query: '{query}'")
        return []
    
    logger.info(f"Vector store returned {len(search_results)} results")
    if search_results:
        scores = [r.get("similarity_score", 0.0) for r in search_results]
        logger.info(f"Score range: min={min(scores):.3f}, max={max(scores):.3f}, avg={sum(scores)/len(scores):.3f}")
        logger.debug(f"Top 5 scores: {[f'{s:.3f}' for s in scores[:5]]}")
    
    # 2. Apply keyword boost
    boosted_results = []
    boost_count = 0
    for result in search_results:
        content = result.get("content", "")
        base_score = result.get("similarity_score", 0.0)
        boosted_score = apply_keyword_boost(query, content, base_score)
        
        if boosted_score > base_score:
            boost_count += 1
            logger.debug(f"Keyword boost applied: {base_score:.3f} -> {boosted_score:.3f}")
        
        # Update the score
        result["similarity_score"] = boosted_score
        boosted_results.append(result)
    
    logger.info(f"Applied keyword boost to {boost_count}/{len(search_results)} chunks")
    
    # Re-sort after boosting
    boosted_results.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)
    
    # 3. Group by file
    groups = group_by_file(boosted_results, max_snippets_per_file=max_snippets_per_group)
    
    logger.info(f"Created {len(groups)} file groups before threshold filtering")
    for i, group in enumerate(groups[:10]):  # Log top 10 groups
        logger.debug(f"Group {i+1}: {group['filename']} - doc_score={group['doc_score']:.3f} ({group['doc_score']*100:.1f}%), chunks={len(group['chunks'])}")
    
    # 4. Filter groups by similarity threshold
    threshold = settings.search_similarity_threshold
    filtered_groups = [g for g in groups if g["doc_score"] >= threshold]
    
    if not filtered_groups:
        logger.warning(f"No groups met similarity threshold of {threshold:.2f} ({threshold*100:.0f}%)")
        if groups:
            logger.warning(f"Top group score was {groups[0]['doc_score']:.3f} ({groups[0]['doc_score']*100:.1f}%) from file '{groups[0]['filename']}'")
        return []
    
    logger.info(f"Filtered {len(groups)} groups to {len(filtered_groups)} groups above threshold {threshold:.2f} ({threshold*100:.0f}%)")
    for group in filtered_groups:
        logger.info(f"  ✓ {group['filename']}: doc_score={group['doc_score']:.3f} ({group['doc_score']*100:.1f}%), {len(group['chunks'])} chunks")
    
    # 5. Extract snippets and format results
    results = []
    for group in filtered_groups[:top_k_groups]:
        snippets = []
        filename = group["filename"]
        logger.debug(f"Processing snippets for file: {filename}")
        
        for chunk_idx, chunk_data in enumerate(group["chunks"]):
            chunk = chunk_data["chunk"]
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {})
            chunk_position = metadata.get("chunk_index", 0)
            score = chunk_data["score"]
            
            # Check if query keywords appear in content
            query_lower = query.lower()
            content_lower = content.lower()
            keyword_found = query_lower in content_lower or any(word in content_lower for word in query_lower.split() if len(word) > 2)
            
            snippet = extract_snippet(content, query, chunk_position)
            snippet["score"] = score
            snippets.append(snippet)
            
            logger.debug(f"  Chunk {chunk_idx+1}: score={score:.3f}, keyword_in_content={keyword_found}, position={chunk_position}, snippet_length={len(snippet['text'])}")
        
        results.append({
            "file_id": group["file_id"],
            "filename": group["filename"],
            "doc_score": group["doc_score"],
            "snippets": snippets
        })
    
    logger.info(f"=== SEARCH COMPLETE: Returning {len(results)} file groups for query '{query}'")
    if results:
        result_summary = ", ".join([f"{r['filename']} ({r['doc_score']*100:.0f}%)" for r in results])
        logger.info(f"Final results: {result_summary}")
    return results
