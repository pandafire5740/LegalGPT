"""
LegalGPT LLM Engine - OpenAI GPT-5 Integration

Provides three core AI capabilities:
1. Chat: Conversational Q&A with document context and streaming support
2. Summarize: Generate concise summaries from search results or documents
3. Extract Terms: Intelligent extraction of key contract terms

All functions use OpenAI GPT-5 with response caching and output sanitization.
Streaming support available for real-time token delivery.
"""
from __future__ import annotations

import json
import hashlib
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import logging
from app.config import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

_openai_client: Optional[OpenAI] = None


class _LRUCache:
    def __init__(self, capacity: int = 64):
        self.capacity = capacity
        self.store: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> Optional[str]:
        if key in self.store:
            self.store.move_to_end(key)
            return self.store[key]
        return None

    def set(self, key: str, value: str) -> None:
        self.store[key] = value
        self.store.move_to_end(key)
        if len(self.store) > self.capacity:
            self.store.popitem(last=False)


_cache = _LRUCache(64)


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
        logger.info("Initialized OpenAI client for GPT-5")
    return _openai_client


def _hash_prompt(*parts: str) -> str:
    m = hashlib.sha256()
    for p in parts:
        m.update(p.encode("utf-8"))
    return m.hexdigest()


def _openai_complete(messages: List[Dict[str, str]], max_tokens: int = 500) -> str:
    key = _hash_prompt(json.dumps(messages, ensure_ascii=False), str(max_tokens))
    cached = _cache.get(key)
    if cached is not None:
        logger.debug(f"Cache hit for prompt hash: {key[:16]}...")
        return cached
    client = _get_openai_client()
    logger.info(f"Calling OpenAI GPT-5, max_completion_tokens={max_tokens}")
    try:
        resp = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            max_completion_tokens=max_tokens,
        )
        raw_content = resp.choices[0].message.content or ""
        
        # Log full response details for debugging
        finish_reason = resp.choices[0].finish_reason if resp.choices else "unknown"
        usage_info = resp.usage.model_dump() if hasattr(resp, 'usage') and resp.usage else None
        
        logger.info(f"OpenAI API response - finish_reason: {finish_reason}, "
                   f"usage: {usage_info}, content_length: {len(raw_content)}")
        
        if not raw_content:
            logger.error(f"OpenAI returned empty content! finish_reason: {finish_reason}, usage: {usage_info}")
            if finish_reason == "length":
                logger.error("Response was truncated due to max_completion_tokens limit. Consider increasing max_tokens.")
            elif finish_reason == "content_filter":
                logger.error("Response was filtered by content filter.")
            else:
                logger.error(f"Unknown finish_reason: {finish_reason}. Full response object available in logs.")
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}", exc_info=True)
        raise
    
    # DEBUG: Log raw content from OpenAI before any processing
    debug_msg = f"""
{'=' * 80}
LLM RAW (from OpenAI, before .strip()):
{'=' * 80}
JSON.stringify equivalent: {json.dumps(raw_content)}
Length: {len(raw_content)} chars
Lines (split by \\n): {len(raw_content.split(chr(10)))}
First 500 chars: {repr(raw_content[:500])}
{'=' * 80}
"""
    logger.info(debug_msg)
    print(debug_msg)  # Also print to stdout for visibility
    
    text = raw_content.strip()  # Only strip leading/trailing whitespace
    
    logger.info(f"After .strip() - Length: {len(text)} chars, Lines: {len(text.split(chr(10)))}")
    logger.info(f"OpenAI response preview: {text[:500]}...")
    _cache.set(key, text)
    return text


def _openai_complete_with_json_mode(messages: List[Dict[str, str]], max_tokens: int = 2000) -> str:
    """
    Complete with JSON mode enabled to ensure structured output.
    Falls back to regular completion if JSON mode fails.
    """
    key = _hash_prompt(json.dumps(messages, ensure_ascii=False), f"{max_tokens}_json")
    cached = _cache.get(key)
    if cached is not None:
        logger.debug(f"Cache hit for JSON mode prompt hash: {key[:16]}...")
        return cached
    
    client = _get_openai_client()
    logger.info(f"Calling OpenAI GPT-5 with JSON mode, max_completion_tokens={max_tokens}")
    
    try:
        # Try with JSON mode first
        resp = client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            max_completion_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        raw_content = resp.choices[0].message.content or ""
        finish_reason = resp.choices[0].finish_reason if resp.choices else "unknown"
        usage_info = resp.usage.model_dump() if hasattr(resp, 'usage') and resp.usage else None
        
        logger.info(f"JSON mode response - finish_reason: {finish_reason}, usage: {usage_info}, content_length: {len(raw_content)}")
        
        if raw_content:
            text = raw_content.strip()
            _cache.set(key, text)
            return text
        else:
            logger.warning("JSON mode returned empty content, falling back to regular mode")
    except Exception as e:
        logger.warning(f"JSON mode failed: {e}, falling back to regular mode")
    
    # Fallback to regular completion
    return _openai_complete(messages, max_tokens=max_tokens)


def _openai_stream(messages: List[Dict[str, str]], max_tokens: Optional[int] = None):
    client = _get_openai_client()
    params = {
        "model": "gpt-5",
        "messages": messages,
        "stream": True,
    }
    # Only set max_completion_tokens if specified (None means no limit)
    if max_tokens is not None:
        params["max_completion_tokens"] = max_tokens
    stream = client.chat.completions.create(**params)
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and getattr(delta, "content", None):
            yield delta.content


def _trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;-") + "."


def _sanitize(text: str, max_words: int) -> str:
    # Remove echoed sections and roles
    lines = text.splitlines()
    # Drop lines that look like roles or headings
    filtered = []
    for ln in lines:
        low = ln.strip().lower()
        if low.startswith("user:") or low.startswith("assistant:") or low.startswith("history:") or low.startswith("context:"):
            continue
        filtered.append(ln)
    s = " ".join(l.strip() for l in filtered)
    # Remove any inline role labels
    import re
    s = re.sub(r"\b(?:User|Assistant|History|Context)\s*:\s*", "", s, flags=re.IGNORECASE)
    # Collapse spaces
    while "  " in s:
        s = s.replace("  ", " ")
    # Trim to max words
    s = _trim_words(s, max_words)
    return s.strip()


def _strip_meta(text: str) -> str:
    """Remove obvious metadata markers to avoid seeding the model with them."""
    import re
    lines = []
    for ln in text.splitlines():
        low = ln.strip().lower()
        if low.startswith(("user:", "assistant:", "history:", "context:", "system:")):
            continue
        lines.append(ln)
    s = "\n".join(lines)
    s = re.sub(r"\b(?:User|Assistant|History|Context|System)\s*:\s*", "", s, flags=re.IGNORECASE)
    return s


def clean_output(text: str) -> str:
    # DEBUG: Log input to clean_output
    logger.info(f"clean_output INPUT - Length: {len(text)} chars, Lines: {len(text.split(chr(10)))}")
    logger.info(f"clean_output INPUT - First 200 chars: {repr(text[:200])}")
    
    s = text or ""
    for bad in [
        "I am LegalGPT",
        "Assistant:",
        "Source Documents:",
        "≤150 words",
    ]:
        s = s.replace(bad, "")
    
    result = s.strip()  # Only strip leading/trailing whitespace
    
    # DEBUG: Log output from clean_output
    logger.info(f"clean_output OUTPUT - Length: {len(result)} chars, Lines: {len(result.split(chr(10)))}")
    logger.info(f"clean_output OUTPUT - First 200 chars: {repr(result[:200])}")
    
    return result


class LLMEngine:
    """
    Singleton LLM engine using OpenAI GPT-5.
    
    All methods are static and use shared OpenAI client with caching.
    """
    
    @staticmethod
    def summarize(query: str, chunks: List[Dict[str, Any]], max_words: int = 75) -> str:
        """
        Generate a concise summary from retrieved document chunks.
        
        Args:
            query: Original search query
            chunks: List of retrieved document chunks with metadata
            max_words: Maximum words in summary (default: 75)
            
        Returns:
            Clean summary text with filename citations where appropriate
        """
        if not chunks:
            return "No relevant content found."
        context_lines = []
        for c in chunks[:8]:
            fname = (c.get("metadata") or {}).get("file_name") or c.get("filename") or "Unknown"
            text = c.get("content") or c.get("text") or ""
            text = _strip_meta(text)
            context_lines.append(f"[File: {fname}]\n{text[:800]}")
        context = "\n\n".join(context_lines)
        system = (
            "You are LegalGPT, the internal legal assistant.\n"
            "Speak naturally and clearly using plain English.\n"
            "Use provided document context when available.\n"
            "Be concise, factual, and helpful.\n"
        )
        user = f"Question: {query}\n\nContext:\n{context}\n\nProvide a short summary."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        completion = _openai_complete(messages, max_tokens=400)
        # Allow only citations present in chunks
        allowed = []
        for c in chunks:
            md = c.get("metadata") or {}
            fn = md.get("file_name")
            if fn:
                allowed.append(fn)
        result = clean_output(completion)
        if allowed:
            import re
            allowed_set = set(allowed)
            def repl(m):
                token = m.group(1).strip()
                return f"[{token}]" if token in allowed_set else ""
            result = re.sub(r"\[(.*?)\]", repl, result)
        else:
            import re
            result = re.sub(r"\[(.*?)\]", "", result)
        return result

    @staticmethod
    def summarize_text(filename: str, text: str, max_words: int = 50) -> str:
        snippet = _strip_meta(text[:1500])
        system = (
            "You are LegalGPT, the internal legal assistant.\n"
            "Speak naturally and clearly using plain English.\n"
            "Be concise."
        )
        user = f"Filename: {filename}\n\nText:\n{snippet}\n\nProvide a short summary."
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        completion = _openai_complete(messages, max_tokens=300)
        return clean_output(completion)

    @staticmethod
    def summarize_file_keyword_context(filename: str, keyword: str, chunks: List[Dict[str, Any]], max_words: int = 40) -> str:
        """
        Generate a specific, informative AI summary of a document's relevance to a query.
        
        Args:
            filename: Name of the file
            keyword: The search keyword/query term
            chunks: List of relevant chunks from the file (with 'content' and 'metadata')
            max_words: Maximum words in summary (default: 40)
            
        Returns:
            Clean, specific summary text (e.g., "This is the 2024 Master Services Agreement between X and Y containing scope, term, termination, and governing law provisions.")
        """
        if not chunks:
            return f"No relevant content found for '{keyword}' in {filename}."
        
        # Combine top chunks for context (limit to avoid token limit)
        context_lines = []
        for c in chunks[:5]:
            text = c.get("content") or c.get("text") or ""
            text = _strip_meta(text)
            context_lines.append(text[:1000])
        
        context = "\n\n".join(context_lines)
        
        system = (
            "You are LegalGPT, a legal assistant specializing in contract analysis.\n"
            "Generate specific, informative summaries that identify document type, parties, and key provisions.\n"
            "Be precise and factual. Include specific details like document type, parties (if mentioned), year (if mentioned), and key clause types."
        )
        user = (
            f"Document name: {filename}\n"
            f"Search query: {keyword}\n\n"
            f"Relevant content from this document:\n{context}\n\n"
            f"Generate a specific summary (max {max_words} words) that:\n"
            f"- Identifies the document type (e.g., 'Master Services Agreement', 'NDA', 'DPA')\n"
            f"- Mentions parties if clearly identified in the content\n"
            f"- Lists the key clause types/provisions found (e.g., 'scope, term, termination, and governing law')\n"
            f"- Explains why this document is relevant to '{keyword}'\n\n"
            f"Example format: 'This is the 2024 Master Services Agreement between Mindbody and CloudScale containing scope, term, termination, and governing law provisions.'\n"
            f"Be specific and avoid generic phrases like 'relevant content found'."
        )
        
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        
        completion = _openai_complete(messages, max_tokens=400)  # Increased tokens for more detailed summaries
        result = clean_output(completion)
        return _trim_words(result, max_words)

    @staticmethod
    def summarize_clause(clause_text: str, max_words: int = 40) -> str:
        """
        Generate a concise 1-2 sentence summary of a legal clause.
        
        Args:
            clause_text: The clause/chunk text to summarize
            max_words: Maximum words in summary (default: 40)
            
        Returns:
            Brief clause summary (1-2 sentences)
        """
        if not clause_text or not clause_text.strip():
            return ""
        
        # Use first 1000 chars to avoid token limits
        text = clause_text[:1000]
        system = (
            "You are LegalGPT, a legal assistant.\n"
            "Summarize legal clauses concisely in 1-2 sentences.\n"
            "Focus on key obligations, rights, or terms. Be specific and factual."
        )
        user = f"Clause:\n{text}\n\nProvide a brief summary (1-2 sentences, ≤{max_words} words):"
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        completion = _openai_complete(messages, max_tokens=150)
        result = clean_output(completion)
        return _trim_words(result, max_words)

    @staticmethod
    def chat(
        messages: List[Dict[str, str]],
        allowed_filenames: Optional[List[str]] = None,
    ) -> str:
        """
        Non-streaming chat - collects streamed tokens and returns full response.
        
        Args:
            messages: Pre-built list of messages (system, history, user) ready for LLM
            allowed_filenames: Optional list of allowed filenames for citation filtering
            
        Returns:
            Cleaned response text with citations filtered if needed
        """
        # Collect all tokens from stream
        full_text = ""
        for token in Streaming.chat_stream(messages):
            full_text += token
        
        # DEBUG: Log raw content from streaming before any processing
        import sys
        newline_char = '\n'
        crlf = '\r\n'
        has_newline = newline_char in full_text
        has_crlf = crlf in full_text
        debug_msg = f"""
{'=' * 80}
LLM RAW (from LLMEngine.chat, before clean_output):
{'=' * 80}
JSON.stringify equivalent: {json.dumps(full_text)}
Length: {len(full_text)} chars
Lines (split by \\n): {len(full_text.split(newline_char))}
First 500 chars: {repr(full_text[:500])}
Contains \\n: {has_newline}
Contains \\r\\n: {has_crlf}
{'=' * 80}
"""
        logger.info(debug_msg)
        print(debug_msg, file=sys.stderr)  # Print to stderr for visibility
        sys.stderr.flush()  # Force flush
        
        result = clean_output(full_text)
        
        # DEBUG: Log after clean_output
        debug_msg = f"""
{'=' * 80}
After clean_output():
Length: {len(result)} chars
Lines (split by \\n): {len(result.split(chr(10)))}
JSON.stringify equivalent: {json.dumps(result)}
{'=' * 80}
"""
        logger.info(debug_msg)
        print(debug_msg)  # Also print to stdout for visibility

        # Optional: restrict bracketed citations to allowed filenames only
        if allowed_filenames:
            import re
            allowed_set = set(allowed_filenames)
            def repl(m):
                token = m.group(1).strip()
                return f"[{token}]" if token in allowed_set else ""
            result = re.sub(r"\[(.*?)\]", repl, result)
        return result

    @staticmethod
    def extract_terms(contract_text: str, expected_fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        fields_hint = expected_fields or [
            "parties", "counterparty", "effective_date", "expiration_date", 
            "renewal_terms", "termination_clause", "payment_terms", 
            "governing_law", "confidentiality", "liability_cap"
        ]
        text = contract_text[:6000]  # Reduced from 8000 to speed up processing
        system = (
            "You are LegalGPT, an expert legal assistant.\n"
            "Extract contract terms and return ONLY a valid JSON object with a 'terms' array.\n\n"
            "CRITICAL: Return ONLY a JSON object. No markdown, no code blocks, no explanations.\n"
            "Format: {\"terms\": [{\"field\": \"term_name\", \"value\": \"extracted_value\", \"confidence\": 0.9, \"snippet\": \"brief quote\", \"location\": \"section\"}]}\n\n"
            "Keep snippets under 60 characters. Extract only terms that are clearly present. Ensure valid JSON syntax."
        )
        user = (
            f"Extract these terms: {', '.join(fields_hint)}\n\n"
            f"Contract:\n{_strip_meta(text)}\n\n"
            f"Return JSON object with 'terms' array. Be concise - extract only what's present."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # No token limit - let GPT-5 generate complete response
        # Use JSON mode to ensure structured output
        completion = _openai_complete_with_json_mode(messages, max_tokens=8000)
        # Try to parse JSON from completion
        def _parse_json(s: str) -> List[Dict[str, Any]]:
            # Strip markdown code fences first (GPT-5 often wraps JSON in ```json ... ```)
            stripped = s.strip()
            if stripped.startswith("```"):
                # Remove opening fence
                lines = stripped.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove closing fence
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                stripped = '\n'.join(lines).strip()
            
            try:
                parsed = json.loads(stripped)
                # Handle both formats: direct array or object with "terms" key
                if isinstance(parsed, dict) and "terms" in parsed:
                    items = parsed["terms"]
                    logger.info(f"JSON parsed successfully from object.terms, items: {len(items) if isinstance(items, list) else 'not a list'}")
                    return items if isinstance(items, list) else []
                elif isinstance(parsed, list):
                    logger.info(f"JSON parsed successfully as array, items: {len(parsed)}")
                    return parsed
                else:
                    logger.warning(f"JSON parsed but not a list or object with 'terms' key: {type(parsed)}")
                    return []
            except Exception as e:
                logger.warning(f"Direct JSON parse failed: {e}, attempting bracket extraction")
                # Try to find object with "terms" key first
                obj_start = stripped.find("{")
                obj_end = stripped.rfind("}")
                if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
                    try:
                        extracted = stripped[obj_start:obj_end+1]
                        import re
                        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
                        parsed = json.loads(extracted)
                        if isinstance(parsed, dict) and "terms" in parsed:
                            items = parsed["terms"]
                            logger.info(f"Extracted JSON object with terms, items: {len(items) if isinstance(items, list) else 'not a list'}")
                            return items if isinstance(items, list) else []
                    except Exception as e2:
                        logger.warning(f"Object extraction failed: {e2}")
                
                # Fallback: try to find array
                start = stripped.find("[")
                end = stripped.rfind("]")
                if start != -1 and end != -1 and end > start:
                    try:
                        extracted = stripped[start:end+1]
                        import re
                        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
                        parsed = json.loads(extracted)
                        logger.info(f"Extracted JSON array, items: {len(parsed) if isinstance(parsed, list) else 'not a list'}")
                        return parsed if isinstance(parsed, list) else []
                    except Exception as e2:
                        logger.error(f"Bracket extraction failed: {e2}, raw text preview: {stripped[:300]}")
                        logger.error(f"Attempted to parse: {extracted[:500] if 'extracted' in locals() else 'N/A'}")
                        return []
                logger.error(f"No JSON array or object found in response, preview: {stripped[:300]}")
                return []
        items = _parse_json(completion)
        logger.info(f"extract_terms returning {len(items)} items")
        if items:
            logger.info(f"Sample extracted term: {items[0] if items else 'N/A'}")
            logger.info(f"First 3 term fields: {[t.get('field', 'N/A') for t in items[:3]]}")
        else:
            logger.warning("extract_terms returned empty list - terms table will not populate!")
            logger.warning(f"Raw completion preview: {completion[:500]}")
        return items

    @staticmethod
    def analyze_contract_sentiment(
        contract_text: str,
        extracted_terms: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze contract sentiment to determine if it's good to sign as-is.
        
        Returns a dictionary with:
        - score: 0-100 (higher is better)
        - label: "Good to Sign", "Needs Review", or "High Risk"
        - explanation: Brief explanation of the score
        - concerns: List of key concerns (if any)
        - positives: List of positive aspects (if any)
        """
        # Build summary of extracted terms for analysis
        terms_summary = []
        for term in extracted_terms:
            field = term.get("field", "")
            value = term.get("value", "")
            if field and value:
                terms_summary.append(f"{field}: {value}")
        
        terms_text = "\n".join(terms_summary) if terms_summary else "No terms extracted"
        contract_snippet = _strip_meta(contract_text[:3000])  # Reduced to 3000 chars to save tokens for terms extraction
        
        system = (
            "You are LegalGPT, a legal contract analyst.\n"
            "Quickly analyze contract favorability. Return ONLY JSON:\n"
            '{"score": 75, "label": "Good to Sign", "explanation": "Brief", "concerns": ["concern"], "positives": ["positive"]}\n\n'
            "Score: 70-100=Good, 40-69=Review, 0-39=High Risk. Keep explanation under 20 words."
        )
        
        user = (
            f"Contract:\n{contract_snippet[:2000]}\n\n"
            f"Terms:\n{terms_text}\n\n"
            f"Quick analysis: score, label, brief explanation, top 2 concerns, top 2 positives."
        )
        
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        
        # Quick concise summary - no token limit needed
        completion = _openai_complete_with_json_mode(messages, max_tokens=2000)
        
        # Log the raw response for debugging
        logger.info(f"Sentiment analysis raw response (length: {len(completion)}): {repr(completion[:200])}")
        
        # Parse JSON response
        def _parse_sentiment_json(s: str) -> Dict[str, Any]:
            if not s or not s.strip():
                logger.warning("Sentiment analysis returned empty response")
                raise ValueError("Empty response from LLM")
            
            stripped = s.strip()
            # Remove markdown code fences if present
            if stripped.startswith("```"):
                lines = stripped.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                stripped = '\n'.join(lines).strip()
            
            if not stripped:
                logger.warning("Sentiment response is empty after stripping markdown")
                raise ValueError("Empty response after processing")
            
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    logger.info(f"Successfully parsed sentiment JSON: {parsed}")
                    return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"Sentiment JSON parse failed: {e}, raw content: {repr(stripped[:200])}, attempting bracket extraction")
                # Try to find JSON object
                start = stripped.find("{")
                end = stripped.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        extracted = stripped[start:end+1]
                        import re
                        # Fix trailing commas before closing braces/brackets
                        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
                        parsed = json.loads(extracted)
                        if isinstance(parsed, dict):
                            logger.info(f"Successfully parsed sentiment JSON after bracket extraction: {parsed}")
                            return parsed
                    except Exception as e2:
                        logger.error(f"Sentiment bracket extraction failed: {e2}, extracted: {repr(extracted[:200])}")
            
            # Fallback: return default response
            logger.warning(f"Failed to parse sentiment JSON, returning default. Raw response: {repr(stripped[:500])}")
            raise ValueError(f"Could not parse JSON from response: {repr(stripped[:200])}")
        
        try:
            result = _parse_sentiment_json(completion)
        except ValueError as e:
            logger.error(f"Sentiment analysis parsing failed: {e}")
            # Return default response
            result = {
                "score": 50,
                "label": "Needs Review",
                "explanation": "Unable to analyze contract automatically. Please review manually.",
                "concerns": ["Analysis unavailable"],
                "positives": []
            }
        
        # Validate and normalize score
        score = result.get("score", 50)
        if not isinstance(score, (int, float)):
            try:
                score = float(score)
            except (ValueError, TypeError):
                score = 50
        score = max(0, min(100, int(score)))  # Clamp to 0-100
        
        # Determine label if not provided or invalid
        label = result.get("label", "")
        if not label or label not in ["Good to Sign", "Needs Review", "High Risk"]:
            if score >= 70:
                label = "Good to Sign"
            elif score >= 40:
                label = "Needs Review"
            else:
                label = "High Risk"
        
        return {
            "score": score,
            "label": label,
            "explanation": result.get("explanation", "Contract analysis completed."),
            "concerns": result.get("concerns", []),
            "positives": result.get("positives", [])
        }


def _build_messages(system_msg: str, user_msg: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": system_msg.strip()},
        {"role": "user", "content": user_msg.strip()},
    ]

class Streaming:
    @staticmethod
    def chat_stream(
        messages: List[Dict[str, str]],
    ):
        """
        Stream chat response from pre-built messages.
        
        Args:
            messages: Pre-built list of messages (system, history, user) ready for LLM
            
        Yields:
            Token strings as they're generated by the LLM
        """
        # No hard limit - let the model decide length, but prompt encourages conciseness
        return _openai_stream(messages, max_tokens=None)


