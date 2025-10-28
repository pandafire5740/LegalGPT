"""
Search query processing: FAISS search, MMR diversification, grouping, and snippet extraction.
Uses OpenAI embeddings (text-embedding-3-small).
"""
import re
import logging
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import numpy as np
import faiss

from app.config import settings
from app.services import search_ingest

logger = logging.getLogger(__name__)

def embed_query(query: str) -> np.ndarray:
    """Generate embedding for search query using OpenAI text-embedding-3-small."""
    client = search_ingest._get_openai_client()
    
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    embedding = np.array([response.data[0].embedding], dtype=np.float32)
    
    return embedding

def search_similar(query_embedding: np.ndarray, top_n: int = 60) -> List[Tuple[int, float]]:
    """Search FAISS index for top N most similar chunks."""
    index = search_ingest.get_index()
    if index is None:
        return []
    
    distances, indices = index.search(query_embedding, top_n)
    
    # Return list of (chunk_idx, score)
    results = [(int(idx), float(dist)) for idx, dist in zip(indices[0], distances[0]) if idx != -1]
    return results

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

def mmr_diversify(query_embedding: np.ndarray, candidates: List[Tuple[int, float]], lambda_param: float = 0.6, k: int = 24) -> List[Tuple[int, float]]:
    """
    Apply MMR (Maximal Marginal Relevance) to reduce near-duplicates.
    
    Args:
        query_embedding: Query vector
        candidates: List of (chunk_idx, score) tuples
        lambda_param: Trade-off between relevance and diversity (0.6 recommended)
        k: Number of results to keep
    
    Returns:
        Diversified list of (chunk_idx, score) tuples
    """
    if len(candidates) <= k:
        return candidates
    
    chunks = search_ingest.get_chunks()
    index = search_ingest.get_index()
    
    # Get embeddings for all candidate chunks
    candidate_indices = [idx for idx, _ in candidates]
    candidate_scores = {idx: score for idx, score in candidates}
    
    selected = []
    remaining = set(candidate_indices)
    
    # Start with highest scoring chunk
    first_idx = candidates[0][0]
    selected.append((first_idx, candidate_scores[first_idx]))
    remaining.remove(first_idx)
    
    # Iteratively select chunks that maximize MMR score
    while len(selected) < k and remaining:
        best_score = -float('inf')
        best_idx = None
        
        for idx in remaining:
            # Relevance to query
            relevance = candidate_scores[idx]
            
            # Max similarity to already selected chunks
            max_sim = 0.0
            idx_embedding = index.reconstruct(int(idx))
            
            for sel_idx, _ in selected:
                sel_embedding = index.reconstruct(int(sel_idx))
                similarity = float(np.dot(idx_embedding, sel_embedding))
                max_sim = max(max_sim, similarity)
            
            # MMR score
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim
            
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx
        
        if best_idx is not None:
            selected.append((best_idx, candidate_scores[best_idx]))
            remaining.remove(best_idx)
        else:
            break
    
    return selected

def group_by_file(selected_chunks: List[Tuple[int, float]], max_snippets_per_file: int = 3) -> List[Dict[str, Any]]:
    """
    Group chunks by file and keep top 3 per file.
    Calculate doc_score = max(snippet_scores) + 0.02 * min(2, num_snippets)
    """
    chunks = search_ingest.get_chunks()
    
    # Group by file_id
    file_groups = defaultdict(list)
    for chunk_idx, score in selected_chunks:
        chunk = chunks[chunk_idx]
        file_groups[chunk["file_id"]].append((chunk_idx, score, chunk))
    
    # Process each file group
    groups = []
    for file_id, file_chunks in file_groups.items():
        # Sort by score and keep top N
        file_chunks.sort(key=lambda x: x[1], reverse=True)
        file_chunks = file_chunks[:max_snippets_per_file]
        
        # Calculate doc_score
        scores = [score for _, score, _ in file_chunks]
        max_score = max(scores)
        num_snippets = len(file_chunks)
        doc_score = max_score + 0.02 * min(2, num_snippets)
        
        # Get filename from first chunk
        filename = file_chunks[0][2]["filename"]
        
        groups.append({
            "file_id": file_id,
            "filename": filename,
            "doc_score": doc_score,
            "chunk_indices": [(idx, score) for idx, score, _ in file_chunks]
        })
    
    # Sort groups by doc_score
    groups.sort(key=lambda x: x["doc_score"], reverse=True)
    
    logger.info(f"Grouped {len(selected_chunks)} chunks into {len(groups)} file groups")
    return groups

def extract_snippet(chunk_text: str, query: str, chunk_position: int) -> Dict[str, Any]:
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
    1. Embed query
    2. Search FAISS (top 60)
    3. Apply keyword boost
    4. MMR diversification (keep 24)
    5. Group by file (top 3 per file)
    6. Return top K groups with snippets
    """
    logger.info(f"Searching for: {query}")
    
    # 1. Embed query
    query_embedding = embed_query(query)
    
    # 2. Search FAISS
    candidates = search_similar(query_embedding, top_n=60)
    if not candidates:
        logger.warning("No search results found")
        return []
    
    # 3. Apply keyword boost
    chunks = search_ingest.get_chunks()
    boosted_candidates = []
    for chunk_idx, score in candidates:
        chunk = chunks[chunk_idx]
        boosted_score = apply_keyword_boost(query, chunk["text"], score)
        boosted_candidates.append((chunk_idx, boosted_score))
    
    # Re-sort after boosting
    boosted_candidates.sort(key=lambda x: x[1], reverse=True)
    
    # 4. MMR diversification
    diversified = mmr_diversify(query_embedding, boosted_candidates, lambda_param=0.6, k=24)
    
    # 5. Group by file
    groups = group_by_file(diversified, max_snippets_per_file=max_snippets_per_group)
    
    # 6. Extract snippets and format results
    results = []
    for group in groups[:top_k_groups]:
        snippets = []
        for chunk_idx, score in group["chunk_indices"]:
            chunk = chunks[chunk_idx]
            snippet = extract_snippet(chunk["text"], query, chunk["position"])
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

