# Advanced Search System

## Overview

This legal knowledge platform uses **100% open-source models** with no external API dependencies:

- **Embeddings**: `BAAI/bge-base-en-v1.5` (768-dimensional, normalized for cosine similarity)
- **Summaries**: `mistralai/Mistral-7B-Instruct-v0.2` (default) or `microsoft/Phi-3-mini-4k-instruct` (lightweight)

## First Run: Model Downloads

On first use, models are automatically downloaded from HuggingFace:

- **bge-base-en-v1.5**: ~440MB
- **Mistral-7B-Instruct-v0.2**: ~7GB (recommended for best quality)
- **Phi-3-mini-4k-instruct**: ~2GB (lightweight alternative)

**Note**: Downloads happen once and are cached locally.

## GPU vs CPU

The system **automatically detects** and uses GPU if available (CUDA), otherwise runs on CPU:

- **GPU**: Fast inference (seconds)
- **CPU**: Slower but fully functional (10-30 seconds for summaries)

For CPU-only machines, use the lightweight Phi-3 model:

```bash
export LEGALGPT_SUMMARY_MODEL="microsoft/Phi-3-mini-4k-instruct"
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the Application

```bash
python3 start.py
```

The server starts at: **http://localhost:8000**

### 3. Build the Search Index

Upload documents via UI, or rebuild manually:

```bash
curl -X POST http://localhost:8000/api/search/rebuild
```

**First-time indexing**: Allow 30-60 seconds for model downloads.

### 4. Search

Via UI:
- Open http://localhost:8000
- Click "Search" tab
- Enter query (e.g., "auto-renewal", "NDA", "termination")

Via API:
```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"confidential information","top_k_groups":6,"max_snippets_per_group":3}'
```

## Configuration

### Environment Variables

Create a `.env` file (see `.env.example`):

```bash
# Summary Model (optional)
LEGALGPT_SUMMARY_MODEL=mistralai/Mistral-7B-Instruct-v0.2

# Options:
# - mistralai/Mistral-7B-Instruct-v0.2 (default, best quality)
# - microsoft/Phi-3-mini-4k-instruct (lightweight, faster on CPU)
```

### Model Selection Guide

| Model | Size | Quality | CPU Speed | GPU Speed | Recommended For |
|-------|------|---------|-----------|-----------|-----------------|
| Mistral-7B-Instruct-v0.2 | 7GB | Best | Slow (20-30s) | Fast (2-5s) | GPU or patience |
| Phi-3-mini-4k-instruct | 2GB | Good | Medium (10-15s) | Fast (1-3s) | CPU machines |

## API Endpoints

### POST /api/search

**Request:**
```json
{
  "query": "auto-renewal 12 months",
  "top_k_groups": 6,
  "max_snippets_per_group": 3
}
```

**Response:**
```json
{
  "summary": "Found 3 documents with auto-renewal clauses extending beyond 12 months...",
  "groups": [
    {
      "file_id": "abc123",
      "filename": "VendorX_MSA.pdf",
      "doc_score": 0.87,
      "snippets": [
        {
          "text": "The agreement **auto-renews** for **12 months** unless...",
          "page_range": "pp. 3-4",
          "position": 5,
          "score": 0.85
        }
      ]
    }
  ],
  "total_groups": 3
}
```

### POST /api/search/rebuild

Rebuilds the FAISS index from all uploaded documents.

**Response:**
```json
{
  "status": "success",
  "indexed_files": 15,
  "total_chunks": 342,
  "message": "Search index rebuilt successfully"
}
```

## How It Works

### 1. Document Ingestion
- Extract text from PDFs (pypdf) and DOCX (python-docx)
- Split into 600-token chunks with 100-token overlap
- Generate embeddings using bge-base-en-v1.5
- Build FAISS index (inner product for normalized vectors = cosine)

### 2. Query Processing
- Embed query with same model
- Retrieve top 60 chunks via FAISS
- Apply MMR diversification (λ=0.6) → 24 final chunks
- Group by file, rank by `doc_score`, extract snippets

### 3. Summarization
- Feed top 3 file groups to Mistral/Phi-3
- Generate 2-3 sentence summary (≤50 words)
- No fact invention, only restates snippets

## Troubleshooting

### "Out of Memory" on CPU

Use the lightweight model:
```bash
export LEGALGPT_SUMMARY_MODEL="microsoft/Phi-3-mini-4k-instruct"
```

### Summaries Taking Too Long

- **GPU**: Should be 2-5 seconds
- **CPU**: 10-30 seconds is normal
- Switch to Phi-3 for faster CPU inference

### Model Download Fails

Check internet connection and HuggingFace availability:
```bash
curl -I https://huggingface.co
```

### Search Returns No Results

1. Check if index is built: `curl http://localhost:8000/api/health`
2. Rebuild: `curl -X POST http://localhost:8000/api/search/rebuild`
3. Verify documents uploaded in UI

## Performance

### Typical Latency (P50)

| Operation | CPU | GPU |
|-----------|-----|-----|
| Query embedding | 50-100ms | 20-50ms |
| FAISS search | 10-20ms | 10-20ms |
| MMR + grouping | 20-50ms | 20-50ms |
| Summary generation | 10-30s | 2-5s |
| **Total** | **11-31s** | **2-6s** |

With 10-50 documents indexed.

## No External APIs

✅ **No OpenAI** - runs 100% locally  
✅ **No cloud dependencies** - all models cached locally  
✅ **No API keys required** - completely self-contained  
✅ **No usage costs** - free and open-source  

## Next Steps

- Upload documents via UI
- Run a test search
- Adjust model based on hardware (Mistral for GPU, Phi-3 for CPU)
- Monitor `logs/` for performance metrics





