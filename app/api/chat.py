"""Chat API endpoints for AI-powered document querying."""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.services.vector_store import VectorStore
from app.services.llm_engine import LLMEngine, Streaming
from app.services.context_assembler import assemble_context
from app.services.intent import detect_intent
from app.dependencies import get_vector_store

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


def _process_chat_request(
    message: str,
    conversation_history: Optional[List[Dict[str, str]]],
    vector_store: VectorStore
) -> Dict[str, Any]:
    """
    Process a chat request and return structured data for both streaming and non-streaming endpoints.
    
    Args:
        message: User's message/query
        conversation_history: Conversation history as list of dicts with 'role' and 'content'
        vector_store: VectorStore instance
        
    Returns:
        Dictionary with keys:
        - intent: Detected intent ("inventory", "capabilities", "rag")
        - answer: Answer text (if available, None for RAG that needs LLM)
        - user_query: Processed query string
        - top_context: List of context chunks for LLM
        - focus_filenames: List of focused filenames
        - allowed_names: List of allowed filenames for citations
        - missing_filenames: List of missing filenames
        - source_documents: List of source document metadata (for non-streaming)
        - requires_llm: Boolean indicating if LLM call is needed
    """
    # Convert conversation history format if needed
    history = conversation_history or []
    
    # Detect intent
    intent = detect_intent(message, conversation_history=history)
    
    # Assemble context
    ctx = assemble_context(vector_store, message, n_results=12, require_keyword=True)
    user_query = ctx.get("processed_query") or message
    targeted_filenames = ctx.get("targeted_filenames", []) or []
    targeted_found = ctx.get("targeted_found", []) or []
    missing_filenames = ctx.get("missing_filenames", []) or []
    
    # Handle inventory intent
    if intent == "inventory":
        inv = ctx.get("inventory", [])
        names = []
        for item in inv:
            fn = item.get('filename')
            if fn:
                names.append(fn)
        unique_sorted = sorted(set(names))
        answer = "\n".join(unique_sorted) if unique_sorted else "No files in memory."
        return {
            "intent": intent,
            "answer": answer,
            "user_query": user_query,
            "top_context": [],
            "focus_filenames": None,
            "allowed_names": [],
            "missing_filenames": [],
            "source_documents": [],
            "requires_llm": False,
        }
    
    # Handle capabilities intent
    if intent == "capabilities":
        answer = (
            "I can upload and index documents, search and summarize results, answer questions using your files, "
            "and extract key contract clauses for review."
        )
        return {
            "intent": intent,
            "answer": answer,
            "user_query": user_query,
            "top_context": [],
            "focus_filenames": None,
            "allowed_names": [],
            "missing_filenames": [],
            "source_documents": [],
            "requires_llm": False,
        }
    
    # Default: RAG using retrieved chunks
    relevant = ctx.get("retrieved_chunks", [])
    
    # Handle missing targeted files
    if targeted_filenames and not targeted_found:
        missing_list = ", ".join(sorted(set(targeted_filenames)))
        answer = (
            "I couldn't find any indexed content for the file(s) you mentioned: "
            f"{missing_list}. Please check the filename spelling or upload the document again."
        )
        return {
            "intent": intent,
            "answer": answer,
            "user_query": user_query,
            "top_context": [],
            "focus_filenames": None,
            "allowed_names": [],
            "missing_filenames": missing_filenames,
            "source_documents": [],
            "requires_llm": False,
        }
    
    # Retry with relaxed keyword requirement if strict returned little/no context
    if not relevant:
        try:
            relevant = vector_store.hybrid_search(message, n_results=12, require_keyword=False)
        except Exception:
            relevant = []
    
    # Use 6 chunks to match LLMEngine limits for consistency
    top_context = relevant[:6]
    focus_filenames = targeted_found if targeted_found else None
    
    # Handle empty context
    if not top_context:
        answer = "I couldn't find any indexed passages that match your request yet. Try rephrasing or upload the relevant document first."
        return {
            "intent": intent,
            "answer": answer,
            "user_query": user_query,
            "top_context": [],
            "focus_filenames": focus_filenames,
            "allowed_names": [],
            "missing_filenames": missing_filenames,
            "source_documents": [],
            "requires_llm": False,
        }
    
    # Handle greetings and identity queries
    msg_lower = message.strip().lower()
    if msg_lower in {"hi", "hello", "hey", "howdy"}:
        has_meaningful = any(doc.get("content_match") for doc in relevant)
        if not has_meaningful:
            answer = "I'm LegalGPT, the internal legal assistant. How can I help?"
            return {
                "intent": intent,
                "answer": answer,
                "user_query": user_query,
                "top_context": [],
                "focus_filenames": focus_filenames,
                "allowed_names": [],
                "missing_filenames": missing_filenames,
                "source_documents": [],
                "requires_llm": False,
            }
    
    if msg_lower.strip() in {"who are you", "who are you?"}:
        answer = "I'm LegalGPT, the internal legal assistant. How can I help?"
        return {
            "intent": intent,
            "answer": answer,
            "user_query": user_query,
            "top_context": [],
            "focus_filenames": focus_filenames,
            "allowed_names": [],
            "missing_filenames": missing_filenames,
            "source_documents": [],
            "requires_llm": False,
        }
    
    # Build allowed filenames for citations
    if focus_filenames:
        allowed_names = list(dict.fromkeys(focus_filenames))
    else:
        allowed_names = []
        for doc in top_context:
            md = doc.get("metadata", {})
            fname = md.get("file_name")
            if fname:
                allowed_names.append(fname)
    
    # Build source documents metadata
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
        "intent": intent,
        "answer": None,  # Will be generated by LLM
        "user_query": user_query,
        "top_context": top_context,
        "focus_filenames": focus_filenames,
        "allowed_names": allowed_names,
        "missing_filenames": missing_filenames,
        "source_documents": source_documents,
        "requires_llm": True,
    }


@router.post("/query")
async def chat_query(
    request: ChatRequest,
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """
    Process a chat query and return AI-generated response with supporting documents.
    """
    try:
        logger.info(f"Processing chat query, message_length: {len(request.message)}")
        
        # Convert Pydantic models to dict
        conversation_history = None
        if request.conversation_history:
            conversation_history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.conversation_history
            ]
        
        # Process request using shared logic
        result = _process_chat_request(request.message, conversation_history, vector_store)
        
        # If answer is already determined (no LLM needed), return it
        if not result["requires_llm"]:
            return {
                "status": "success",
                "answer": result["answer"],
                "source_documents": result["source_documents"],
                "query": request.message,
            }
        
        # Generate answer using LLM
        history = conversation_history or []
        answer = LLMEngine.chat(
            result["user_query"],
            history,
            result["top_context"],
            max_words=150,
            allowed_filenames=result["allowed_names"],
            focus_filenames=result["focus_filenames"],
        )
        
        # Sanitize citations: if allowed list empty, strip all; else keep only allowed
        if answer:
            import re
            if result["allowed_names"]:
                allowed_set = set(result["allowed_names"])
                def repl(m):
                    token = m.group(1).strip()
                    return f"[{token}]" if token in allowed_set else ""
                answer = re.sub(r"\[(.*?)\]", repl, answer)
            else:
                answer = re.sub(r"\[(.*?)\]", "", answer)
        
        # Add missing files warning if applicable
        if result["missing_filenames"] and result["focus_filenames"]:
            missing_list = ", ".join(sorted(set(result["missing_filenames"])))
            answer += (
                "\n\n⚠️ I couldn't locate the following requested file(s): "
                f"{missing_list}."
            )
        
        return {
            "status": "success",
            "answer": answer,
            "source_documents": result["source_documents"],
            "query": request.message,
        }
        
    except Exception as e:
        logger.error(f"Failed to process chat query, error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.post("/query/stream")
async def chat_query_stream(
    request: ChatRequest,
    vector_store: VectorStore = Depends(get_vector_store)
):
    """Stream a chat response token-by-token using Server-Sent Events (SSE)."""
    try:
        # Convert Pydantic models to dict
        conversation_history = None
        if request.conversation_history:
            conversation_history = [
                {"role": msg.role, "content": msg.content}
                for msg in request.conversation_history
            ]
        
        # Process request using shared logic
        result = _process_chat_request(request.message, conversation_history, vector_store)
        
        # Handle non-LLM responses (inventory, capabilities, errors, greetings)
        if not result["requires_llm"]:
            def simple_stream():
                yield f"data: {result['answer']}\n\n"
            return StreamingResponse(simple_stream(), media_type="text/event-stream")
        
        # Stream LLM response
        history = conversation_history or []
        
        def event_stream():
            # Wrap OpenAI stream as SSE data events
            for token in Streaming.chat_stream(
                result["user_query"],
                history,
                result["top_context"],
                focus_filenames=result["focus_filenames"],
            ):
                yield f"data: {token}\n\n"
            
            # Add missing files warning if applicable
            if result["missing_filenames"] and result["focus_filenames"]:
                missing_list = ", ".join(sorted(set(result["missing_filenames"])))
                yield (
                    "data: "
                    "\n\n⚠️ I couldn't locate the following requested file(s): "
                    f"{missing_list}."
                    "\n\n"
                )
        
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
async def get_conversation_starters(
    vector_store: VectorStore = Depends(get_vector_store)
) -> Dict[str, Any]:
    """
    Get conversation starter prompts based on available documents.
    """
    try:
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
