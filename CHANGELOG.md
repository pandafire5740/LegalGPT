# Changelog

All notable changes to LegalGPT will be documented in this file.

## [2.0.0] - 2025-10-28

### Major Changes
- **Switched to OpenAI GPT-4o** for all LLM operations (chat, summarization, extraction)
- **OpenAI Embeddings**: Replaced local sentence-transformers with `text-embedding-3-small`
- **Streaming Chat**: Added Server-Sent Events (SSE) for real-time token streaming
- **Contract Extraction**: New intelligent term extraction from files in memory

### Added
- SSE streaming endpoint: `POST /api/chat/query/stream`
- Extract from memory: `POST /api/legalgpt/extract/from-memory`
- Files list for extraction: `GET /api/legalgpt/extract/files-in-memory`
- Inventory intent: Direct file listing for "what files are in memory?" queries
- Light/Dark mode toggle with iOS-style liquid glass design
- Document counter with hover tooltip showing filenames
- Clear files button to reset vector store
- Targeted file Q&A: chat detects filenames in the query and prioritizes those documents

### Changed
- Chat now uses structured messages (system + history + user)
- Retrieval: Relaxed fallback when strict keyword matching returns no results
- Upload: Duplicate detection only checks vector store, allows disk overwrites
- Extract UI: Dropdown selector instead of file upload
- Improved JSON parsing with markdown fence stripping and error recovery

### Removed
- All Hugging Face dependencies (transformers, sentence-transformers)
- Local LLM models (Phi-3, Mistral, Qwen)
- Duplicate env/config files (config.env.example, requirements_legalgpt.txt)
- Unused Docker configuration
- SharePoint sync (kept for future implementation)

### Fixed
- Chat bar positioning: Only visible in Chat tab, pegged to sidebar height
- Duplicate file warnings after reset
- JSON parsing for GPT-4o responses with code fences
- Theme consistency in dark mode across all tabs

## [1.0.0] - Initial Release

### Features
- Document upload and indexing
- Semantic search with ChromaDB
- Basic chat interface
- Local LLM integration (Phi-3)
