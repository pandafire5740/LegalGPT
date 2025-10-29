"""
Document ingestion utilities: chunking and embedding.
Uses OpenAI embeddings (text-embedding-3-small).
"""
import os
import re
import logging
from typing import List, Dict, Any
from pathlib import Path
import tiktoken
import numpy as np
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_openai_client = None


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
