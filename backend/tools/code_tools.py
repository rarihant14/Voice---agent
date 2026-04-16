"""
Code Generation Tools
Uses Groq LLM to generate code based on user's voice request.
"""

import os
import re
import logging
from datetime import datetime
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

LANGUAGE_EXTENSIONS = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "html": "html",
    "css": "css",
    "bash": "sh",
    "shell": "sh",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "go": "go",
    "rust": "rs",
    "json": "json",
    "yaml": "yaml",
    "sql": "sql",
}

CODE_SYSTEM_PROMPT = """You are an expert software engineer. Generate clean, well-commented, production-quality code.

Rules:
1. Output ONLY the code — no markdown fences, no explanations before or after
2. Include helpful inline comments
3. Add a docstring/header comment describing what the code does
4. Make the code complete and runnable
5. Follow best practices for the given language"""


def generate_code(prompt: str, language: str = "python", filename: str = None, content_hint: str = None) -> dict:
    """
    Generate code using Groq LLM.
    Returns dict with: code, filename, language, error
    """
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return {
            "code": "# Error: GROQ_API_KEY not set\n# Please configure your .env file\n",
            "filename": filename or "error.py",
            "language": language,
            "error": "GROQ_API_KEY not configured",
        }

    # Detect language from prompt if not explicitly set
    detected_lang = _detect_language(prompt) or language or "python"
    ext = LANGUAGE_EXTENSIONS.get(detected_lang.lower(), "py")

    # Determine filename
    if not filename:
        filename = _extract_filename(prompt) or f"generated_{_timestamp()}.{ext}"
    elif "." not in filename:
        filename = f"{filename}.{ext}"

    try:
        llm = ChatGroq(
            api_key=groq_key,
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_tokens=2048,
        )
        messages = [
            SystemMessage(content=CODE_SYSTEM_PROMPT),
            HumanMessage(content=f"Generate {detected_lang} code for: {prompt}"),
        ]
        response = llm.invoke(messages)
        code = _clean_code(response.content, detected_lang)

        return {
            "code": code,
            "filename": filename,
            "language": detected_lang,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Code generation error: {e}")
        return {
            "code": f"# Code generation failed\n# Error: {e}\n",
            "filename": filename,
            "language": detected_lang,
            "error": str(e),
        }


def _clean_code(raw: str, language: str) -> str:
    """Strip markdown fences if LLM included them."""
    raw = raw.strip()
    # Remove ```python ... ``` or ``` ... ```
    patterns = [
        rf"```{language}\n?(.*?)```",
        r"```\w*\n?(.*?)```",
    ]
    for pat in patterns:
        match = re.search(pat, raw, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return raw


def _detect_language(text: str) -> str:
    """Detect programming language from text."""
    text_lower = text.lower()
    for lang in LANGUAGE_EXTENSIONS:
        if lang in text_lower:
            return lang
    return "python"  # default


def _extract_filename(text: str) -> str:
    """Extract filename from code request."""
    patterns = [
        r"(?:called|named|save\s+(?:it\s+)?(?:as|to))\s+([\w\-\.]+\.\w+)",
        r"(?:file|script)\s+([\w\-]+)",
        r"([\w\-]+\.(py|js|ts|sh|html|java|go|rs))",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            name = match.group(1)
            if "." not in name:
                return None
            return name
    return None


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
