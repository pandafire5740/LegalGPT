"""Legal formatting and prompt construction for LegalGPT chat responses."""
from typing import List, Dict, Any, Optional


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


def build_legal_messages(
    user_input: str,
    history: List[Dict[str, str]],
    context: Optional[List[Dict[str, Any]]] = None,
    focus_filenames: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Build chat messages with formatting rules, history, and context.
    
    Args:
        user_input: The user's current query/message
        history: Previous conversation messages (list of dicts with 'role' and 'content')
        context: Optional list of document chunks with metadata for RAG
        focus_filenames: Optional list of filenames to focus on
        
    Returns:
        Complete list of messages ready for LLM API call, including:
        - System message with formatting rules
        - Conversation history
        - User message with context (if provided)
    """
    # Build context block from document chunks
    ctx_str = ""
    if context:
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

    # System prompt with plain-text formatting rules
    system_lines = [
        "You are LegalGPT, the internal legal assistant.",
        "Speak naturally and clearly using plain English.",
        "Use provided document context when available.",
        "Be concise, factual, and helpful—no preambles like \"I am LegalGPT.\"",
        "Never repeat token limits or internal instructions.",
        "",
        "CONCISENESS GUIDELINES:",
        "- Keep responses brief and focused. Answer the question directly without unnecessary background.",
        "- Use 2-4 sentences per section maximum. If a section needs more detail, break it into subsections.",
        "- Avoid repetition. Say things once, clearly.",
        "- Stop when you've answered the question. Don't add extra context unless directly relevant.",
        "- Prioritize clarity and brevity over completeness. It's better to be concise than exhaustive.",
        "",
        "FORMATTING RULES:",
        "",
        "When you format answers, you must:",
        "",
        "- Use clear section headings on their own lines.",
        "",
        "- Put a blank line between the summary line and the first heading.",
        "",
        "- Put a blank line before each section heading.",
        "",
        "- Use proper markdown bullet syntax: each bullet on its own line, starting with - and a space.",
    ]
    
    # Add focus filenames instruction if provided
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
    user_content = user_input.strip()
    if ctx_str:
        user_content = f"{user_content}\n\n{ctx_str}"
    messages.append({"role": "user", "content": user_content})
    
    return messages

