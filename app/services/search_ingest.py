"""
Document ingestion: chunking, embedding, and FAISS indexing.
Uses OpenAI embeddings (text-embedding-3-small).
"""
import os
import re
import logging
import pickle
from typing import List, Dict, Any, Optional
from pathlib import Path
import tiktoken
import faiss
import numpy as np
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# Global state
_index = None
_chunks = []
_openai_client = None

FAISS_INDEX_PATH = "./data/faiss_index.bin"
CHUNKS_PATH = "./data/chunks.pkl"

def _get_openai_client():
    """Get or create the OpenAI client (singleton)."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
        logger.info("✅ OpenAI embeddings client initialized (text-embedding-3-small)")
    return _openai_client

def chunk_text(text: str, file_id: str, filename: str, max_tokens: int = 600, overlap_tokens: int = 100) -> List[Dict[str, Any]]:
    """
    Split text into chunks of ~600 tokens with 100-token overlap.
    Try to split on natural boundaries (headings, paragraphs, bullets).
    """
    enc = tiktoken.get_encoding("cl100k_base")
    
    # Split on common document boundaries
    # Headings (lines starting with numbers or all caps)
    # Paragraphs (double newlines)
    # Bullets (lines starting with -, *, •, 1., etc.)
    
    # First, split into paragraphs
    paragraphs = re.split(r'\n\s*\n', text)
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    position = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        para_tokens = len(enc.encode(para))
        
        # If adding this paragraph would exceed max_tokens, save current chunk
        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append({
                "file_id": file_id,
                "filename": filename,
                "text": chunk_text,
                "position": position,
                "token_count": current_tokens
            })
            position += 1
            
            # Keep last paragraph for overlap (if small enough)
            if len(current_chunk) > 1 and len(enc.encode(current_chunk[-1])) < overlap_tokens:
                current_chunk = [current_chunk[-1]]
                current_tokens = len(enc.encode(current_chunk[-1]))
            else:
                current_chunk = []
                current_tokens = 0
        
        current_chunk.append(para)
        current_tokens += para_tokens
    
    # Add final chunk
    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        chunks.append({
            "file_id": file_id,
            "filename": filename,
            "text": chunk_text,
            "position": position,
            "token_count": current_tokens
        })
    
    logger.info(f"Created {len(chunks)} chunks from {filename}")
    return chunks

def embed_chunks(chunks: List[Dict[str, Any]]) -> np.ndarray:
    """Generate embeddings for chunks using OpenAI text-embedding-3-small."""
    client = _get_openai_client()
    texts = [chunk["text"] for chunk in chunks]
    
    logger.info(f"Generating embeddings for {len(texts)} chunks using OpenAI")
    
    # OpenAI embeddings API supports batch requests (up to 2048 texts)
    all_embeddings = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
    
    embeddings = np.array(all_embeddings, dtype=np.float32)
    logger.info(f"Generated embeddings: shape {embeddings.shape}")
    return embeddings

def build_index(chunks: List[Dict[str, Any]], embeddings: np.ndarray):
    """Build FAISS index from embeddings."""
    global _index, _chunks
    
    dimension = embeddings.shape[1]
    _index = faiss.IndexFlatIP(dimension)  # Inner product (cosine similarity after normalization)
    
    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)
    _index.add(embeddings)
    
    _chunks = chunks
    logger.info(f"Built FAISS index with {len(chunks)} chunks (dim={dimension})")

def save_index():
    """Persist index and chunks to disk."""
    os.makedirs("./data", exist_ok=True)
    
    # Save FAISS index
    faiss.write_index(_index, FAISS_INDEX_PATH)
    
    # Save chunks metadata
    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(_chunks, f)
    
    logger.info(f"Saved index and chunks to disk ({len(_chunks)} chunks)")

def load_index():
    """Load index and chunks from disk."""
    global _index, _chunks
    
    if not os.path.exists(FAISS_INDEX_PATH) or not os.path.exists(CHUNKS_PATH):
        logger.warning("Index files not found on disk")
        return False
    
    try:
        _index = faiss.read_index(FAISS_INDEX_PATH)
        
        with open(CHUNKS_PATH, "rb") as f:
            _chunks = pickle.load(f)
        
        logger.info(f"Loaded index and chunks from disk ({len(_chunks)} chunks)")
        return True
    except Exception as e:
        logger.error(f"Failed to load index: {e}")
        return False

def get_index():
    """Get the current FAISS index."""
    return _index

def get_chunks():
    """Get the current list of chunks."""
    return _chunks

def clear_index():
    """Clear the index and chunks (for rebuild)."""
    global _index, _chunks
    _index = None
    _chunks = []
    logger.info("Cleared index and chunks")


