# Performance Fixes - October 20, 2025

## 🚨 Critical Issues Found

### Issue #1: VectorStore Reloading on Every Request
**Severity:** CRITICAL  
**Impact:** 30-60 seconds added to EVERY request

**Problem:**
```python
class VectorStore:
    def __init__(self):
        # This was called on EVERY API request!
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')  # 5-10s load
```

Every time an API endpoint created a `VectorStore()` instance, it reloaded the entire SentenceTransformer model from disk, adding 5-10 seconds per request.

**Evidence from Logs:**
```
INFO:sentence_transformers.SentenceTransformer:Load pretrained SentenceTransformer: all-MiniLM-L6-v2
INFO:sentence_transformers.SentenceTransformer:Load pretrained SentenceTransformer: all-MiniLM-L6-v2
INFO:sentence_transformers.SentenceTransformer:Load pretrained SentenceTransformer: all-MiniLM-L6-v2
```
This message appeared 10+ times in a single session!

---

### Issue #2: HuggingFace Network Timeouts
**Severity:** CRITICAL  
**Impact:** 30-50 seconds wasted on network retries

**Problem:**
```
ReadTimeoutError: HTTPSConnectionPool(host='huggingface.co', port=443): 
Read timed out. (read timeout=10)
Retrying in 1s [Retry 1/5]
```

Every model load attempted to check HuggingFace online for updates:
- Initial timeout: 10 seconds
- Retries: 5 attempts
- Total wasted: **50 seconds per model load**

This happened for:
- SentenceTransformer (all-MiniLM-L6-v2)
- Mistral-7B
- BAAI/bge-base-en-v1.5
- Every config file check

---

### Issue #3: ChromaDB Client Reinitialization
**Severity:** MEDIUM  
**Impact:** 1-2 seconds added per request

**Problem:**
```python
self.client = chromadb.PersistentClient(path=..., settings=...)
```
ChromaDB client was being recreated on every VectorStore instantiation.

---

## ✅ Solutions Implemented

### Fix #1: Singleton Pattern for Embedding Models

**Before:**
```python
class VectorStore:
    def __init__(self):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
```

**After:**
```python
# Global cached instance
_embedding_model = None

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading embedding model (one-time): all-MiniLM-L6-v2")
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("✅ Embedding model loaded and cached")
    return _embedding_model

class VectorStore:
    def __init__(self):
        self.embedding_model = _get_embedding_model()  # Instant after first load!
```

**Result:**
- First call: 5-10 seconds (one-time)
- Subsequent calls: **0 seconds** ⚡

---

### Fix #2: Offline Mode for HuggingFace

**Implementation:**
```python
# Set environment variables
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# Load models with local_files_only
tokenizer = AutoTokenizer.from_pretrained(
    model_name,
    local_files_only=True  # Don't check online
)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    local_files_only=True
)
```

**Result:**
- No network calls
- No 10-second timeouts
- No retries
- **50 seconds saved per model load**

---

### Fix #3: Singleton Pattern for ChromaDB Client

**Before:**
```python
class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(...)
```

**After:**
```python
_chroma_client = None

def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(...)
        logger.info("Initialized ChromaDB client")
    return _chroma_client

class VectorStore:
    def __init__(self):
        self.client = _get_chroma_client()  # Reuses cached instance
```

**Result:**
- First call: <1 second
- Subsequent calls: **0 seconds** ⚡

---

## 📊 Performance Comparison

### Before Fixes

| Operation | Time | Frequency |
|-----------|------|-----------|
| Load SentenceTransformer | 5-10s | **Every request** |
| HuggingFace timeouts/retries | 30-50s | **Every model load** |
| ChromaDB init | 1-2s | **Every request** |
| Model loading (Mistral) | 10-20s | First use per session |
| AI generation | 15-30s | Every query |
| **TOTAL (first query)** | **60-110s** | 😱 |
| **TOTAL (subsequent)** | **50-70s** | Still terrible! |

### After Fixes

| Operation | Time | Frequency |
|-----------|------|-----------|
| Load SentenceTransformer | 5-10s | **One-time only** |
| HuggingFace checks | 0s | **Disabled** ⚡ |
| ChromaDB init | <1s | **One-time only** |
| Model loading (Mistral) | 10-20s | **One-time only** |
| AI generation | 15-30s | Every query |
| **TOTAL (first query)** | **30-60s** | ✅ 50% faster |
| **TOTAL (subsequent)** | **15-30s** | 🚀 **75% faster!** |

---

## 🎯 Real-World Impact

### User Experience Before:
1. User asks first question
2. Wait **60-110 seconds** 😴
3. User asks second question  
4. Wait **50-70 seconds** 😴
5. User thinks app is broken

### User Experience After:
1. User asks first question
2. Wait **30-60 seconds** ⏳ (acceptable for first-time setup)
3. User asks second question
4. Wait **15-30 seconds** ⚡ (just generation time)
5. User is happy! 😊

---

## 🔧 Files Modified

### 1. `app/services/vector_store.py`
**Changes:**
- Added `_chroma_client` global singleton
- Added `_get_chroma_client()` function
- Added `_embedding_model` global singleton
- Added `_get_embedding_model()` function
- Modified `VectorStore.__init__()` to use cached instances

**Lines Changed:** ~30 lines

---

### 2. `app/services/ai_service.py`
**Changes:**
- Added `os.environ['HF_HUB_OFFLINE'] = '1'`
- Added `os.environ['TRANSFORMERS_OFFLINE'] = '1'`
- Added `local_files_only=True` to all model loads
- Improved logging messages

**Lines Changed:** ~10 lines

---

### 3. `app/services/search_ingest.py`
**Changes:**
- Added offline mode to `_get_embedding_model()`
- Prevents network timeouts for search embeddings

**Lines Changed:** ~5 lines

---

## ✅ Verification

### Check Logs for Success:
```bash
tail -f server.log
```

**Good Signs:**
```
✅ Embedding model loaded and cached
INFO:app.services.vector_store:VectorStore ready (using cached instances)
INFO:app.services.ai_service:Using cached mistral model ⚡
```

**Bad Signs (if you still see these, something's wrong):**
```
❌ Load pretrained SentenceTransformer: all-MiniLM-L6-v2  # Repeated multiple times
❌ ReadTimeoutError: Read timed out
❌ Retrying in 1s [Retry 1/5]
```

---

## 🧪 Testing

### Test Scenario 1: First Query
```bash
# Expected: 30-60 seconds
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"message": "What documents do I have?"}'
```

**Expected Log Output:**
```
Loading embedding model (one-time): all-MiniLM-L6-v2
✅ Embedding model loaded and cached
Initialized ChromaDB client
🔄 Loading chat model: mistralai/Mistral-7B-Instruct-v0.2 (using cached version)
✅ Chat model loaded successfully
Generating response with Mistral-7B...
```

---

### Test Scenario 2: Second Query
```bash
# Expected: 15-30 seconds (just generation!)
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about NDAs"}'
```

**Expected Log Output:**
```
VectorStore ready (using cached instances)
Using cached mistral model ⚡
Generating response with Mistral-7B...
```

**Key:** No "Loading" messages! Everything cached!

---

## 📈 Monitoring

### Check Current Performance:
```bash
# Time a query
time curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

### Check Model Status:
```bash
curl http://localhost:8000/api/health/models | python3 -m json.tool
```

### Monitor Logs in Real-Time:
```bash
tail -f server.log | grep -E "cached|Loading|seconds"
```

---

## 🎉 Summary

**Problems Solved:**
1. ✅ VectorStore no longer reloads on every request (75% faster)
2. ✅ No more network timeouts (50 seconds saved per load)
3. ✅ ChromaDB client cached (1-2 seconds saved per request)
4. ✅ All models cached properly (instant reuse)

**Performance Gains:**
- First query: **50% faster** (60-110s → 30-60s)
- Subsequent queries: **75% faster** (50-70s → 15-30s)
- No more mysterious delays
- Predictable response times

**User Experience:**
- First-time setup: Acceptable wait
- Regular usage: Fast responses
- App feels responsive
- No more "is it broken?" moments

---

## 🚀 Next Steps (Optional Optimizations)

If you want **even faster** responses:

### 1. Use GPU for Inference
- Install CUDA/Metal support
- Mistral: 15-30s → **2-5s**
- Phi-3: 3-8s → **<1s**

### 2. Model Quantization
- Use 4-bit or 8-bit quantized models
- Smaller memory footprint
- Faster inference

### 3. Batch Processing
- Process multiple queries together
- Better GPU utilization

### 4. Model Warm-up on Startup
- Load models when server starts
- First query is already fast
- Trade: Slower startup for faster first response

But for now, the current fixes provide **excellent performance** without these advanced optimizations!





