from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FormState(BaseModel):
    """The structured Interaction form. This mirrors the left panel of the UI and the
    Redux `form` slice on the frontend. The agent is the *only* writer of this object."""

    hcp_name: str = ""
    interaction_type: str = "Meeting"
    date: str = ""  # ISO date string, e.g. "2026-07-08"
    time: str = ""  # "HH:MM"
    attendees: list[str] = Field(default_factory=list)
    topics_discussed: str = ""
    sentiment: str = ""  # Positive | Neutral | Negative
    materials_shared: list[str] = Field(default_factory=list)
    follow_up: Optional[str] = None  # populated in Phase 2


def empty_form() -> dict:
    """A fresh, empty form as a plain dict (the shape stored in LangGraph state)."""
    return FormState().model_dump()


class InteractionRecord(BaseModel):
    """A persisted interaction, as returned by list_interactions for the records table."""

    id: int
    hcp_name: str = ""
    interaction_type: str = ""
    date: str = ""
    time: str = ""
    sentiment: str = ""
    topics_discussed: str = ""
    materials_shared: list[str] = Field(default_factory=list)
    created_at: str = ""


class ChatRequest(BaseModel):
    thread_id: str
    message: str
    # Optional model id chosen in the sidebar; ignored if not in the catalog.
    model: Optional[str] = None


class ModelInfo(BaseModel):
    id: str
    label: str
    note: str = ""
    recommended: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    default: str


class ChatResponse(BaseModel):
    reply: str
    form: FormState
    # Transient UI signals produced by a tool this turn (None when not applicable).
    notification: Optional[str] = None
    records: Optional[list[InteractionRecord]] = None
