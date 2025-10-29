# Document Verification Guide

## How to Verify Your Uploads

### Method 1: Ask the Chat Bot 💬

The easiest way to verify your documents are loaded:

1. Open http://localhost:8000
2. Go to the **Chat** tab
3. Type any of these queries:
   - `What documents do you have?`
   - `List all files`
   - `Show me what's in memory`
   - `What do you know about?`
   - `Which documents are uploaded?`
   - `In "Master Services Agreement", what are the renewal terms?`

**Example Response:**
```
📁 Documents Currently in Memory (2 total):

   1. Complete_with_Docusign_Sapien-Playlist_MNDA.pdf
   2. test_legal_doc.txt

💡 What I can do:
   • Answer questions about these documents
   • Search for specific terms or clauses
   • Summarize document content
   • Extract key information

Feel free to ask me anything about these documents!
```

### Method 2: Use the API Endpoint 🔧

For programmatic verification:

```bash
curl http://localhost:8000/api/search/status
```

**Response:**
```json
{
  "status": "ready",
  "total_files": 2,
  "total_chunks": 2,
  "documents": [
    {
      "file_id": "f_1",
      "filename": "Complete_with_Docusign_Sapien-Playlist_MNDA.pdf",
      "chunk_count": 1,
      "source": "local"
    },
    {
      "file_id": "f_2",
      "filename": "test_legal_doc.txt",
      "chunk_count": 1,
      "source": "local"
    }
  ]
}
```

### Method 3: Use the Search Tab 🔍

1. Go to the **Search** tab
2. Try searching for a term you know is in your documents
3. If results appear, your documents are indexed!

---

## Complete Upload & Verification Workflow

### Step 1: Upload Documents
1. Click **"Upload Local Documents"** in the sidebar
2. Select your PDF or DOCX files
3. Click **"Upload Documents"**
4. Wait for the progress bar to complete
5. See the success message

### Step 2: Verify Upload (Immediate)
**Option A - Chat Verification:**
```
You: "What documents do you have?"

Bot: 📁 Documents Currently in Memory (3 total):
     1. Your_New_Document.pdf
     2. Complete_with_Docusign_Sapien-Playlist_MNDA.pdf
     3. test_legal_doc.txt

You: "In Master_Services_Agreement_Long_Form.pdf, what are the renewal terms?"

Bot: [Uses only that document in the response or notifies you if it can’t be found]
```

**Option B - API Verification:**
```bash
curl -s http://localhost:8000/api/search/status | jq '.documents[].filename'
```

### Step 3: Test Search
```
Search Query: "confidential information"
Results: Should show snippets from your uploaded documents
```

### Step 4: Test Chat
```
You: "What does the NDA say about confidential information?"

Bot: [Provides answer with source citations from your documents]
```

---

## Troubleshooting

### ❌ "No documents found in the system"

**Possible causes:**
1. Upload failed - check browser console for errors
2. Processing incomplete - wait 30 seconds and ask again
3. Index not built - run: `curl -X POST http://localhost:8000/api/search/rebuild`

**Solution:**
```bash
# Rebuild the search index
curl -X POST http://localhost:8000/api/search/rebuild

# Check status
curl http://localhost:8000/api/search/status
```

### ❌ Document appears in list but not searchable

**Solution:**
The document is in ChromaDB but not in the FAISS search index. Rebuild:
```bash
curl -X POST http://localhost:8000/api/search/rebuild
```

### ❌ Search returns no results

1. **Check document list:**
   ```
   Chat: "What documents do you have?"
   ```

2. **Verify term exists:**
   - Search for common legal terms: "NDA", "confidential", "agreement"
   - If still no results, check if document was processed correctly

3. **Rebuild index:**
   ```bash
   curl -X POST http://localhost:8000/api/search/rebuild
   ```

---

## Understanding Document Sources

### ChromaDB (Chat Storage)
- Used by the **Chat** feature
- Stores document chunks with metadata
- Enables hybrid search (vector + keyword)
- Updated immediately on upload

### FAISS Index (Advanced Search)
- Used by the **Search** tab
- Enables semantic similarity search
- Provides grouped results with AI summaries
- Updated via auto-rebuild after upload

### Both are Checked
When you ask "What documents do you have?", the chat checks **both** sources and deduplicates the results!

---

## Quick Reference

| Action | Command |
|--------|---------|
| List documents (Chat) | "What documents do you have?" |
| List documents (API) | `curl http://localhost:8000/api/search/status` |
| Rebuild search index | `curl -X POST http://localhost:8000/api/search/rebuild` |
| Test search | Visit http://localhost:8000 → Search tab |
| Upload documents | Sidebar → "Upload Local Documents" |

---

## Best Practices

✅ **Always verify after upload:**
- Ask chat: "What documents do you have?"
- New files should appear immediately

✅ **If something seems wrong:**
1. Check the list first
2. If document is listed but not searchable, rebuild index
3. If document is not listed, try uploading again

✅ **Regular maintenance:**
- After uploading multiple documents, rebuild the search index
- This ensures optimal search performance

---

**Need Help?**
Check the server logs for detailed information:
```bash
tail -50 /Users/harshulmakwana/legal-knowledge-platform/server.log
```





