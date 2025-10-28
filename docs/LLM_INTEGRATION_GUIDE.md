# LLM Integration Guide

## What Was Removed

All LLM (Large Language Model) logic has been stripped from the application. Here's what was removed from `app/services/ai_service.py`:

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

## Current Behavior

The AI service now returns **placeholder responses** that include:
- Retrieved relevant document excerpts
- Source document citations
- Messages indicating LLM integration is needed
- Full context that would be passed to an LLM

### Example Response

```json
{
  "answer": "🔧 **LLM Integration Needed**\n\nI found 5 relevant document excerpts for your query, but LLM integration is not yet implemented.\n\n**Retrieved Context:**\n[Document excerpts here]\n\n💡 Implement your LLM integration in `app/services/ai_service.py` to generate intelligent responses.",
  "source_documents": [...],
  "query": "user query",
  "timestamp": "2025-10-28T13:20:00",
  "llm_integration_status": "pending"
}
```

## Where to Add Your LLM Integration

### File Location
`/Users/harshulmakwana/legal-knowledge-platform/app/services/ai_service.py`

### Key Methods to Implement

#### 1. `process_query()` - Main chat interface
**Line ~26**
```python
async def process_query(self, query: str, conversation_history: Optional[List[Dict[str, str]]] = None, model_preference: str = "phi") -> Dict[str, Any]:
    # Document retrieval already works ✅
    relevant_docs = self.vector_store.hybrid_search(query, n_results=10)
    
    # TODO: Add your LLM integration here
    # - Build prompt from relevant_docs
    # - Call your LLM API/model
    # - Parse and return response
```

#### 2. `summarize_document()` - Document summarization
**Line ~123**
```python
async def summarize_document(self, file_name: str) -> Dict[str, Any]:
    # Document retrieval already works ✅
    file_docs = [doc for doc in all_docs if doc['metadata'].get('file_name') == file_name]
    
    # TODO: Add your LLM integration here
    # - Combine document chunks
    # - Generate summary with LLM
```

#### 3. `_summarize_all_documents()` - Multi-document overview
**Line ~282**
```python
async def _summarize_all_documents(self, query: str) -> Dict[str, Any]:
    # Document collection already works ✅
    all_docs = self.vector_store.get_all_documents()
    
    # TODO: Add your LLM integration here
    # - Generate overview of all documents
```

#### 4. `extract_terms_conditions()` - Structured extraction
**Line ~176**
```python
async def extract_terms_conditions(self, query_filter: Optional[str] = None) -> Dict[str, Any]:
    # Document search already works ✅
    relevant_docs = self.vector_store.hybrid_search(search_query, n_results=15)
    
    # TODO: Add your LLM integration here
    # - Extract structured terms/conditions
    # - Parse legal clauses
```

## Integration Options

### Option 1: OpenAI API
```python
import openai

client = openai.OpenAI(api_key="your-key")
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}]
)
answer = response.choices[0].message.content
```

### Option 2: Anthropic Claude API
```python
import anthropic

client = anthropic.Anthropic(api_key="your-key")
response = client.messages.create(
    model="claude-3-sonnet-20240229",
    messages=[{"role": "user", "content": prompt}]
)
answer = response.content[0].text
```

### Option 3: Local Models (like before)
```python
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

# Load model (add caching logic)
model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-3-mini-4k-instruct")
tokenizer = AutoTokenizer.from_pretrained("microsoft/Phi-3-mini-4k-instruct")

# Create pipeline
pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

# Generate
response = pipe(prompt, max_new_tokens=200)
```

### Option 4: LangChain
```python
from langchain_openai import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain

llm = ChatOpenAI(model="gpt-4")
# Use with existing vector store retriever
```

### Option 5: LlamaIndex
```python
from llama_index import VectorStoreIndex, ServiceContext
from llama_index.llms import OpenAI

llm = OpenAI(model="gpt-4")
# Connect with existing ChromaDB
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

## File Statistics

- **Original file size**: 712 lines
- **Stripped down size**: 390 lines
- **Lines removed**: ~322 lines (45% reduction)
- **Dependencies removed**: transformers, torch model loading
- **Memory footprint**: Reduced by ~2-3GB (no model in memory)

## Next Steps

1. ✅ Choose your LLM integration approach (API vs local model)
2. ✅ Add necessary dependencies to `requirements.txt`
3. ✅ Implement LLM calls in the methods marked with TODO
4. ✅ Test with various queries
5. ✅ Handle errors and timeouts appropriately
6. ✅ Add any necessary API keys to `.env` configuration

## Configuration

You may want to add these to your `.env` file:

```env
# LLM Configuration
LLM_PROVIDER=openai  # or anthropic, local, etc.
LLM_MODEL=gpt-4
LLM_API_KEY=your-api-key-here
LLM_MAX_TOKENS=500
LLM_TEMPERATURE=0.7

# Rate Limiting
LLM_MAX_REQUESTS_PER_MINUTE=10
LLM_TIMEOUT_SECONDS=30
```

## Current Server Status

✅ Server is running at: http://localhost:8000  
✅ All endpoints functional with placeholder responses  
✅ Document retrieval working perfectly  
✅ Ready for LLM integration  

---

**Note**: The application is fully functional for document upload, search, and retrieval. Only the LLM-powered response generation needs to be implemented.

