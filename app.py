"""
FastAPI Backend Server
Exposes endpoints for audio upload, pipeline processing, and output listing.
"""

import os
import sys
import json
import logging
import tempfile
import shutil
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from backend.agents.stt_agent import STTAgent
from backend.agents.intent_agent import IntentAgent
from backend.agents.execution_agent import ExecutionAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# App Init

app = FastAPI(title="Voice AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
FRONTEND_DIR = Path(__file__).parent / "frontend"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Agent singletons
stt_agent = STTAgent()
intent_agent = IntentAgent()
execution_agent = ExecutionAgent()
SESSION_HISTORY_LIMIT = 20
SESSION_STORE = {}


#Models 

class TextProcessRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


class PipelineResponse(BaseModel):
    session_id: str
    transcription: str
    stt_method: str
    intent: str
    confidence: float
    entities: dict
    reasoning: str
    action_taken: str
    output_content: str
    output_path: Optional[str]
    steps: list
    error: Optional[str]
    history: list


# Endpoints 

@app.get("/")
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok", "groq_configured": bool(os.getenv("GROQ_API_KEY"))}


@app.post("/process/audio", response_model=PipelineResponse)
async def process_audio(request: Request, file: UploadFile = File(...)):
    """Accept an audio file, run full STT → Intent → Execution pipeline."""
    # Validate file type
    allowed = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported audio format: {suffix}. Use: {allowed}")

    # Save temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        session_id = _resolve_session_id(request)
        return _run_pipeline(tmp_path, session_id)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/process/text", response_model=PipelineResponse)
async def process_text(request: Request, req: TextProcessRequest):
    """Process plain text directly (skip STT)."""
    session_id = req.session_id or _resolve_session_id(request)
    return _run_pipeline_from_text(req.text, session_id=session_id)


@app.get("/session/history")
async def session_history(request: Request):
    session_id = _resolve_session_id(request)
    return {"session_id": session_id, "history": _get_session_history(session_id)}


@app.get("/output/files")
async def list_output_files():
    """List all files in the output directory."""
    files = []
    for f in sorted(OUTPUT_DIR.iterdir()):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "path": f"/output/{f.name}",
            })
    return {"files": files}


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


#Pipeline Logic 

def _resolve_session_id(request: Request) -> str:
    header_session = request.headers.get("X-Session-ID", "").strip()
    return header_session or str(uuid.uuid4())


def _get_session_history(session_id: str) -> list:
    return list(SESSION_STORE.get(session_id, []))


def _append_session_history(session_id: str, response: dict) -> list:
    history = SESSION_STORE.setdefault(session_id, [])
    history.append({
        "input": response.get("transcription", ""),
        "intent": response.get("intent", "general_chat"),
        "action_taken": response.get("action_taken", ""),
        "output_preview": (response.get("output_content", "") or "")[:180],
        "error": response.get("error"),
        "stt_method": response.get("stt_method", "direct"),
    })
    SESSION_STORE[session_id] = history[-SESSION_HISTORY_LIMIT:]
    return list(SESSION_STORE[session_id])


def _run_pipeline(audio_path: str, session_id: str) -> dict:
    """Full pipeline: STT → Intent → Execute."""
    # Step 1: Speech to Text
    logger.info("Running STT...")
    stt_result = stt_agent.transcribe(audio_path)

    if stt_result.get("error") and not stt_result.get("text"):
        response = _error_response(stt_result["error"], stt_result.get("method", "none"))
        response["session_id"] = session_id
        response["history"] = _append_session_history(session_id, response)
        return response

    transcription = stt_result["text"]
    return _run_pipeline_from_text(transcription, stt_result, session_id=session_id)


def _run_pipeline_from_text(text: str, stt_result: dict = None, session_id: Optional[str] = None) -> dict:
    """Intent + Execution pipeline from text."""
    if stt_result is None:
        stt_result = {"text": text, "method": "direct-text", "language": "en", "error": None}
    if not session_id:
        session_id = str(uuid.uuid4())
    session_history = _get_session_history(session_id)

    # Step 2: Intent Classification
    logger.info("Classifying intent...")
    intent_result = intent_agent.classify(text)

    # Step 3: Execute
    logger.info(f"Executing intent: {intent_result.get('intent')}")
    exec_result = execution_agent.execute(text, intent_result, session_history=session_history)

    response = {
        "session_id": session_id,
        "transcription": text,
        "stt_method": stt_result.get("method", "direct"),
        "intent": intent_result.get("intent", "general_chat"),
        "confidence": intent_result.get("confidence", 0.0),
        "entities": intent_result.get("entities", {}),
        "reasoning": intent_result.get("reasoning", ""),
        "action_taken": exec_result.get("action_taken", ""),
        "output_content": exec_result.get("output_content", ""),
        "output_path": exec_result.get("output_path"),
        "steps": exec_result.get("steps", []),
        "error": exec_result.get("error"),
        "history": [],
    }
    response["history"] = _append_session_history(session_id, response)
    return response


def _error_response(error: str, method: str) -> dict:
    return {
        "session_id": "",
        "transcription": "",
        "stt_method": method,
        "intent": "general_chat",
        "confidence": 0.0,
        "entities": {},
        "reasoning": "",
        "action_taken": "Pipeline failed",
        "output_content": "",
        "output_path": None,
        "steps": ["❌ Pipeline failed"],
        "error": error,
        "history": [],
    }


def _open_browser_once(url: str) -> None:
    def _open() -> None:
        time.sleep(1.5)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    _open_browser_once(f"http://{host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=True)
