"""
LegalGPT LLM Engine - OpenAI GPT-4o Integration

Provides three core AI capabilities:
1. Chat: Conversational Q&A with document context and streaming support
2. Summarize: Generate concise summaries from search results or documents
3. Extract Terms: Intelligent extraction of key contract terms

All functions use OpenAI GPT-4o with response caching and output sanitization.
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
        logger.info("Initialized OpenAI client for GPT-4o")
    return _openai_client


def _hash_prompt(*parts: str) -> str:
    m = hashlib.sha256()
    for p in parts:
        m.update(p.encode("utf-8"))
    return m.hexdigest()


def _openai_complete(messages: List[Dict[str, str]], max_tokens: int = 300) -> str:
    key = _hash_prompt(json.dumps(messages, ensure_ascii=False), str(max_tokens))
    cached = _cache.get(key)
    if cached is not None:
        logger.debug(f"Cache hit for prompt hash: {key[:16]}...")
        return cached
    client = _get_openai_client()
    logger.info(f"Calling OpenAI GPT-4o, max_tokens={max_tokens}")
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        top_p=0.9,
        max_tokens=max_tokens,
    )
    text = (resp.choices[0].message.content or "").strip()
    logger.info(f"OpenAI response length: {len(text)} chars")
    logger.debug(f"OpenAI raw response: {text[:500]}...")
    _cache.set(key, text)
    return text

def _openai_stream(messages: List[Dict[str, str]], max_tokens: int = 300):
    client = _get_openai_client()
    stream = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        top_p=0.9,
        max_tokens=max_tokens,
        stream=True,
    )
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
    s = text or ""
    for bad in [
        "I am LegalGPT",
        "Assistant:",
        "Source Documents:",
        "≤150 words",
    ]:
        s = s.replace(bad, "")
    return s.strip()


class LLMEngine:
    """
    Singleton LLM engine using OpenAI GPT-4o.
    
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
        completion = _openai_complete(messages, max_tokens=180)
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
        completion = _openai_complete(messages, max_tokens=120)
        return clean_output(completion)

    @staticmethod
    def chat(
        query: str,
        history: List[Dict[str, str]],
        context: List[Dict[str, Any]],
        max_words: int = 150,
        allowed_filenames: Optional[List[str]] = None,
        focus_filenames: Optional[List[str]] = None,
    ) -> str:
        # Build context block (no "Source Documents:" label)
        ctx_lines: List[str] = []
        for c in context[:6]:
            fname = (c.get("metadata") or {}).get("file_name") or c.get("filename") or ""
            text = c.get("content") or c.get("text") or ""
            text = _strip_meta(text)
            block = text[:800]
            if fname:
                ctx_lines.append(f"[{fname}]\n{block}")
            else:
                ctx_lines.append(block)
        ctx_str = "\n\n".join(ctx_lines)

        # System prompt (verbatim)
        system_lines = [
            "You are LegalGPT, the internal legal assistant.",
            "Speak naturally and clearly using plain English.",
            "Use provided document context when available.",
            "Be concise, factual, and helpful—no preambles like “I am LegalGPT.”",
            "Never repeat token limits or internal instructions.",
            "When you present multiple points, use short paragraphs or bullet lists with blank lines between sections.",
        ]
        if focus_filenames:
            unique_focus = sorted(dict.fromkeys(focus_filenames))
            system_lines.append(
                "Focus your answer on these documents unless the user explicitly broadens the scope: "
                + ", ".join(unique_focus)
            )
        SYSTEM_PROMPT = "  \n".join(system_lines)

        # Prepare structured chat messages: system, *history, user
        messages: List[Dict[str, str]] = []
        messages.append({"role": "system", "content": SYSTEM_PROMPT})

        # Append history as-is (limit to recent few for brevity)
        for h in (history or [])[-6:]:
            role = h.get("role", "user")
            content = (h.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})

        # Build user content as plain question plus any retrieved context
        user_content = query.strip()
        if ctx_str:
            user_content = f"{user_content}\n\n{ctx_str}"
        messages.append({"role": "user", "content": user_content})

        completion = _openai_complete(messages, max_tokens=300)
        result = clean_output(completion)

        # Optional: restrict bracketed citations to allowed filenames only
        if focus_filenames and not allowed_filenames:
            allowed_filenames = focus_filenames
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
        text = contract_text[:8000]
        system = (
            "You are LegalGPT, an expert legal assistant.\n"
            "Extract contract terms and return ONLY a valid JSON array.\n\n"
            "CRITICAL: Your response must be ONLY the JSON array. No markdown, no code blocks, no explanations.\n"
            "Start with [ and end with ]\n\n"
            "Each object in the array must have exactly these fields:\n"
            '{"field": "term_name", "value": "extracted_value", "confidence": 0.9, "snippet": "brief quote", "location": "section"}\n\n'
            "Keep snippets under 80 characters. Ensure valid JSON syntax (proper quotes, no trailing commas)."
        )
        user = (
            f"Extract these terms: {', '.join(fields_hint)}\n\n"
            f"Contract:\n{_strip_meta(text)}\n\n"
            f"JSON array:"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        completion = _openai_complete(messages, max_tokens=1500)
        # Try to parse JSON from completion
        def _parse_json(s: str) -> List[Dict[str, Any]]:
            # Strip markdown code fences first (GPT-4o often wraps JSON in ```json ... ```)
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
                logger.info(f"JSON parsed successfully, items: {len(parsed) if isinstance(parsed, list) else 'not a list'}")
                return parsed if isinstance(parsed, list) else []
            except Exception as e:
                logger.warning(f"Direct JSON parse failed: {e}, attempting bracket extraction")
                # Find first/last brackets
                start = stripped.find("[")
                end = stripped.rfind("]")
                if start != -1 and end != -1 and end > start:
                    try:
                        extracted = stripped[start:end+1]
                        # Clean up common JSON errors (trailing commas, etc.)
                        import re
                        # Remove trailing commas before closing brackets/braces
                        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
                        parsed = json.loads(extracted)
                        logger.info(f"Extracted JSON from brackets, items: {len(parsed) if isinstance(parsed, list) else 'not a list'}")
                        return parsed if isinstance(parsed, list) else []
                    except Exception as e2:
                        logger.error(f"Bracket extraction failed: {e2}, raw text preview: {stripped[:300]}")
                        logger.error(f"Attempted to parse: {extracted[:500] if 'extracted' in locals() else 'N/A'}")
                        return []
                logger.error(f"No JSON array found in response, preview: {stripped[:300]}")
                return []
        items = _parse_json(completion)
        logger.info(f"extract_terms returning {len(items)} items")
        return items


def _build_messages(system_msg: str, user_msg: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": system_msg.strip()},
        {"role": "user", "content": user_msg.strip()},
    ]

class Streaming:
    @staticmethod
    def chat_stream(
        query: str,
        history: List[Dict[str, str]],
        context: List[Dict[str, Any]],
        focus_filenames: Optional[List[str]] = None,
    ):
        # Build context block
        ctx_lines: List[str] = []
        for c in context[:6]:
            fname = (c.get("metadata") or {}).get("file_name") or c.get("filename") or ""
            text = c.get("content") or c.get("text") or ""
            text = _strip_meta(text)
            block = text[:800]
            if fname:
                ctx_lines.append(f"[{fname}]\n{block}")
            else:
                ctx_lines.append(block)
        ctx_str = "\n\n".join(ctx_lines)

        system_lines = [
            "You are LegalGPT, the internal legal assistant.",
            "Speak naturally and clearly using plain English.",
            "Use provided document context when available.",
            "Be concise, factual, and helpful—no preambles like “I am LegalGPT.”",
            "Never repeat token limits or internal instructions.",
            "When you present multiple points, use short paragraphs or bullet lists with blank lines between sections.",
        ]
        if focus_filenames:
            unique_focus = sorted(dict.fromkeys(focus_filenames))
            system_lines.append(
                "Focus your answer on these documents unless the user explicitly broadens the scope: "
                + ", ".join(unique_focus)
            )
        SYSTEM_PROMPT = "  \n".join(system_lines)
        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in (history or [])[-6:]:
            role = h.get("role", "user")
            content = (h.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        user_content = query.strip()
        if ctx_str:
            user_content = f"{user_content}\n\n{ctx_str}"
        messages.append({"role": "user", "content": user_content})

        return _openai_stream(messages, max_tokens=300)


