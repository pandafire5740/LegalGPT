# LegalGPT - Legal Knowledge Platform

Internal AI assistant for the Legal team providing private natural-language search over Legal SharePoint and Legal Slack channels, contract term extraction from uploaded files, and reusable prompt templates for common legal tasks.

## Features

- **Natural-language search** across SharePoint (Legal site) and Slack (approved channels)
- **Contract term extraction** from uploaded files with consistent schema
- **Built-in prompt templates** for routine legal workflows
- **Simple analytics** and optional survey collection

## Architecture

### Backend (FastAPI)
- **Retrieval Module**: SharePoint and Slack integration with FAISS vector search
- **Extraction Module**: Contract field extraction using OpenAI with structured output
- **Prompts Module**: Template management for common legal tasks
- **Survey Module**: Usage analytics and feedback collection

### Frontend
- Reuse existing v0 chatbot UI
- Add mode toggles (Chat | Search | Extract)
- Left sidebar for Prompt Templates with CRUD operations

## Local Development

### Prerequisites
- Python 3.11+
- OpenAI API key
- Microsoft Graph credentials (for SharePoint)
- Slack bot token (for Slack integration)

### Setup

1. **Create virtual environment:**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. **Install dependencies:**
```bash
pip install -r requirements_legalgpt.txt
```

3. **Configure environment:**
```bash
cp env.example .env
# Edit .env with your API keys and credentials
```

4. **Start the backend:**
```bash
uvicorn backend.app:app --reload --port 8000
```

5. **Frontend setup:**
Use your existing v0 chatbot. Add new routes/views and call the API endpoints.

## Environment Variables

```bash
# OpenAI
OPENAI_API_KEY=your-openai-api-key

# Microsoft Graph (client credentials flow)
MS_TENANT_ID=your-tenant-id
MS_CLIENT_ID=your-client-id
MS_CLIENT_SECRET=your-client-secret
SHAREPOINT_SITE_URL=https://contoso.sharepoint.com/sites/Legal

# Slack
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token

# App Configuration
PROMPTS_PATH=prompts/prompts.json
PORT=8000
```

## API Endpoints

### Retrieval
- `POST /api/search` - Hybrid search across SharePoint and Slack
- `GET /api/search/stats` - Search index statistics

### Contract Extraction
- `POST /api/extract` - Extract contract fields from uploaded files
- `GET /api/extract/export` - Export extraction results as CSV
- `POST /api/extract/export` - Export specific results as CSV

### Prompt Templates
- `GET /api/prompts` - List all prompt templates
- `POST /api/prompts` - Save prompt templates

### Survey
- `POST /api/survey/response` - Submit survey response
- `GET /api/survey/aggregate` - Get survey analytics

## Contract Extraction Schema

The system extracts the following fields from contracts:

- `counterparty` - Name of the other party
- `effective_date` - Contract effective date
- `expiration_or_renewal` - Expiration or renewal terms
- `renewal_terms` - Renewal conditions
- `termination_clause` - Termination provisions
- `governing_law` - Jurisdiction and governing law
- `payment_terms` - Payment terms and amounts
- `notice_clause` - Notice requirements
- `data_protection` - Data protection provisions
- `limitation_of_liability` - Liability limitations
- `indemnity` - Indemnification terms
- `assignment` - Assignment provisions
- `confidentiality` - Confidentiality terms

## System Prompts & Guardrails

### Core System Message
```
You are LegalGPT, an internal assistant for the Legal team. You retrieve and
summarize information from approved sources (SharePoint, Slack) and extract
contract terms. You do not provide legal advice. Always cite sources with
titles and links when answering retrieval queries. Respect user permissions.
```

### Privacy Rules
- Never exfiltrate or store document contents externally
- Refuse queries outside approved sources or channels
- If the user asks for legal advice, respond: "I can summarize information, but I can't advise."

## Security & Privacy

- **No external logging** of customer data
- **Org-managed API keys** with principle of least privilege
- **Microsoft Entra ID (SSO)** for Legal group authentication
- **Slack tokens scoped** to Legal channels only
- **Modular design** isolating retrieval, extraction, and prompting

## Data Sources

### SharePoint Integration
- **Scope**: Legal SharePoint site only
- **Permissions**: Files.Read.All, Sites.Read.All, User.Read
- **Indexing**: Documents, metadata, and content

### Slack Integration
- **Allowed Channels**: #legal-shared, #legal-intake
- **Permissions**: channels:read, channels:history, groups:history, files:read, search:read
- **Indexing**: Messages, file links, and metadata

## Indexing & Search

### FAISS Vector Index
- **Embeddings**: OpenAI text-embedding-3-large
- **Storage**: Local FAISS index with metadata
- **Hybrid Search**: Combines vector similarity and keyword matching

### Search Features
- **Hybrid retrieval**: Keyword prefilter + vector search
- **Source citations**: Links and modified timestamps
- **Relevance scoring**: Combined vector and keyword scores

## Deployment

### Development
```bash
uvicorn backend.app:app --reload --port 8000
```

### Production
```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --workers 4
```

## Monitoring & Analytics

- **Usage tracking**: Feature usage and query patterns
- **Survey collection**: Optional lightweight feedback
- **Error monitoring**: Comprehensive logging and error handling
- **Performance metrics**: Search latency and extraction accuracy

## Troubleshooting

### Common Issues

1. **OpenAI API errors**: Check API key and rate limits
2. **SharePoint authentication**: Verify Microsoft Graph credentials
3. **Slack integration**: Ensure bot token has required scopes
4. **FAISS index**: Check disk space and permissions

### Logs
- Backend logs: Check uvicorn output
- Index logs: Check data/legal_index_*.log files
- API logs: Check FastAPI request logs

## Contributing

1. Follow the modular architecture
2. Add comprehensive logging
3. Include error handling
4. Update documentation
5. Test with sample data

## License

Internal use only - Legal team at Mindbody + ClassPass





