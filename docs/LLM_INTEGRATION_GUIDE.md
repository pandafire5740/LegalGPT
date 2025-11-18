# LLM Integration Guide

## Current LLM Implementation

The application now uses **OpenAI GPT-4o** for all LLM functionality. The implementation is located in `app/services/llm_engine.py`.

### Key Components

- **`LLMEngine.chat()`** - Conversational Q&A with document context
- **`Streaming.chat_stream()`** - Streaming token-by-token responses
- **`LLMEngine.summarize()`** - Document summarization
- **`LLMEngine.extract_terms()`** - Contract term extraction

All functions use OpenAI GPT-4o with response caching and output sanitization.

## Historical Note: What Was Removed

Previously, the application had a placeholder `app/services/ai_service.py` file that has since been removed. Here's what was originally removed from that file:

### Removed Components

1. **`_get_chat_pipeline()` function** (~118 lines)
   - Model loading logic for Phi-3-mini
   - Tokenizer initialization
   - Pipeline creation with transformers library
   - Model caching and status tracking
   - All HuggingFace transformers integration

2. **Global State Variables**
   - `_chat_pipelines = {}`
   - `_loading_status = {}`

3. **Dependencies on:**
   - `transformers` library (AutoModelForCausalLM, AutoTokenizer, pipeline)
   - `torch` (PyTorch)
   - Model weights (~2GB Phi-3-mini model)

4. **LLM Generation Logic**
   - Prompt building
   - Model inference calls
   - Token generation
   - Response parsing

## What Was Kept

The application still has full document retrieval functionality:

✅ **Vector Store Integration** - All document search and retrieval  
✅ **Hybrid Search** - Combines semantic and keyword search  
✅ **Document Management** - Upload, indexing, metadata tracking  
✅ **Context Preparation** - Retrieves relevant document chunks  
✅ **Source Citations** - Tracks which documents were used  
✅ **All API Endpoints** - Still functional with placeholder responses  

## Current Implementation

The application uses OpenAI GPT-4o for all LLM functionality. The implementation is in `app/services/llm_engine.py`.

### Main LLM Functions

#### 1. `LLMEngine.chat()` - Conversational Q&A
```python
from app.services.llm_engine import LLMEngine

answer = LLMEngine.chat(
    user_query="What are the payment terms?",
    history=[...],  # Conversation history
    context=[...],  # Retrieved document chunks
    max_words=150,
    allowed_filenames=[...],
    focus_filenames=[...]
)
```

#### 2. `Streaming.chat_stream()` - Streaming responses
```python
from app.services.llm_engine import Streaming

for token in Streaming.chat_stream(
    user_query="...",
    history=[...],
    context=[...],
    focus_filenames=[...]
):
    yield token  # Stream tokens as they're generated
```

#### 3. `LLMEngine.summarize()` - Document summarization
```python
summary = LLMEngine.summarize(
    query="Summarize the contract",
    context=[...],  # Document chunks
    max_words=200
)
```

#### 4. `LLMEngine.extract_terms()` - Term extraction
```python
terms = LLMEngine.extract_terms(
    query="Extract payment terms",
    context=[...],  # Contract chunks
    filter_query="payment"
)
```

## Configuration

The LLM engine uses OpenAI GPT-4o. Configure it via environment variables:

```env
OPENAI_API_KEY=your-api-key-here
```

The implementation includes:
- ✅ Response caching (LRU cache, 64 entries)
- ✅ Output sanitization
- ✅ Streaming support
- ✅ Token counting and context window management
- ✅ Error handling and retries

## Alternative LLM Providers

If you want to switch to a different LLM provider, modify `app/services/llm_engine.py`:

### Option 1: Anthropic Claude
Replace OpenAI calls with Anthropic API:
```python
import anthropic

client = anthropic.Anthropic(api_key="your-key")
response = client.messages.create(
    model="claude-3-sonnet-20240229",
    messages=[{"role": "user", "content": prompt}]
)
```

### Option 2: Local Models
Use transformers for local models:
```python
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-3-mini-4k-instruct")
tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct")
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
```

## Testing Your Integration

### 1. Test with cURL
```bash
curl -X POST http://localhost:8000/api/chat/query \
  -H "Content-Type: application/json" \
  -d '{"message": "What documents do you have?"}'
```

### 2. Test with the Web UI
Open http://localhost:8000 and use the chat interface

### 3. Check logs
```bash
tail -f /Users/harshulmakwana/legal-knowledge-platform/server.log
```

## Current Server Status

✅ Server is running at: http://localhost:8000  
✅ All endpoints functional with OpenAI GPT-4o integration  
✅ Document retrieval working perfectly  
✅ LLM-powered responses fully implemented  
✅ Streaming support available  

---

**Note**: The application is fully functional with OpenAI GPT-4o integration. All LLM functionality is implemented in `app/services/llm_engine.py`.

