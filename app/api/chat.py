"""Chat API endpoints for AI-powered document querying."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.services.vector_store import VectorStore
from app.services.llm_engine import LLMEngine, Streaming
from app.services.context_assembler import assemble_context
from app.services.intent import detect_intent

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str = Field(..., description="User's question or request")
    conversation_history: Optional[List[ChatMessage]] = Field(
        default=None, 
        description="Previous conversation messages for context"
    )
    model: Optional[str] = Field(
        default="phi",
        description="Model to use (fixed to 'phi')"
    )


class TermsExtractionRequest(BaseModel):
    """Terms and conditions extraction request model."""
    filter_query: Optional[str] = Field(
        default=None,
        description="Optional filter for specific types of contracts"
    )


@router.post("/query")
async def chat_query(request: ChatRequest) -> Dict[str, Any]:
    """
    Process a chat query and return AI-generated response with supporting documents.
    """
    try:
        logger.info(f"Processing chat query, message_length: {len(request.message)}")
        
        vector_store = VectorStore()
        
        # Convert Pydantic models to dict for AI service
        conversation_history = None
        if request.conversation_history:
            conversation_history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.conversation_history
            ]
        
        # Assemble context and detect intent
        intent = detect_intent(request.message)
        # First pass: strict retrieval
        ctx = assemble_context(request.message, n_results=12, require_keyword=True)
        
        if intent == "inventory":
            inv = ctx.get("inventory", [])
            # Deterministic, plain list of filenames (no LLM, no extra text)
            names = []
            for item in inv:
                fn = item.get('filename')
                if fn:
                    names.append(fn)
            # Unique and sorted for readability
            unique_sorted = sorted(set(names))
            answer = "\n".join(unique_sorted) if unique_sorted else "No files in memory."
            return {
                "status": "success",
                "answer": answer,
                "source_documents": [],
                "query": request.message,
            }
        
        if intent == "capabilities":
            answer = (
                "I can upload and index documents, search and summarize results, answer questions using your files, "
                "and extract key contract clauses for review."
            )
            return {
                "status": "success",
                "answer": answer,
                "source_documents": [],
                "query": request.message,
            }
        
        # Default: RAG using retrieved chunks
        relevant = ctx.get("retrieved_chunks", [])
        # Retry with relaxed keyword requirement if strict returned little/no context
        if not relevant:
            try:
                relevant = vector_store.hybrid_search(request.message, n_results=12, require_keyword=False)
            except Exception:
                relevant = []
        top_context = relevant[:10]

        # If greeting and no meaningful context, return a friendly greeting without LLM
        msg_lower = request.message.strip().lower()
        if msg_lower in {"hi", "hello", "hey", "howdy"}:
            has_meaningful = any(doc.get("content_match") for doc in relevant)
            if not has_meaningful:
                return {
                    "status": "success",
                    "answer": "I’m LegalGPT, the internal legal assistant. How can I help?",
                    "source_documents": [],
                    "query": request.message,
                }
        # Explicit identity response
        if msg_lower.strip() in {"who are you", "who are you?"}:
            return {
                "status": "success",
                "answer": "I’m LegalGPT, the internal legal assistant. How can I help?",
                "source_documents": [],
                "query": request.message,
            }
        # Build history list
        history = conversation_history or []
        allowed_names = []
        for doc in top_context:
            md = doc.get("metadata", {})
            fname = md.get("file_name")
            if fname:
                allowed_names.append(fname)
        answer = LLMEngine.chat(request.message, history, top_context, max_words=150, allowed_filenames=allowed_names)

        # Sanitize citations: if allowed list empty, strip all; else keep only allowed
        if answer:
            import re
            if allowed_names:
                allowed_set = set(allowed_names)
                def repl(m):
                    token = m.group(1).strip()
                    return f"[{token}]" if token in allowed_set else ""
                answer = re.sub(r"\[(.*?)\]", repl, answer)
            else:
                answer = re.sub(r"\[(.*?)\]", "", answer)
        # Build source documents for UI
        sources_dict = {}
        for doc in top_context:
            md = doc.get("metadata", {})
            fname = md.get("file_name", "Unknown")
            if fname not in sources_dict:
                sources_dict[fname] = {
                    "file_name": fname,
                    "file_path": md.get("file_path", "N/A"),
                    "similarity_score": doc.get("final_score", doc.get("similarity_score", 0.0)),
                    "excerpt": (doc.get("content", "")[:200] + "...") if len(doc.get("content", "")) > 200 else doc.get("content", ""),
                }
        source_documents = list(sources_dict.values())
        return {
            "status": "success",
            "answer": answer,
            "source_documents": source_documents,
            "query": request.message,
        }
        
    except Exception as e:
        logger.error(f"Failed to process chat query, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/query/stream")
async def chat_query_stream(request: ChatRequest):
    """Stream a chat response token-by-token using Server-Sent Events (SSE)."""
    try:
        vector_store = VectorStore()
        # Strict retrieval first
        ctx = assemble_context(request.message, n_results=12, require_keyword=True)
        relevant = ctx.get("retrieved_chunks", [])
        if not relevant:
            try:
                relevant = vector_store.hybrid_search(request.message, n_results=12, require_keyword=False)
            except Exception:
                relevant = []
        top_context = relevant[:10]
        history = []
        if request.conversation_history:
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.conversation_history
            ]

        def event_stream():
            # Wrap OpenAI stream as SSE data events
            for token in Streaming.chat_stream(request.message, history, top_context):
                yield f"data: {token}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Failed to stream chat query, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Streaming failed: {str(e)}")


# Legacy endpoints removed - use /api/legalgpt/extract/ for term extraction


@router.get("/suggestions")
async def get_query_suggestions() -> Dict[str, Any]:
    """
    Get example queries that users can ask.
    """
    suggestions = [
        {
            "category": "Document Search",
            "examples": [
                "Show me all contracts with termination clauses",
                "Find documents mentioning confidentiality agreements",
                "What contracts have liability limitations?",
                "Search for agreements with Company ABC"
            ]
        },
        {
            "category": "Document Analysis",
            "examples": [
                "Summarize the main contract for Project X",
                "What are the payment terms in the vendor agreement?",
                "Extract all key dates from employment contracts",
                "Compare liability clauses across all contracts"
            ]
        },
        {
            "category": "Terms & Conditions",
            "examples": [
                "Get terms and conditions from all service agreements",
                "Show termination conditions in employment contracts",
                "Extract governing law clauses from all documents",
                "Find all indemnification terms"
            ]
        },
        {
            "category": "File Management",
            "examples": [
                "Where is the contract with Vendor ABC stored?",
                "Find the location of the NDA with Company XYZ",
                "Show me all contracts modified this month",
                "List all PDF contracts in the system"
            ]
        }
    ]
    
    return {
        "status": "success",
        "suggestions": suggestions
    }


@router.post("/feedback")
async def submit_feedback(
    query: str,
    response_id: str,
    rating: int,
    feedback: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit feedback on a chat response for improvement.
    """
    try:
        # Log feedback for analysis
        logger.info(f"Received user feedback, query: {query}, response_id: {response_id}, rating: {rating}, feedback: {feedback}")
        
        # In a production system, you'd store this in a database
        # for analysis and model improvement
        
        return {
            "status": "success",
            "message": "Thank you for your feedback!"
        }
        
    except Exception as e:
        logger.error(f"Failed to submit feedback, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Feedback submission failed: {str(e)}")


@router.get("/conversation-starters")
async def get_conversation_starters() -> Dict[str, Any]:
    """
    Get conversation starter prompts based on available documents.
    """
    try:
        vector_store = VectorStore()
        stats = vector_store.get_collection_stats()
        
        starters = [
            f"I have {stats['total_chunks']} document sections available. What would you like to know?",
            "Ask me about terms and conditions in your contracts.",
            "I can help you find specific clauses or document locations.",
            "Let me summarize any document for you.",
            "Search for contracts by company name, date, or content."
        ]
        
        return {
            "status": "success",
            "starters": starters,
            "document_stats": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get conversation starters, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get starters: {str(e)}")


# WebSocket endpoint for real-time chat (optional enhancement)
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set

active_connections: Set[WebSocket] = set()

@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            if message:
                # Process query
                vector_store = VectorStore()
                ai_service = AIService(vector_store)
                
                response = await ai_service.process_query(message)
                
                # Send response back
                await websocket.send_json({
                    "type": "response",
                    "data": response
                })
                
    except WebSocketDisconnect:
        active_connections.discard(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.close()
        active_connections.discard(websocket)
"""
