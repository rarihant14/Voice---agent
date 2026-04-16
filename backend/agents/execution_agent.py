"""
Execution agent for routing classified intents to the appropriate tool path.
"""

import os
import logging
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    transcription: str
    intent: str
    confidence: float
    entities: dict
    session_history: list
    action_taken: str
    output_content: str
    output_path: Optional[str]
    error: Optional[str]
    steps: list


def route_intent(state: AgentState) -> str:
    """Decide which node to execute for the current intent."""
    routing = {
        "write_code": "code_node",
        "create_file": "file_node",
        "summarize_text": "summarize_node",
        "general_chat": "chat_node",
    }
    return routing.get(state.get("intent", "general_chat"), "chat_node")


def code_node(state: AgentState) -> AgentState:
    from backend.tools.code_tools import generate_code
    from backend.tools.file_tools import save_to_output

    state["steps"].append("Generating code...")
    entities = state.get("entities", {})
    transcription = state.get("transcription", "")

    result = generate_code(
        prompt=transcription,
        language=entities.get("language") or "python",
        filename=entities.get("filename"),
        content_hint=entities.get("content_hint"),
    )

    if result.get("error"):
        state["error"] = result["error"]
        state["action_taken"] = "Code generation failed"
        state["output_content"] = ""
        return state

    code = result["code"]
    filename = result["filename"]
    saved_path = save_to_output(filename, code)

    state["action_taken"] = f"Generated and saved `{filename}`"
    state["output_content"] = code
    state["output_path"] = saved_path
    state["steps"].append(f"Code saved to {saved_path}")
    return state


def file_node(state: AgentState) -> AgentState:
    from backend.tools.file_tools import create_file_or_folder

    state["steps"].append("Creating file or folder...")
    entities = state.get("entities", {})
    transcription = state.get("transcription", "")

    result = create_file_or_folder(
        transcription=transcription,
        filename=entities.get("filename"),
        content_hint=entities.get("content_hint"),
    )

    state["action_taken"] = result.get("action", "File created")
    state["output_content"] = result.get("content", "")
    state["output_path"] = result.get("path")
    state["error"] = result.get("error")
    state["steps"].append(state["action_taken"])
    return state


def _format_session_context(history: list) -> str:
    if not history:
        return ""

    lines = []
    for item in history[-5:]:
        lines.append(
            "intent={intent}; input={input}; action={action}; output={output}".format(
                intent=item.get("intent", "unknown"),
                input=item.get("input", "").strip(),
                action=item.get("action_taken", "").strip(),
                output=item.get("output_preview", "").strip(),
            )
        )
    return "\n".join(lines)


def _merge_context_with_request(history: list, transcription: str) -> str:
    memory_context = _format_session_context(history)
    if not memory_context:
        return transcription
    return f"Session context:\n{memory_context}\n\nCurrent user request:\n{transcription}"


def summarize_node(state: AgentState) -> AgentState:
    state["steps"].append("Summarizing...")
    transcription = state.get("transcription", "")
    history = state.get("session_history", [])

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        state["action_taken"] = "Summarization failed (no API key)"
        state["output_content"] = "Please set GROQ_API_KEY to enable summarization."
        state["error"] = "Missing GROQ_API_KEY"
        return state

    try:
        llm = ChatGroq(api_key=groq_key, model="llama-3.3-70b-versatile", temperature=0.3)
        messages = [
            SystemMessage(content="You are a helpful assistant. Summarize or explain the user's request clearly and concisely."),
            HumanMessage(content=_merge_context_with_request(history, transcription)),
        ]
        response = llm.invoke(messages)
        state["action_taken"] = "Text summarized"
        state["output_content"] = response.content
        state["steps"].append("Summary generated")
    except Exception as exc:
        state["error"] = str(exc)
        state["action_taken"] = "Summarization failed"
        state["output_content"] = f"Error: {exc}"

    return state


def chat_node(state: AgentState) -> AgentState:
    state["steps"].append("Processing chat...")
    transcription = state.get("transcription", "")
    history = state.get("session_history", [])

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        state["output_content"] = "Please set GROQ_API_KEY in your .env to enable chat responses."
        state["action_taken"] = "Chat (no LLM)"
        return state

    try:
        llm = ChatGroq(api_key=groq_key, model="llama-3.3-70b-versatile", temperature=0.7)
        messages = [
            SystemMessage(content="You are a helpful, friendly local AI assistant. Be concise and use prior session context when relevant."),
            HumanMessage(content=_merge_context_with_request(history, transcription)),
        ]
        response = llm.invoke(messages)
        state["action_taken"] = "Responded to chat"
        state["output_content"] = response.content
        state["steps"].append("Chat response generated")
    except Exception as exc:
        state["error"] = str(exc)
        state["action_taken"] = "Chat failed"
        state["output_content"] = f"Error: {exc}"

    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("code_node", code_node)
    graph.add_node("file_node", file_node)
    graph.add_node("summarize_node", summarize_node)
    graph.add_node("chat_node", chat_node)

    graph.add_conditional_edges(
        "__start__",
        route_intent,
        {
            "code_node": "code_node",
            "file_node": "file_node",
            "summarize_node": "summarize_node",
            "chat_node": "chat_node",
        },
    )

    graph.add_edge("code_node", END)
    graph.add_edge("file_node", END)
    graph.add_edge("summarize_node", END)
    graph.add_edge("chat_node", END)
    return graph.compile()


class ExecutionAgent:
    """Wrap the LangGraph execution pipeline."""

    def __init__(self):
        self.graph = build_graph()

    def execute(self, transcription: str, intent_result: dict, session_history: Optional[list] = None) -> dict:
        initial_state: AgentState = {
            "transcription": transcription,
            "intent": intent_result.get("intent", "general_chat"),
            "confidence": intent_result.get("confidence", 0.0),
            "entities": intent_result.get("entities", {}),
            "session_history": session_history or [],
            "action_taken": "",
            "output_content": "",
            "output_path": None,
            "error": None,
            "steps": ["Received transcription", "Intent classified"],
        }

        try:
            return self.graph.invoke(initial_state)
        except Exception as exc:
            logger.error("Graph execution failed: %s", exc)
            initial_state["error"] = str(exc)
            initial_state["action_taken"] = "Execution failed"
            return initial_state
