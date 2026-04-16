"""
Speech-to-Text Agent
Uses OpenAI Whisper via API (groq/openai-compatible) for transcription.
Reasoning: Local Whisper models require significant VRAM (large model ~3GB).
For production reliability and speed, we use Groq's Whisper endpoint which
offers near-instant transcription. Falls back to local whisper-tiny if no API key.
"""

import os
import tempfile
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)


class STTAgent:
    """Handles audio transcription using Groq's Whisper API."""

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.model = "whisper-large-v3"

    def transcribe(self, audio_path: str) -> dict:
        """
        Transcribe audio file to text.
        Returns dict with: text, language, duration, method
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return {"error": "Audio file not found", "text": ""}

        # Try Groq Whisper API first
        if self.groq_api_key:
            return self._transcribe_groq(audio_path)

        # Fallback: local whisper-tiny (no GPU needed)
        return self._transcribe_local(audio_path, groq_attempted=False)

    def _transcribe_groq(self, audio_path: Path) -> dict:
        """Use Groq's Whisper API for transcription."""
        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)

            with open(audio_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    file=(audio_path.name, f.read()),
                    model=self.model,
                    response_format="verbose_json",
                )

            return {
                "text": transcription.text.strip(),
                "language": getattr(transcription, "language", "en"),
                "duration": getattr(transcription, "duration", 0),
                "method": "groq-whisper-large-v3",
                "error": None,
            }
        except Exception as e:
            logger.error(f"Groq STT failed: {e}")
            return self._transcribe_local(audio_path, groq_attempted=True, groq_error=str(e))

    def _transcribe_local(self, audio_path: Path, groq_attempted: bool = False, groq_error: str = "") -> dict:
        """Fallback: local whisper-tiny via transformers pipeline."""
        try:
            import whisper
            model = whisper.load_model("tiny")
            result = model.transcribe(str(audio_path))
            return {
                "text": result["text"].strip(),
                "language": result.get("language", "en"),
                "duration": 0,
                "method": "local-whisper-tiny",
                "error": None,
            }
        except ImportError:
            error_message = "No STT backend available. Install openai-whisper"
            if groq_attempted and groq_error:
                error_message = f"Groq STT failed: {groq_error}. Also could not fall back to local whisper because openai-whisper is not installed."
            elif not self.groq_api_key:
                error_message += " or set GROQ_API_KEY."
            else:
                error_message += "."
            return {
                "text": "",
                "language": "en",
                "duration": 0,
                "method": "none",
                "error": error_message,
            }
        except Exception as e:
            return {
                "text": "",
                "language": "en",
                "duration": 0,
                "method": "none",
                "error": str(e),
            }
