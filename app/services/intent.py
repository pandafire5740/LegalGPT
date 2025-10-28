"""Simple intent detection for Chat routing."""
from __future__ import annotations

from typing import Literal


def detect_intent(query: str) -> Literal["inventory", "capabilities", "rag"]:
    q = (query or "").lower()
    inv_kw = [
        "what files", "files in memory", "what’s indexed", "whats indexed",
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


