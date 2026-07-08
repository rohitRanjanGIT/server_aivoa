"""Builds and runs the LangGraph ReAct agent backed by a Groq LLM (see config.groq_model)."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent

from ..config import get_settings, resolve_model
from ..schemas import empty_form
from .prompts import system_prompt
from .state import FormAgentState
from .tools import ALL_TOOLS

# One in-memory checkpointer for the process — keyed per thread_id so each browser
# session keeps its own conversation + form state.
_checkpointer = MemorySaver()


@lru_cache
def get_agent(model: str | None = None):
    """Build (and cache) a ReAct agent for the given model id.

    Agents are cached per model so switching models in the sidebar is cheap. They all share
    the one process-wide checkpointer, so a thread's form/history survives a model switch.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    llm = ChatGroq(
        model=model or settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0,
    )

    return create_react_agent(
        llm,
        tools=ALL_TOOLS,
        state_schema=FormAgentState,
        state_modifier=system_prompt(),
        checkpointer=_checkpointer,
    )


def run_turn(
    thread_id: str, message: str, model: str | None = None
) -> tuple[str, dict, str | None, list | None]:
    """Run one conversational turn.

    Returns (assistant_reply, updated_form, notification, records). `notification` and
    `records` are transient — reset each turn and populated only by the tool that ran.
    `model` is the sidebar-selected model id (validated/normalized by the caller).
    """
    agent = get_agent(resolve_model(model))
    # A single user turn should need at most a couple of tool calls. Cap the graph so a
    # weak model that loops through tools fails fast and cheap instead of burning tokens.
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 8}

    # Reset transient signals every turn; seed an empty form only on a brand-new thread.
    inputs: dict = {
        "messages": [HumanMessage(content=message)],
        "notification": None,
        "records": None,
    }
    snapshot = agent.get_state(config)
    if not snapshot.values.get("form"):
        inputs["form"] = empty_form()
        inputs["editing_id"] = None

    try:
        result = agent.invoke(inputs, config)
    except GraphRecursionError:
        # The model kept calling tools without settling on an answer. Return the current
        # form unchanged with a friendly nudge rather than a 500.
        current = agent.get_state(config).values
        return (
            "I got a bit tangled up on that one — could you rephrase it more simply?",
            current.get("form") or empty_form(),
            None,
            None,
        )

    form = result.get("form") or empty_form()
    notification = result.get("notification")
    records = result.get("records")
    reply = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            reply = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    return reply, form, notification, records


def get_form(thread_id: str) -> dict:
    """Return the current form for a thread (for hydration/reload)."""
    agent = get_agent()
    snapshot = agent.get_state({"configurable": {"thread_id": thread_id}})
    return snapshot.values.get("form") or empty_form()
