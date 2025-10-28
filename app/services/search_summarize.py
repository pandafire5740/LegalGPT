"""
AI-powered summarization of search results using a single open-source model (Phi-3-mini).
Falls back to simple file listing if model isn't available.
"""
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Lazy-loaded globals
_tokenizer = None
_model = None
_pipeline = None

def _get_summary_pipeline():
    """
    Get or create the text generation pipeline.
    Single standardized model: microsoft/Phi-3-mini-4k-instruct
    """
    global _tokenizer, _model, _pipeline
    
    if _pipeline is not None:
        return _pipeline
    
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
        import torch
        
        model_name = "microsoft/Phi-3-mini-4k-instruct"
        logger.info(f"Loading summary model: {model_name}")
        
        _tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        if _tokenizer.pad_token is None and _tokenizer.eos_token is not None:
            _tokenizer.pad_token = _tokenizer.eos_token
        _tokenizer.padding_side = "left"
        
        requested_dtype = torch.float32 if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()) else "auto"
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=requested_dtype,
            device_map="auto",
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            local_files_only=True
        )
        if hasattr(_model, "config"):
            try:
                _model.config.use_cache = False
            except Exception:
                pass
        if hasattr(_model, "generation_config"):
            try:
                _model.generation_config.use_cache = False
            except Exception:
                pass
        
        _pipeline = pipeline(
            "text-generation",
            model=_model,
            tokenizer=_tokenizer,
            max_new_tokens=90,
            temperature=0.2,
            do_sample=False,
            pad_token_id=_tokenizer.eos_token_id if _tokenizer.eos_token_id else _tokenizer.pad_token_id
        )
        
        logger.info(f"Summary model loaded successfully: {model_name}")
        return _pipeline
        
    except Exception as e:
        logger.error(f"Failed to load summary model: {e}")
        logger.info("Summaries will use fallback (file listing)")
        return None

SYSTEM_PROMPT = """You summarize legal search results for internal users.
2–3 sentences total, MAX 50 words. No legal advice. Do not invent facts."""

def generate_summary(query: str, search_results: List[Dict[str, Any]]) -> str:
    """
    Generate a brief AI summary of search results.
    Takes top 3 file groups and generates a 2-3 sentence summary (≤50 words).
    """
    if not search_results:
        return "No matching results found."
    
    pipeline = _get_summary_pipeline()
    
    if pipeline is None:
        # Fallback: simple file listing
        logger.info("Using fallback summary (model not available)")
        file_count = len(search_results)
        filenames = [r.get("filename", r.get("title", "Document")) for r in search_results[:3]]
        if file_count == 1:
            return f"Found 1 document: {filenames[0]}"
        elif file_count <= 3:
            return f"Found {file_count} documents: {', '.join(filenames)}"
        else:
            return f"Found {file_count} documents matching your query, including: {', '.join(filenames)} and {file_count - 3} more."
    
    # Build prompt from top 3 groups
    top_groups = search_results[:3]
    bullets = []
    
    for g in top_groups:
        filename = g.get("filename", g.get("title", "Document"))
        snippets = g.get("snippets", [])
        best_snippet = snippets[0]["text"] if snippets else ""
        # Remove bold markers for LLM
        best_snippet = best_snippet.replace("**", "")
        bullets.append(f"- {filename}: {best_snippet[:200]}")
    
    results_text = "\n".join(bullets)
    
    prompt = f"""{SYSTEM_PROMPT}

User query: {query}

Results:
{results_text}

Summary:"""
    
    try:
        logger.info("Generating AI summary...")
        output = pipeline(prompt, max_new_tokens=90)[0]["generated_text"]
        
        # Extract only the summary part (after "Summary:")
        if "Summary:" in output:
            summary = output.split("Summary:")[-1].strip()
        else:
            summary = output.strip()
        
        # Ensure it's not too long (word count check)
        words = summary.split()
        if len(words) > 50:
            summary = " ".join(words[:50]) + "..."
        
        logger.info(f"Generated summary ({len(words)} words)")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        file_count = len(search_results)
        return f"Found {file_count} relevant document{'s' if file_count != 1 else ''} matching your query."
