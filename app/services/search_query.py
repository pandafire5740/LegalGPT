"""
Clause-level hybrid search: ChromaDB vector search + keyword matching.
Uses OpenAI embeddings (text-embedding-3-small) for semantic search.

This module implements a lawyer-friendly, clause-centric search that:
- Treats each chunk as a "clause" with metadata (file_name, file_path, section_title, etc.)
- Combines semantic similarity (vector) with keyword overlap/density scoring
- Groups results by file and computes doc_scores
- Extracts clause snippets with query term highlighting
- Optionally generates LLM summaries per clause (cached)
"""
import re
import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from app.services.vector_store import VectorStore
from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration Constants
# ============================================================================

# Multiplier for initial vector search results (to account for grouping/filtering)
RESULTS_MULTIPLIER = 3  # Get 3x more results than needed for diversity

# Hybrid scoring weights
KEYWORD_OVERLAP_WEIGHT = 0.02  # Per query word found in clause (capped at 5)
KEYWORD_DENSITY_WEIGHT = 0.03  # Density bonus: overlap / clause_length

# Doc score calculation
DIVERSITY_BONUS_PER_SNIPPET = 0.02  # Bonus per snippet (capped at 2 snippets)
MAX_DIVERSITY_SNIPPETS = 2  # Maximum snippets that contribute to diversity bonus

# Clause summary settings
MAX_CLAUSE_SUMMARIES_PER_FILE = 2  # Maximum clauses to summarize per file (top 1-2 to save tokens)
CLAUSE_SUMMARY_MAX_WORDS = 40  # Maximum words per clause summary

# Clause text truncation
MAX_CLAUSE_TEXT_LENGTH = 700  # Maximum characters for clause text sent to UI

# Search relevance thresholds (tuned for lawyer-friendly precision)
SEARCH_DOC_THRESHOLD = 0.5      # doc_score cutoff - files below this are filtered out
SEARCH_CLAUSE_THRESHOLD = 0.45  # per-clause hybrid_score cutoff - clauses below this are filtered out
MAX_FILES_RETURNED = 5          # Maximum number of files to return
MAX_CLAUSES_PER_FILE = 3        # Maximum clauses per file


# ============================================================================
# Contract Type Detection
# ============================================================================

def normalize_query(q: str) -> str:
    """Normalize query for matching."""
    return q.lower().strip()

CONTRACT_TYPE_PHRASES = {
    "master services agreement": {
        "aliases": ["master services agreement", "msa", "master service agreement"]
    },
    "non-disclosure agreement": {
        "aliases": ["non-disclosure agreement", "nda", "non disclosure agreement", "confidentiality agreement"]
    },
    "data processing addendum": {
        "aliases": ["data processing addendum", "dpa", "data processing agreement"]
    },
    "statement of work": {
        "aliases": ["statement of work", "sow"]
    },
    "service level agreement": {
        "aliases": ["service level agreement", "sla"]
    },
    "independent contractor agreement": {
        "aliases": ["independent contractor agreement", "ica", "independent contractor"]
    },
    "partnership agreement": {
        "aliases": ["partnership agreement", "partnership"]
    },
}

def detect_contract_type(query: str) -> Optional[str]:
    """
    Detect if query is asking for a specific contract type.
    
    Returns the contract type label if detected, None otherwise.
    """
    q = normalize_query(query)
    for label, cfg in CONTRACT_TYPE_PHRASES.items():
        for alias in cfg["aliases"]:
            if alias in q:
                return label
    return None

def is_phrase_hit(text: str, contract_type: str) -> bool:
    """
    Check if text contains any alias for the given contract type.
    
    Args:
        text: Text to check (file_name or clause_text)
        contract_type: Contract type label from CONTRACT_TYPE_PHRASES
        
    Returns:
        True if any alias is found in text (case-insensitive)
    """
    if not contract_type or contract_type not in CONTRACT_TYPE_PHRASES:
        return False
    
    text_lower = text.lower()
    cfg = CONTRACT_TYPE_PHRASES[contract_type]
    for alias in cfg["aliases"]:
        if alias in text_lower:
            return True
    return False

# ============================================================================
# Helper Functions
# ============================================================================

def tokenize_query(query: str) -> List[str]:
    """
    Tokenize query into words (lowercased, split on whitespace/punctuation).
    
    Args:
        query: Search query string
        
    Returns:
        List of lowercased word tokens (filtered to meaningful words > 2 chars)
    """
    # Split on whitespace and punctuation, lowercase, filter short words
    tokens = re.findall(r'\b\w+\b', query.lower())
    return [t for t in tokens if len(t) > 2]


def compute_keyword_features(query_tokens: List[str], clause_text: str) -> Tuple[int, float]:
    """
    Compute keyword overlap and density for a clause.
    
    Args:
        query_tokens: List of lowercased query word tokens
        clause_text: Full clause/chunk text
        
    Returns:
        Tuple of (keyword_overlap, keyword_density)
        - keyword_overlap: Number of query tokens found in clause (capped at 5)
        - keyword_density: keyword_overlap / (clause_word_count + 1)
    """
    clause_lower = clause_text.lower()
    clause_words = set(re.findall(r'\b\w+\b', clause_lower))
    
    # Count how many query tokens appear in clause
    overlap = sum(1 for token in query_tokens if token in clause_words)
    overlap = min(overlap, 5)  # Cap at 5 for scoring
    
    # Compute density
    clause_word_count = len(clause_words)
    density = overlap / (clause_word_count + 1) if clause_word_count > 0 else 0.0
    
    return overlap, density


def compute_hybrid_score(
    base_similarity_score: float,
    keyword_overlap: int,
    keyword_density: float
) -> Tuple[float, str]:
    """
    Compute hybrid score combining semantic similarity with keyword matching.
    
    Args:
        base_similarity_score: Vector similarity score (0.0-1.0)
        keyword_overlap: Number of query tokens found (0-5)
        keyword_density: Overlap / clause_length (0.0-1.0)
        
    Returns:
        Tuple of (hybrid_score, match_type)
        - hybrid_score: Combined score
        - match_type: "semantic+keyword" or "semantic"
    """
    hybrid_score = (
        base_similarity_score
        + KEYWORD_OVERLAP_WEIGHT * keyword_overlap
        + KEYWORD_DENSITY_WEIGHT * keyword_density
    )
    
    # Clamp to [0.0, 1.0] range
    hybrid_score = max(0.0, min(1.0, hybrid_score))
    
    match_type = "semantic+keyword" if keyword_overlap > 0 else "semantic"
    
    return hybrid_score, match_type


def compute_doc_score(snippet_scores: List[float], num_snippets: int) -> float:
    """
    Compute document-level score from snippet scores.
    
    Formula: max(snippet_scores) + diversity_bonus
    
    Args:
        snippet_scores: List of hybrid scores for snippets in this file
        num_snippets: Number of snippets (for diversity bonus)
        
    Returns:
        Document score (0.0-1.0)
    """
    if not snippet_scores:
        return 0.0
    
    base = max(snippet_scores)
    diversity_bonus = DIVERSITY_BONUS_PER_SNIPPET * min(MAX_DIVERSITY_SNIPPETS, num_snippets)
    
    return min(1.0, base + diversity_bonus)


def truncate_clause_text(clause_text: str, max_chars: int = MAX_CLAUSE_TEXT_LENGTH) -> str:
    """
    Truncate clause text to a maximum length, preserving sentence boundaries when possible.
    
    Args:
        clause_text: Full clause text
        max_chars: Maximum characters (default: MAX_CLAUSE_TEXT_LENGTH)
        
    Returns:
        Truncated text (with ellipsis if truncated)
    """
    if not clause_text or len(clause_text) <= max_chars:
        return clause_text
    
    # Try to truncate at a sentence boundary
    truncated = clause_text[:max_chars]
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')
    
    # Prefer sentence boundary, but don't go too far back
    cutoff = max(last_period, last_newline)
    if cutoff > max_chars * 0.7:  # Only use boundary if it's not too far back
        truncated = truncated[:cutoff + 1]
    
    return truncated + "..."

def detect_clause_type(clause_text: str, section_title: Optional[str] = None) -> str:
    """
    Detect the primary clause type from clause text and optional section title.
    
    Returns one of:
    - "Intro / Recitals"
    - "Term & Renewal"
    - "Termination"
    - "Payment"
    - "Confidentiality"
    - "Liability"
    - "Governing Law"
    - "Other"
    
    Args:
        clause_text: The clause text content
        section_title: Optional section title/heading
        
    Returns:
        Clause type label
    """
    # Combine text and title for analysis
    combined_text = (section_title or "").lower() + " " + clause_text.lower()
    
    # Define keywords for each clause type
    clause_keywords = {
        "Intro / Recitals": [
            "recitals", "whereas", "background", "preamble", "introduction",
            "parties agree", "this agreement", "entered into"
        ],
        "Term & Renewal": [
            "term", "duration", "initial term", "renewal", "automatic renewal",
            "commencement", "effective date", "expiration", "expiry"
        ],
        "Termination": [
            "termination", "terminate", "expiration", "end of term",
            "breach", "default", "cure period", "notice of termination"
        ],
        "Payment": [
            "payment", "fee", "pricing", "invoice", "billing", "compensation",
            "reimbursement", "cost", "charge", "amount", "dollar"
        ],
        "Confidentiality": [
            "confidential", "non-disclosure", "nda", "proprietary",
            "trade secret", "disclosure", "protected information"
        ],
        "Liability": [
            "liability", "indemnification", "indemnify", "damages",
            "limitation of liability", "consequential damages", "warranty",
            "disclaimer", "hold harmless"
        ],
        "Governing Law": [
            "governing law", "jurisdiction", "venue", "dispute resolution",
            "arbitration", "litigation", "courts", "legal proceedings"
        ]
    }
    
    # Score each clause type
    scores = {}
    for clause_type, keywords in clause_keywords.items():
        score = sum(1 for keyword in keywords if keyword in combined_text)
        if score > 0:
            scores[clause_type] = score
    
    # Return the highest scoring type, or "Other" if no match
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    
    return "Other"

def build_clause_snippet(full_clause_text: str, query: str) -> str:
    """
    Build a markdown snippet from clause text, highlighting query terms.
    
    Extracts 2-3 sentences around the densest query overlap and bolds exact query terms.
    
    Args:
        full_clause_text: Complete clause/chunk text
        query: Search query string
        
    Returns:
        Markdown-formatted snippet with **bolded** query terms
    """
    # Tokenize query for matching
    query_tokens = tokenize_query(query)
    
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', full_clause_text)
    
    if not sentences:
        return full_clause_text
    
    # Find sentence(s) with most query token matches
    best_sent_idx = 0
    best_match_count = 0
    
    for i, sent in enumerate(sentences):
        sent_lower = sent.lower()
        match_count = sum(1 for token in query_tokens if token in sent_lower)
        if match_count > best_match_count:
            best_match_count = match_count
            best_sent_idx = i
    
    # Extract 2-3 sentences around best match
    start_idx = max(0, best_sent_idx - 1)
    end_idx = min(len(sentences), best_sent_idx + 2)
    snippet_sentences = sentences[start_idx:end_idx]
    snippet_text = " ".join(snippet_sentences).strip()
    
    # Bold exact query token matches (case-insensitive, word boundaries)
    for token in query_tokens:
        if len(token) > 2:  # Only bold meaningful words
            pattern = re.compile(fr'(\b{re.escape(token)}\b)', re.IGNORECASE)
            snippet_text = pattern.sub(r'**\1**', snippet_text)
    
    # Ensure we return a non-empty string (required by Pydantic model)
    return snippet_text if snippet_text else full_clause_text[:200]


# ============================================================================
# Main Search Functions
# ============================================================================

def search_and_group(
    vector_store: VectorStore,
    query: str,
    top_k_groups: int = 6,
    max_snippets_per_group: int = 3,
    enable_clause_summaries: bool = False
) -> List[Dict[str, Any]]:
    """
    Main clause-level hybrid search flow (tuned for lawyer-friendly precision).
    
    1. Search ChromaDB using vector similarity
    2. Apply hybrid scoring (semantic + keyword)
    3. Detect contract type from query (if applicable)
    4. Group clauses by file_name
    5. Filter by thresholds (doc_score >= 0.5, clause_score >= 0.45)
    6. Apply phrase-hit filtering for contract-type queries
    7. Extract clause snippets
    8. Optionally generate LLM summaries per clause
    
    Args:
        vector_store: VectorStore instance for search
        query: Search query string
        top_k_groups: Number of file groups to return (overridden by MAX_FILES_RETURNED)
        max_snippets_per_group: Maximum clauses per file group (overridden by MAX_CLAUSES_PER_FILE)
        enable_clause_summaries: Whether to generate LLM summaries (costly)
        
    Returns:
        List of file groups, each containing:
        - file_name, file_path, doc_score, keyword_summary
        - clauses: List of ClauseHit dicts with clause_text, similarity_score, match_type, etc.
    """
    logger.info(f"=== CLAUSE-LEVEL SEARCH START: query='{query}', top_k_groups={top_k_groups}, max_snippets_per_group={max_snippets_per_group}")
    
    # Detect contract type from query
    contract_type = detect_contract_type(query)
    if contract_type:
        logger.info(f"Detected contract type: {contract_type}")
    
    # Tokenize query once for reuse
    query_tokens = tokenize_query(query)
    logger.debug(f"Query tokens: {query_tokens}")
    
    # 1. Vector search: Get enough results for grouping
    n_results = MAX_FILES_RETURNED * MAX_CLAUSES_PER_FILE * RESULTS_MULTIPLIER
    logger.debug(f"Requesting {n_results} results from vector store")
    
    search_results = vector_store.search_similar(query, n_results=n_results)
    
    if not search_results:
        logger.warning(f"No search results found for query: '{query}'")
        return []
    
    logger.info(f"Vector store returned {len(search_results)} clause results")
    if search_results:
        scores = [r.get("similarity_score", 0.0) for r in search_results]
        logger.info(f"Base similarity range: min={min(scores):.3f}, max={max(scores):.3f}, avg={sum(scores)/len(scores):.3f}")
    
    # 2. Apply hybrid scoring and mark phrase hits
    hybrid_results = []
    semantic_only_count = 0
    keyword_boosted_count = 0
    
    for result in search_results:
        content = result.get("content", "")
        base_score = result.get("similarity_score", 0.0)
        metadata = result.get("metadata", {})
        file_name = metadata.get("file_name", "Unknown")
        
        # Compute keyword features
        keyword_overlap, keyword_density = compute_keyword_features(query_tokens, content)
        
        # Compute hybrid score
        hybrid_score, match_type = compute_hybrid_score(base_score, keyword_overlap, keyword_density)
        
        # Mark phrase hits if contract type detected
        is_phrase_match = False
        if contract_type:
            is_phrase_match = is_phrase_hit(file_name, contract_type) or is_phrase_hit(content, contract_type)
        
        if match_type == "semantic+keyword":
            keyword_boosted_count += 1
        
        # Update result with hybrid score, match type, and phrase hit flag
        result["similarity_score"] = hybrid_score
        result["match_type"] = match_type
        result["keyword_overlap"] = keyword_overlap
        result["keyword_density"] = keyword_density
        result["is_phrase_hit"] = is_phrase_match
        
        hybrid_results.append(result)
    
    logger.info(f"Hybrid scoring: {keyword_boosted_count} clauses got keyword boost, {semantic_only_count} semantic-only")
    if contract_type:
        phrase_hits = sum(1 for r in hybrid_results if r.get("is_phrase_hit", False))
        logger.info(f"Phrase hits for '{contract_type}': {phrase_hits}/{len(hybrid_results)}")
    
    # Re-sort by hybrid score
    hybrid_results.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)
    
    # 3. Group clauses by file_name
    file_groups = defaultdict(list)
    for clause_result in hybrid_results:
        metadata = clause_result.get("metadata", {})
        file_name = metadata.get("file_name", "Unknown")
        file_id = clause_result.get("id", "")
        score = clause_result.get("similarity_score", 0.0)
        
        file_groups[file_name].append({
            "clause": clause_result,
            "score": score,
            "file_id": file_id,
            "is_phrase_hit": clause_result.get("is_phrase_hit", False)
        })
    
    logger.debug(f"Grouped clauses into {len(file_groups)} unique files")
    
    # 4. Process each file group: compute doc_score, filter clauses by threshold, keep top N
    groups = []
    for file_name, file_clauses in file_groups.items():
        # Filter clauses by SEARCH_CLAUSE_THRESHOLD
        file_clauses = [fc for fc in file_clauses if fc["score"] >= SEARCH_CLAUSE_THRESHOLD]
        
        if not file_clauses:
            logger.debug(f"File '{file_name}': All clauses filtered out by clause threshold {SEARCH_CLAUSE_THRESHOLD}")
            continue
        
        # Sort by score and keep top N (limited by MAX_CLAUSES_PER_FILE)
        file_clauses.sort(key=lambda x: x["score"], reverse=True)
        original_count = len(file_clauses)
        file_clauses = file_clauses[:MAX_CLAUSES_PER_FILE]
        
        # Compute doc_score
        snippet_scores = [fc["score"] for fc in file_clauses]
        doc_score = compute_doc_score(snippet_scores, len(file_clauses))
        
        # Check if file has any phrase hits
        has_phrase_hit = any(fc.get("is_phrase_hit", False) for fc in file_clauses)
        
        # Get file_id and file_path from metadata
        file_id = file_clauses[0]["clause"].get("metadata", {}).get("file_id", file_name) if file_clauses else file_name
        
        groups.append({
            "file_id": file_id,
            "filename": file_name,
            "doc_score": doc_score,
            "clauses": file_clauses,
            "has_phrase_hit": has_phrase_hit
        })
        
        logger.debug(f"File '{file_name}': {original_count} clauses -> {len(file_clauses)} kept, doc_score={doc_score:.3f}, phrase_hit={has_phrase_hit}")
    
    # Sort groups by doc_score
    groups.sort(key=lambda x: x["doc_score"], reverse=True)
    logger.info(f"Created {len(groups)} file groups before threshold filtering")
    
    # 5. Apply contract-type filtering if applicable
    if contract_type:
        # Separate files with phrase hits from those without
        phrase_hit_files = [g for g in groups if g.get("has_phrase_hit", False)]
        non_phrase_files = [g for g in groups if not g.get("has_phrase_hit", False)]
        
        # For non-phrase-hit files, require higher doc_score (>= 0.75)
        filtered_non_phrase = [g for g in non_phrase_files if g["doc_score"] >= 0.75]
        
        # Combine: phrase-hit files first, then high-scoring non-phrase files
        filtered_groups = phrase_hit_files + filtered_non_phrase
        
        logger.info(f"Contract-type filtering for '{contract_type}': {len(phrase_hit_files)} phrase-hit files, {len(filtered_non_phrase)} high-scoring non-phrase files")
    else:
        filtered_groups = groups
    
    # 6. Filter by SEARCH_DOC_THRESHOLD
    filtered_groups = [g for g in filtered_groups if g["doc_score"] >= SEARCH_DOC_THRESHOLD]
    
    if not filtered_groups:
        logger.warning(f"No groups met doc threshold of {SEARCH_DOC_THRESHOLD:.2f} ({SEARCH_DOC_THRESHOLD*100:.0f}%)")
        if groups:
            logger.warning(f"Top group score was {groups[0]['doc_score']:.3f} ({groups[0]['doc_score']*100:.1f}%) from file '{groups[0]['filename']}'")
        return []
    
    logger.info(f"Filtered to {len(filtered_groups)} groups above doc threshold {SEARCH_DOC_THRESHOLD:.2f}")
    
    # 7. Limit to MAX_FILES_RETURNED
    filtered_groups = filtered_groups[:MAX_FILES_RETURNED]
    logger.info(f"Limited to top {len(filtered_groups)} files (MAX_FILES_RETURNED={MAX_FILES_RETURNED})")
    
    # 8. Build clause hits with snippets and optional summaries
    results = []
    clause_summary_cache = {}  # Cache for clause summaries: hash -> summary
    
    for group in filtered_groups:
        filename = group["filename"]
        logger.debug(f"Processing clauses for file: {filename}")
        
        clause_hits = []
        max_summaries = MAX_CLAUSE_SUMMARIES_PER_FILE if enable_clause_summaries else 0
        
        for clause_idx, clause_data in enumerate(group["clauses"]):
            clause_result = clause_data["clause"]
            content = clause_result.get("content", "")
            metadata = clause_result.get("metadata", {})
            score = clause_data["score"]
            match_type = clause_result.get("match_type", "semantic")
            
            # Extract metadata
            file_path = metadata.get("file_path")
            section_title = metadata.get("section_title") or metadata.get("clause_heading")
            chunk_index = metadata.get("chunk_index")
            
            # Detect clause type
            clause_type = detect_clause_type(content, section_title)
            
            # Build clause snippet (ensure it's never empty - required by Pydantic model)
            clause_snippet = build_clause_snippet(content, query) or content[:200] or "No snippet available"  # Multiple fallbacks
            
            # Truncate clause text before sending to UI
            truncated_content = truncate_clause_text(content)
            
            # Optional: Generate clause summary (cached) - only for top N clauses
            clause_summary = None
            if enable_clause_summaries and clause_idx < max_summaries:
                # Create cache key from stable identifiers
                cache_key_parts = [filename, section_title or "", content[:200]]  # Use first 200 chars
                cache_key = hashlib.md5("|".join(cache_key_parts).encode()).hexdigest()
                
                if cache_key in clause_summary_cache:
                    clause_summary = clause_summary_cache[cache_key]
                    logger.debug(f"Using cached clause summary for clause {clause_idx+1}")
                else:
                    # Generate summary via LLM (lazy import to avoid circular dependency)
                    try:
                        from app.services.llm_engine import LLMEngine
                        clause_summary = LLMEngine.summarize_clause(
                            clause_text=content,
                            max_words=CLAUSE_SUMMARY_MAX_WORDS
                        )
                        clause_summary_cache[cache_key] = clause_summary
                        logger.debug(f"Generated clause summary for clause {clause_idx+1}: {clause_summary[:50]}...")
                    except Exception as e:
                        logger.warning(f"Failed to generate clause summary: {e}")
                        clause_summary = None
            
            clause_hit = {
                "file_name": filename,
                "file_path": file_path,
                "section_title": section_title,
                "clause_text": truncated_content,  # Truncated for UI
                "clause_snippet": clause_snippet,
                "similarity_score": score,
                "match_type": match_type,
                "chunk_index": chunk_index,
                "clause_summary": clause_summary,
                "display_clause_score": score,  # For UI display (can be made optional)
                "clause_type": clause_type,  # Primary clause type for clustering
                "_original_content": content  # Store original content for summary generation (not sent to UI)
            }
            
            clause_hits.append(clause_hit)
            
            logger.debug(f"  Clause {clause_idx+1}: type={clause_type}, score={score:.3f}, match_type={match_type}, snippet_length={len(clause_snippet)}")
        
        # Get file_path from first clause if available
        file_path = clause_hits[0].get("file_path") if clause_hits else None
        
        # Group clauses by type and sort within each group by score
        clause_type_order = [
            "Intro / Recitals",
            "Term & Renewal",
            "Termination",
            "Payment",
            "Confidentiality",
            "Liability",
            "Governing Law",
            "Other"
        ]
        
        # Group clauses by type
        clauses_by_type = {}
        for clause in clause_hits:
            clause_type = clause.get("clause_type", "Other")
            if clause_type not in clauses_by_type:
                clauses_by_type[clause_type] = []
            clauses_by_type[clause_type].append(clause)
        
        # Sort clauses within each type by score (descending)
        for clause_type in clauses_by_type:
            clauses_by_type[clause_type].sort(key=lambda c: c.get("similarity_score", 0.0), reverse=True)
        
        # Rebuild clause_hits in type order, with clauses sorted within each type
        sorted_clause_hits = []
        for clause_type in clause_type_order:
            if clause_type in clauses_by_type:
                sorted_clause_hits.extend(clauses_by_type[clause_type])
        
        results.append({
            "file_id": group["file_id"],
            "filename": filename,
            "file_path": file_path,
            "doc_score": group["doc_score"],
            "clauses": sorted_clause_hits,  # Sorted by type, then by score within type
            "clauses_by_type": clauses_by_type  # Also include grouped structure for UI
        })
    
    logger.info(f"=== SEARCH COMPLETE: Returning {len(results)} file groups with {sum(len(r['clauses']) for r in results)} total clauses")
    return results
