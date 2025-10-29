# LegalGPT - AI-Powered Legal Document Platform

An intelligent legal document management system powered by OpenAI GPT-4o. Upload contracts, search with natural language, chat with your documents, and extract key terms automatically.

## 🚀 Features

### Core Capabilities
- **AI Chat**: Conversational interface with GPT-4o streaming responses
- **Document Upload**: Upload and index legal documents (PDF, Word, TXT)
- **Smart Search**: Semantic search with AI-generated summaries
- **Contract Extraction**: Intelligent extraction of key terms from contracts
- **Light/Dark Mode**: iOS-style liquid glass theme toggle

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Frontend  │ ───│   FastAPI App    │ ───│   ChromaDB      │
│   (HTML/JS/CSS) │    │   (REST API)     │    │   (Vector DB)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
            ┌───────▼────┐ ┌──▼────────┐
            │  OpenAI    │ │   Redis   │
            │  GPT-4o    │ │  (Cache)  │
            └────────────┘ └───────────┘
```

### Tech Stack
- **Frontend**: Vanilla JavaScript, CSS with modern Flexbox layout
- **Backend**: FastAPI (Python 3.9+)
- **AI**: OpenAI GPT-4o for chat, summarization, and extraction
- **Embeddings**: OpenAI text-embedding-3-small
- **Vector DB**: ChromaDB for semantic search
- **Cache**: Redis for performance optimization

## 📋 Prerequisites

- **Python 3.9 or higher**
- **OpenAI API key** ([Get one here](https://platform.openai.com/api-keys))
- **Redis server** (for caching)
- **~2GB RAM** minimum
- **~500MB disk space** for dependencies

## 🛠️ Installation

### 1. Clone and Setup

```bash
cd /Users/harshulmakwana/legal-knowledge-platform

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start Redis Server

**Option A: Use included Redis:**
```bash
cd redis-stable/src
./redis-server --daemonize yes --port 6379
```

**Option B: Install system Redis:**
```bash
# macOS
brew install redis
brew services start redis

# Ubuntu
sudo apt-get install redis-server
sudo systemctl start redis-server
```

### 3. Configuration

Copy `env.example` to `.env` and add your OpenAI API key:

```bash
cp env.example .env
```

Edit `.env` and set your OpenAI API key:

```env
# Required
OPENAI_API_KEY=sk-proj-your-actual-key-here

# Optional (defaults shown)
REDIS_URL=redis://localhost:6379/0
CHROMA_PERSIST_DIRECTORY=./chroma_db
UPLOADS_DIRECTORY=./uploads
PORT=8000
```

## 🚀 Running the Application

### Quick Start

```bash
# Make sure Redis is running first
python3 start.py
```

The app will:
1. Check Redis connection
2. Initialize OpenAI client
3. Start the web server on `http://localhost:8000`

**First time setup**: Ensure your OpenAI API key is set in `.env`

### Manual Start

```bash
# With uvicorn directly
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 📚 Documentation

- Architecture: docs/ARCHITECTURE.md
- Search: docs/SEARCH.md
- Formatting Guide: docs/FORMATTING_GUIDE.md
- QA & Verification: docs/QA_AND_VERIFICATION.md
- Performance & Stability: docs/PERFORMANCE.md
- LLM Integration Guide: docs/LLM_INTEGRATION_GUIDE.md
- Changelog: CHANGELOG.md

## 🌐 Usage

### Web Interface

Open your browser to `http://localhost:8000` and explore three powerful modes:

#### Chat Mode
- Ask questions about your documents in natural language
- Streaming responses powered by GPT-4o
- Contextual answers grounded in your uploaded files
- Reference specific filenames (full name or nickname) to focus responses on that document
- Example: "What are the payment terms in the MSA?"

#### Search Mode  
- Semantic search across all documents
- AI-generated summaries of search results
- Grouped results by document with relevance scores
- Example: "Find all termination clauses"

#### Extract Mode
- Select any uploaded contract from the dropdown
- Click "Extract Terms" to analyze with GPT-4o
- Get structured extraction of key contract terms
- Export results as CSV for review

### API Endpoints

#### Health Check
```bash
GET /api/health/                 # Basic health check
GET /api/health/detailed         # Detailed system status
GET /api/health/models           # AI model status
```

#### Search
```bash
POST /api/search/                # Search documents
  {
    "query": "confidentiality clause",
    "top_k_groups": 5,
    "max_snippets_per_group": 3
  }

POST /api/search/rebuild         # Rebuild search index
GET /api/search/status           # List indexed documents
```

#### Chat
```bash
POST /api/chat/query             # Chat with documents (full response)
POST /api/chat/query/stream      # Streaming chat with SSE
  {
    "message": "What are the payment terms?",
    "conversation_history": []   # Optional
  }
```

#### Extract
```bash
GET /api/legalgpt/extract/files-in-memory  # List files available for extraction
POST /api/legalgpt/extract/from-memory     # Extract terms from a file
  {
    "filename": "contract.pdf"
  }
```

#### Documents
```bash
POST /api/documents/upload       # Upload new documents
GET /api/documents/stats         # Get collection statistics
```

### Example Queries

**Search:**
- "termination clauses"
- "confidentiality agreement"
- "liability limitations"

**Chat:**
- "What documents do you have?"
- "Summarize all documents"
- "What are the key terms in the NDA?"
- "Find all payment deadlines"
- "In “Master_Services_Agreement_Long_Form.pdf”, what is the renewal clause?"

#### Targeted File Questions
- Mention the filename (with or without extension) to zero in on that document
- Aliases like "Master Services Agreement" or "MSA" are detected automatically
- If a file can’t be located, LegalGPT will respond with a plain-language warning

## ⚡ Performance

- **Chat**: Streaming responses typically complete in 2-5 seconds
- **Search**: Near-instant (<500ms) with AI summaries
- **Extraction**: 3-8 seconds depending on document length
- **Upload**: Background processing, immediate feedback

### Cost Optimization
- Uses OpenAI's efficient `text-embedding-3-small` for embeddings
- GPT-4o calls are optimized with caching
- Typical usage: $0.01-0.05 per document for full analysis

## 🔧 Troubleshooting

### Common Issues

**"Redis connection failed"**
- Start Redis: `cd redis-stable/src && ./redis-server --daemonize yes`
- Or install system Redis (see Installation section)

**"OpenAI API error"**
- Verify your API key is correct in `.env`
- Check you have credits/billing set up at platform.openai.com
- Ensure `OPENAI_API_KEY` starts with `sk-proj-` or `sk-`

**Chat responses slow**
- Check your internet connection (API calls require network)
- First query may take longer as OpenAI initializes
- Streaming should show tokens within 1-2 seconds

**Search returns no results**
- Upload documents first via web interface
- Check `/api/search/status` to see indexed documents
- Try rebuilding index: `POST /api/search/rebuild`

**Port 8000 already in use**
```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9
```

## 🤖 AI Models

| Component | Model | Purpose |
|-----------|-------|---------|
| Chat | GPT-4o | Conversational Q&A, document summarization |
| Extraction | GPT-4o | Contract term extraction, clause analysis |
| Embeddings | text-embedding-3-small | Semantic search, document similarity |

All powered by OpenAI's API for:
- ✅ State-of-the-art accuracy
- ✅ Fast streaming responses
- ✅ Intelligent contract analysis
- ✅ Consistent, reliable outputs

## 📝 Development

### Project Structure

```
app/
├── api/                      # REST API endpoints
│   ├── chat.py              # Chat with streaming support
│   ├── documents.py         # Document upload/management
│   ├── health.py            # System health checks
│   ├── legalgpt_extract.py  # Contract term extraction
│   └── search.py            # Semantic search
├── services/                # Core business logic
│   ├── llm_engine.py        # OpenAI GPT-4o integration
│   ├── vector_store.py      # ChromaDB + OpenAI embeddings
│   ├── document_processor.py # Text extraction & chunking
│   ├── context_assembler.py # RAG context building
│   ├── search_ingest.py     # FAISS indexing
│   ├── search_query.py      # Hybrid search with MMR
│   └── intent.py            # Query intent detection
├── static/                  # Web frontend
│   ├── index.html          # Single-page application
│   ├── styles.css          # Modern UI with dark mode
│   └── app.js              # SSE streaming, state management
├── config.py                # Settings management
└── main.py                  # FastAPI application
```

## 🔒 Security & Privacy

- 🔐 **Secure Storage**: Documents stored locally in encrypted ChromaDB
- 🌐 **API Security**: OpenAI API calls use HTTPS encryption
- 📁 **Data Control**: All uploaded files remain on your server
- 🚫 **No Sharing**: Documents and queries are not used for OpenAI training
- ⚡ **Fast Caching**: Response caching reduces redundant API calls

## 📄 License

This project is proprietary software for internal use.

## 🆘 Support

For issues:
1. Check troubleshooting section above
2. Review logs in `server.log`
3. Check health endpoint: `http://localhost:8000/api/health/detailed`

---

**Built with ❤️ for Legal Teams**
