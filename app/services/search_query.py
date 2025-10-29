"""
Search query processing: ChromaDB search, keyword boost, grouping, and snippet extraction.
Uses OpenAI embeddings (text-embedding-3-small).
"""
import re
import logging
from typing import List, Dict, Any
from collections import defaultdict

from app.services.vector_store import VectorStore

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
    
    # Process each file group
    groups = []
    for file_name, file_chunks in file_groups.items():
        # Sort by score and keep top N
        file_chunks.sort(key=lambda x: x["score"], reverse=True)
        file_chunks = file_chunks[:max_snippets_per_file]
        
        # Calculate doc_score
        scores = [fc["score"] for fc in file_chunks]
        max_score = max(scores) if scores else 0.0
        num_snippets = len(file_chunks)
        doc_score = max_score + 0.02 * min(2, num_snippets)
        
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


def search_and_group(query: str, top_k_groups: int = 6, max_snippets_per_group: int = 3) -> List[Dict[str, Any]]:
    """
    Main search flow:
    1. Search ChromaDB (get enough results for grouping)
    2. Apply keyword boost
    3. Group by file (top N per file)
    4. Return top K groups with snippets
    """
    logger.info(f"Searching for: {query}")
    
    # Use VectorStore for search
    vector_store = VectorStore()
    
    # Get more results than needed to account for grouping and filtering
    # We want top_k_groups * max_snippets_per_group, but get more for diversity
    n_results = top_k_groups * max_snippets_per_group * 3  # Get extra for diversity
    
    # 1. Search ChromaDB
    search_results = vector_store.search_similar(query, n_results=n_results)
    
    if not search_results:
        logger.warning("No search results found")
        return []
    
    # 2. Apply keyword boost
    boosted_results = []
    for result in search_results:
        content = result.get("content", "")
        base_score = result.get("similarity_score", 0.0)
        boosted_score = apply_keyword_boost(query, content, base_score)
        
        # Update the score
        result["similarity_score"] = boosted_score
        boosted_results.append(result)
    
    # Re-sort after boosting
    boosted_results.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)
    
    # 3. Group by file
    groups = group_by_file(boosted_results, max_snippets_per_file=max_snippets_per_group)
    
    # 4. Extract snippets and format results
    results = []
    for group in groups[:top_k_groups]:
        snippets = []
        for chunk_data in group["chunks"]:
            chunk = chunk_data["chunk"]
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {})
            chunk_position = metadata.get("chunk_index", 0)
            score = chunk_data["score"]
            
            snippet = extract_snippet(content, query, chunk_position)
            snippet["score"] = score
            snippets.append(snippet)
        
        results.append({
            "file_id": group["file_id"],
            "filename": group["filename"],
            "doc_score": group["doc_score"],
            "snippets": snippets
        })
    
    logger.info(f"Returning {len(results)} file groups")
    return results
