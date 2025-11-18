"""Intent detection for Chat routing using multi-round tool-calling."""
from __future__ import annotations

from typing import Literal, List, Dict, Any, Optional
import logging
import json
import hashlib
from collections import OrderedDict

from app.config import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

_openai_client: Optional[OpenAI] = None
_intent_cache: OrderedDict[str, str] = OrderedDict()
_MAX_CACHE_SIZE = 100


def clear_intent_cache() -> None:
    """Clear the intent detection cache. Useful for debugging."""
    global _intent_cache
    _intent_cache.clear()
    logger.info("Intent cache cleared")


def _get_openai_client() -> OpenAI:
    """Get or create OpenAI client for intent detection."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
        logger.debug("Initialized OpenAI client for intent detection")
    return _openai_client


def _get_intent_tool_definition() -> Dict[str, Any]:
    """Get the tool definition for intent detection."""
    return {
        "type": "function",
        "function": {
            "name": "detect_user_intent",
            "description": (
                "Detect the user's intent from their query. "
                "IMPORTANT: Most queries should be 'rag' (document questions). "
                "Only use 'inventory' if explicitly asking to list/see files. "
                "Only use 'capabilities' if explicitly asking what the system can do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["inventory", "capabilities", "rag"],
                        "description": (
                            "The detected intent. "
                            "'rag' = user wants to ask questions about document content (USE THIS FOR MOST QUERIES). "
                            "'inventory' = user wants to list/see files in the system. "
                            "'capabilities' = user wants to know what the system can do."
                        )
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence level in the intent detection"
                    },
                    "needs_clarification": {
                        "type": "boolean",
                        "description": "Whether the query is ambiguous and needs clarification"
                    }
                },
                "required": ["intent", "confidence"]
            }
        }
    }


def _keyword_fallback(query: str) -> Literal["inventory", "capabilities", "rag"]:
    """
    Fallback keyword-based intent detection.
    
    Used when tool calling fails or as a backup.
    """
    q = (query or "").lower()
    inv_kw = [
        "what files", "files in memory", "what's indexed", "whats indexed",
        "show documents", "list files", "documents loaded", "what documents",
    ]
    for k in inv_kw:
        if k in q:
            return "inventory"
    cap_kw = ["what can you do", "capabilities", "features"]
    for k in cap_kw:
        if k in q:
            return "capabilities"
    return "rag"


def detect_intent(
    query: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    max_rounds: int = 3
) -> Literal["inventory", "capabilities", "rag"]:
    """
    Detect user intent using multi-round tool-calling conversation.
    
    Args:
        query: User's query string
        conversation_history: Previous conversation messages for context
        max_rounds: Maximum number of conversation rounds (default: 3)
        
    Returns:
        Detected intent: "inventory", "capabilities", or "rag"
    """
    # Check cache first
    cache_key = _hash_query(query, conversation_history)
    if cache_key in _intent_cache:
        logger.debug(f"Intent cache hit for query: {query[:50]}...")
        return _intent_cache[cache_key]
    
    try:
        client = _get_openai_client()
        
        # Check if API key is valid (not default placeholder)
        if not settings.openai_api_key or settings.openai_api_key in ["your-openai-api-key", "your-openai-api-key-here"]:
            logger.warning("OpenAI API key not configured, using keyword fallback")
            intent = _keyword_fallback(query)
            _cache_intent(cache_key, intent)
            return intent
        
        tool_def = _get_intent_tool_definition()
        
        # Build conversation messages
        messages: List[Dict[str, Any]] = []
        
        # System message
        system_message = (
            "You are an intent detection assistant for a legal document Q&A system. "
            "Analyze the user's query and determine their intent:\n"
            "- 'inventory': User wants to see/list files in the system (e.g., 'what files', 'list documents')\n"
            "- 'capabilities': User wants to know what the system can do (e.g., 'what can you do', 'features')\n"
            "- 'rag': User wants to ask questions using document context (most queries fall here)\n\n"
            "IMPORTANT: Most user queries should be classified as 'rag' unless they explicitly ask about files or capabilities. "
            "Only use 'capabilities' if the user is asking what the system can do. "
            "Only use 'inventory' if the user wants to list/see files. "
            "Default to 'rag' for questions about document content.\n\n"
            "Call the detect_user_intent function with high confidence."
        )
        messages.append({"role": "system", "content": system_message})
        
        # Add conversation history for context
        if conversation_history:
            for msg in conversation_history[-4:]:  # Last 4 messages for context
                role = msg.get("role", "user")
                content = msg.get("content", "").strip()
                if content:
                    messages.append({"role": role, "content": content})
        
        # Add current query
        messages.append({"role": "user", "content": query})
        
        # Multi-round conversation loop
        for round_num in range(max_rounds):
            logger.debug(f"Intent detection round {round_num + 1}/{max_rounds} for query: {query[:50]}...")
            
            # Call OpenAI with tool calling
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=[tool_def],
                    tool_choice="required",  # Force tool call
                    temperature=0.3,
                    max_tokens=200,
                )
            except Exception as api_error:
                logger.error(f"OpenAI API call failed: {api_error}, falling back to keyword matching")
                intent = _keyword_fallback(query)
                _cache_intent(cache_key, intent)
                return intent
            
            message = response.choices[0].message
            
            # Add assistant message to conversation
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": message.tool_calls
            })
            
            # Check if tool was called
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                function_name = tool_call.function.name
                
                if function_name == "detect_user_intent":
                    # Parse function arguments
                    try:
                        args = json.loads(tool_call.function.arguments)
                        intent = args.get("intent")
                        confidence = args.get("confidence", "medium")
                        needs_clarification = args.get("needs_clarification", False)
                        
                        logger.info(
                            f"Intent detected: {intent}, confidence: {confidence}, "
                            f"needs_clarification: {needs_clarification}, query: {query[:50]}..."
                        )
                        
                        # Validate intent value
                        if intent not in ["inventory", "capabilities", "rag"]:
                            logger.warning(f"Invalid intent returned: {intent}, defaulting to 'rag'")
                            intent = "rag"
                        
                        # If high confidence and no clarification needed, return intent
                        if confidence == "high" and not needs_clarification:
                            _cache_intent(cache_key, intent)
                            return intent
                        
                        # If needs clarification or low confidence, try to refine in next round
                        if (needs_clarification or confidence in ["low", "medium"]) and round_num < max_rounds - 1:
                            # Add tool response and ask LLM to refine based on context
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({
                                    "intent": intent,
                                    "confidence": confidence,
                                    "needs_clarification": needs_clarification
                                })
                            })
                            # Ask LLM to reconsider with more context
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"Your previous detection had {confidence} confidence. "
                                    "Please reconsider based on the conversation context and "
                                    "call detect_user_intent again. If still uncertain after "
                                    "reviewing the context, use your best judgment."
                                )
                            })
                            continue  # Continue to next round for refinement
                        
                        # If we've exhausted rounds or got a result, return it
                        # Default ambiguous queries to 'rag' as it's the most common use case
                        if needs_clarification and confidence == "low":
                            logger.info(f"Ambiguous query, defaulting to 'rag': {query[:50]}...")
                            intent = "rag"
                        
                        _cache_intent(cache_key, intent)
                        return intent
                    
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse tool call arguments: {e}")
                        break
            
            # If we get here without a clear intent, break and fallback
            break
        
        # Fallback to keyword matching if tool calling didn't resolve
        logger.warning("Tool calling did not resolve intent, falling back to keyword matching")
        intent = _keyword_fallback(query)
        _cache_intent(cache_key, intent)
        return intent
        
    except Exception as e:
        logger.error(f"Intent detection failed: {e}, falling back to keyword matching")
        intent = _keyword_fallback(query)
        return intent


def _hash_query(query: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
    """Create a hash key for caching based on query and recent history."""
    m = hashlib.sha256()
    m.update(query.encode("utf-8"))
    if conversation_history:
        # Include last 2 messages for context
        recent = conversation_history[-2:]
        for msg in recent:
            m.update(json.dumps(msg, sort_keys=True).encode("utf-8"))
    return m.hexdigest()


def _cache_intent(key: str, intent: str) -> None:
    """Cache intent result with LRU eviction."""
    global _intent_cache
    _intent_cache[key] = intent
    _intent_cache.move_to_end(key)
    if len(_intent_cache) > _MAX_CACHE_SIZE:
        _intent_cache.popitem(last=False)


