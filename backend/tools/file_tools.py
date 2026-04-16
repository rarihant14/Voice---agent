"""
File Tools - Safe file/folder creation restricted to output/ directory.
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def safe_path(filename: str) -> Path:
    """Ensure path stays within output/ directory."""
    # Strip any path traversal attempts
    safe_name = Path(filename).name
    return OUTPUT_DIR / safe_name


def save_to_output(filename: str, content: str) -> str:
    """Save content to output directory. Returns the saved path string."""
    path = safe_path(filename)
    path.write_text(content, encoding="utf-8")
    logger.info(f"Saved file: {path}")
    return str(path)


def create_file_or_folder(transcription: str, filename: str = None, content_hint: str = None) -> dict:
    """
    Parse the request and create appropriate file/folder.
    Returns dict with: action, content, path, error
    """
    text_lower = transcription.lower()

    # Detect folder creation request
    is_folder = any(k in text_lower for k in ["folder", "directory", "dir", "mkdir"])

    # Extract filename from transcription if not provided
    if not filename:
        filename = _extract_filename(transcription)

    if is_folder:
        folder_name = filename or _extract_folder_name(transcription) or f"new_folder_{_timestamp()}"
        folder_path = OUTPUT_DIR / folder_name
        try:
            folder_path.mkdir(exist_ok=True)
            return {
                "action": f"Created folder `{folder_name}` in output/",
                "content": f"Directory created: output/{folder_name}",
                "path": str(folder_path),
                "error": None,
            }
        except Exception as e:
            return {"action": "Failed to create folder", "content": "", "path": None, "error": str(e)}

    # File creation
    if not filename:
        # Default to a timestamped text file
        filename = f"file_{_timestamp()}.txt"

    content = content_hint or f"# Created by Voice Agent\n# Request: {transcription}\n# Timestamp: {datetime.now().isoformat()}\n"
    path = safe_path(filename)

    try:
        path.write_text(content, encoding="utf-8")
        return {
            "action": f"Created file `{filename}` in output/",
            "content": content,
            "path": str(path),
            "error": None,
        }
    except Exception as e:
        return {"action": "Failed to create file", "content": "", "path": None, "error": str(e)}


def _extract_filename(text: str) -> str:
    """Try to extract a filename from the transcription."""
    # Match patterns like "called X", "named X", "file X.ext"
    patterns = [
        r"(?:called|named|file)\s+([\w\-\.]+\.\w+)",
        r"([\w\-]+\.(py|txt|js|ts|json|yaml|yml|md|html|css|sh|csv))",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_folder_name(text: str) -> str:
    """Extract folder name from transcription."""
    patterns = [
        r"(?:folder|directory|dir)\s+(?:called|named)?\s*([\w\-]+)",
        r"(?:called|named)\s+([\w\-]+)\s+(?:folder|directory)",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
