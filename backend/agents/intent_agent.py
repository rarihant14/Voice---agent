"""
Intent Classification Agent
Uses Groq LLM via LangChain to classify user intent from transcribed text.
Supported intents: create_file, write_code, summarize_text, general_chat
"""

import os
import json
import logging
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntentResult(BaseModel):
    intent: str = Field(description="Primary intent: create_file | write_code | summarize_text | general_chat")
    confidence: float = Field(description="Confidence score 0.0 to 1.0")
    entities: dict = Field(description="Extracted entities like filename, language, topic")
    reasoning: str = Field(description="Brief reasoning for classification")
    sub_intents: list = Field(description="Any secondary intents detected")


INTENT_SYSTEM_PROMPT = """You are an intent classification engine for a voice-controlled AI assistant.
Analyze the user's transcribed speech and classify it into exactly one primary intent.

Available intents:
- create_file: User wants to create a new file or folder (e.g., "create a file called notes.txt", "make a folder")
- write_code: User wants code generated and/or saved to a file (e.g., "write a Python function", "create a script that...")
- summarize_text: User wants text summarized or explained (e.g., "summarize this", "explain", "what does this mean")
- general_chat: Any general question, greeting, or conversation not fitting above

You MUST respond with valid JSON matching this exact schema:
{{
  "intent": "<one of the four intents>",
  "confidence": <float 0.0-1.0>,
  "entities": {{
    "filename": "<extracted filename or null>",
    "language": "<programming language or null>",
    "topic": "<main topic or null>",
    "content_hint": "<brief description of desired content or null>"
  }},
  "reasoning": "<one sentence explaining why>",
  "sub_intents": ["<additional intents if any>"]
}}"""

INTENT_USER_PROMPT = """Transcribed speech: "{text}"

Classify the intent and extract relevant entities."""


class IntentAgent:
    """Classifies user intent using Groq LLM via LangChain."""

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.llm = None
        self._init_llm()

    def _init_llm(self):
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set. Intent agent will use fallback.")
            return
        try:
            self.llm = ChatGroq(
                api_key=self.groq_api_key,
                model="llama-3.3-70b-versatile",
                temperature=0.1,
                max_tokens=512,
            )
        except Exception as e:
            logger.error(f"Failed to init LLM: {e}")

    def classify(self, text: str) -> dict:
        """Classify the intent of the given text."""
        if not text or not text.strip():
            return self._fallback_result("empty input", "general_chat")

        if self.llm:
            return self._classify_with_llm(text)
        return self._classify_with_rules(text)

    def _classify_with_llm(self, text: str) -> dict:
        """Use LangChain + Groq for classification."""
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", INTENT_SYSTEM_PROMPT),
                ("human", INTENT_USER_PROMPT),
            ])
            chain = prompt | self.llm
            response = chain.invoke({"text": text})
            content = response.content.strip()

            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            result = json.loads(content)
            result["method"] = "groq-llm"
            return result
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._classify_with_rules(text)

    def _classify_with_rules(self, text: str) -> dict:
        """Rule-based fallback classifier."""
        text_lower = text.lower()

        code_keywords = ["write code", "create a script", "python", "function", "class", "generate code",
                         "write a", "implement", "script", "program", "def ", "make a function"]
        file_keywords = ["create a file", "create file", "make a file", "new file", "create folder",
                         "make folder", "touch ", "mkdir"]
        summarize_keywords = ["summarize", "summary", "explain", "what does", "tldr", "brief", "describe"]

        if any(k in text_lower for k in code_keywords):
            intent = "write_code"
        elif any(k in text_lower for k in file_keywords):
            intent = "create_file"
        elif any(k in text_lower for k in summarize_keywords):
            intent = "summarize_text"
        else:
            intent = "general_chat"

        return {
            "intent": intent,
            "confidence": 0.7,
            "entities": {
                "filename": None,
                "language": "python" if "python" in text_lower else None,
                "topic": None,
                "content_hint": text,
            },
            "reasoning": "Rule-based classification (LLM unavailable)",
            "sub_intents": [],
            "method": "rule-based",
        }

    def _fallback_result(self, reason: str, intent: str) -> dict:
        return {
            "intent": intent,
            "confidence": 0.0,
            "entities": {"filename": None, "language": None, "topic": None, "content_hint": None},
            "reasoning": reason,
            "sub_intents": [],
            "method": "fallback",
        }
