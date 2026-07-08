"""LangGraph tools that own the interaction form and its persistence.

(form in graph state):
  * log_interaction  — parse a full natural-language description into the form.
  * edit_interaction — merge corrections into the form without wiping fields.
  * submit_interaction — save the form as a NEW record, then clear the form.
  * list_interactions  — return all saved records (for the records table + chat).
  * select_interaction — load a saved record (by id) into the form for editing.
  * update_interaction — write the currently-selected record's changes back to its row.
  * delete_interaction — delete a saved record by id.
  * clear_form         — reset the form.

Every tool returns a `Command` that updates shared graph state, plus the required
ToolMessage so the ReAct loop can continue.
"""

from __future__ import annotations

from datetime import date as date_cls, datetime, timedelta
from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ..db import get_sessionmaker, is_configured
from ..models import Interaction
from ..schemas import empty_form

VALID_INTERACTION_TYPES = {"meeting", "call", "email", "conference", "other"}

# --------------------------------------------------------------------------- helpers
def _normalize_sentiment(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    if v.startswith("pos"):
        return "Positive"
    if v.startswith("neg"):
        return "Negative"
    if v.startswith("neu"):
        return "Neutral"
    return value.strip().capitalize()


def _normalize_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    if v in VALID_INTERACTION_TYPES:
        return v.capitalize()
    return value.strip().capitalize()


def _resolve_date(value: Optional[str]) -> Optional[str]:
    """Turn relative words into an ISO date; pass through anything already concrete."""
    if value is None:
        return None
    v = value.strip().lower()
    today = date_cls.today()
    if v in ("", "today", "now"):
        return today.isoformat()
    if v == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    if v == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    return value.strip()


def _clean_list(value) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        items = [p.strip() for p in value.replace(";", ",").split(",")]
    else:
        items = [str(p).strip() for p in value]
    return [p for p in items if p]


def _join(items) -> str:
    return ", ".join(items or [])


def _split(value: Optional[str]) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _row_to_form(row: Interaction) -> dict:
    return {
        "hcp_name": row.hcp_name or "",
        "interaction_type": row.interaction_type or "Meeting",
        "date": row.date or "",
        "time": row.time or "",
        "attendees": _split(row.attendees),
        "topics_discussed": row.topics_discussed or "",
        "sentiment": row.sentiment or "",
        "materials_shared": _split(row.materials_shared),
        "follow_up": row.follow_up or None,
    }


def _row_to_record(row: Interaction) -> dict:
    return {
        "id": row.id,
        "hcp_name": row.hcp_name or "",
        "interaction_type": row.interaction_type or "",
        "date": row.date or "",
        "time": row.time or "",
        "sentiment": row.sentiment or "",
        "topics_discussed": row.topics_discussed or "",
        "materials_shared": _split(row.materials_shared),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _tool_msg(text: str, tool_call_id: str) -> dict:
    return {"messages": [ToolMessage(text, tool_call_id=tool_call_id)]}


def _db_unavailable(tool_call_id: str) -> Command:
    return Command(
        update=_tool_msg(
            "The database is not configured, so records cannot be saved or read. "
            "Set DATABASE_URL in the backend .env.",
            tool_call_id,
        )
    )


# --------------------------------------------------------------------- Phase 1 tools
@tool
def log_interaction(
    tool_call_id: Annotated[str, InjectedToolCallId],
    hcp_name: Optional[str] = None,
    interaction_type: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    topics_discussed: Optional[str] = None,
    sentiment: Optional[str] = None,
    materials_shared: Optional[list[str]] = None,
) -> Command:
    """Log a NEW HCP interaction by parsing a natural-language description into the form.

    Use this when the rep describes an interaction for the first time (e.g. "Today I met
    Dr. Smith and discussed Prodo-X efficacy, sentiment was positive, shared brochures").
    Extract every field you can. Leave a field as null if it was not mentioned.

    Args:
        hcp_name: Name of the healthcare professional, e.g. "Dr. Smith".
        interaction_type: One of Meeting, Call, Email, Conference, Other.
        date: The interaction date. May be "today"/"yesterday"/"tomorrow" or an ISO date.
        time: Time of the interaction as "HH:MM" (24h) if mentioned.
        attendees: Other people present.
        topics_discussed: Summary of what was discussed.
        sentiment: Overall sentiment — Positive, Neutral, or Negative.
        materials_shared: Materials or samples shared, e.g. ["Brochures"].
    """
    form = empty_form()
    form["hcp_name"] = (hcp_name or "").strip()
    form["interaction_type"] = _normalize_type(interaction_type) or "Meeting"
    form["date"] = _resolve_date(date) or date_cls.today().isoformat()
    form["time"] = (time or datetime.now().strftime("%H:%M")).strip()
    form["attendees"] = _clean_list(attendees) or []
    form["topics_discussed"] = (topics_discussed or "").strip()
    form["sentiment"] = _normalize_sentiment(sentiment) or ""
    form["materials_shared"] = _clean_list(materials_shared) or []

    return Command(
        update={
            "form": form,
            "editing_id": None,
            **_tool_msg("Interaction logged and form populated.", tool_call_id),
        }
    )


@tool
def edit_interaction(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    hcp_name: Optional[str] = None,
    interaction_type: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    topics_discussed: Optional[str] = None,
    sentiment: Optional[str] = None,
    materials_shared: Optional[list[str]] = None,
) -> Command:
    """Edit the CURRENT interaction form by changing ONLY the fields the rep mentions.

    Use this for corrections/adjustments to an already-populated form (e.g. "Actually the
    name was Dr. John and the sentiment was negative"). Pass only the fields being changed;
    everything else is left untouched. This edits the form in place — it does not save to
    the database (use submit_interaction or update_interaction for that).
    """
    form = dict(state.get("form") or empty_form())

    if hcp_name is not None:
        form["hcp_name"] = hcp_name.strip()
    if interaction_type is not None:
        form["interaction_type"] = _normalize_type(interaction_type) or form["interaction_type"]
    if date is not None:
        form["date"] = _resolve_date(date) or form["date"]
    if time is not None:
        form["time"] = time.strip()
    if attendees is not None:
        form["attendees"] = _clean_list(attendees) or []
    if topics_discussed is not None:
        form["topics_discussed"] = topics_discussed.strip()
    if sentiment is not None:
        form["sentiment"] = _normalize_sentiment(sentiment) or ""
    if materials_shared is not None:
        form["materials_shared"] = _clean_list(materials_shared) or []

    return Command(update={"form": form, **_tool_msg("Form updated.", tool_call_id)})


# --------------------------------------------------------------------- Phase 2 tools
@tool
def submit_interaction(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Save the CURRENT form as a NEW interaction record in the database.

    Use this when the rep is done describing a new interaction and wants to save/log/submit
    it. Requires at least an HCP name. On success the form is cleared for the next entry.
    """
    if not is_configured():
        return _db_unavailable(tool_call_id)

    form = state.get("form") or empty_form()
    if not (form.get("hcp_name") or "").strip():
        return Command(
            update=_tool_msg(
                "Cannot submit: an HCP name is required before saving.", tool_call_id
            )
        )

    Session = get_sessionmaker()
    with Session() as session:
        row = Interaction(
            hcp_name=form.get("hcp_name", ""),
            interaction_type=form.get("interaction_type", "Meeting"),
            date=form.get("date", ""),
            time=form.get("time", ""),
            attendees=_join(form.get("attendees")),
            topics_discussed=form.get("topics_discussed", ""),
            sentiment=form.get("sentiment", ""),
            materials_shared=_join(form.get("materials_shared")),
            follow_up=form.get("follow_up") or "",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        new_id = row.id

    return Command(
        update={
            "form": empty_form(),
            "editing_id": None,
            "notification": f"Saved as interaction #{new_id}.",
            **_tool_msg(f"Interaction saved to the database with id {new_id}.", tool_call_id),
        }
    )


@tool
def list_interactions(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """List all saved interaction records from the database.

    Use this when the rep asks to see/show/list their logged interactions. Returns each
    record's id so the rep can then open, update, or delete a specific one.
    """
    if not is_configured():
        return _db_unavailable(tool_call_id)

    Session = get_sessionmaker()
    with Session() as session:
        rows = session.query(Interaction).order_by(Interaction.id.desc()).all()
        records = [_row_to_record(r) for r in rows]

    if not records:
        summary = "There are no saved interactions yet."
    else:
        lines = [
            f"#{r['id']}: {r['hcp_name'] or 'Unknown'} — {r['interaction_type']} on "
            f"{r['date']} ({r['sentiment'] or 'no sentiment'})"
            for r in records
        ]
        summary = f"Found {len(records)} interaction(s):\n" + "\n".join(lines)

    return Command(update={"records": records, **_tool_msg(summary, tool_call_id)})


@tool
def select_interaction(
    tool_call_id: Annotated[str, InjectedToolCallId],
    interaction_id: int,
) -> Command:
    """Load a saved interaction (by its id) into the form so it can be edited.

    Use this when the rep wants to open/select/edit an existing record, e.g. "open #3" or
    "edit the Dr. Smith interaction" (after listing to find its id). After loading, the rep
    can describe changes (handled by edit_interaction) and then save with update_interaction.
    """
    if not is_configured():
        return _db_unavailable(tool_call_id)

    Session = get_sessionmaker()
    with Session() as session:
        row = session.get(Interaction, interaction_id)
        if row is None:
            return Command(
                update=_tool_msg(
                    f"No interaction found with id {interaction_id}.", tool_call_id
                )
            )
        form = _row_to_form(row)

    return Command(
        update={
            "form": form,
            "editing_id": interaction_id,
            "notification": f"Loaded interaction #{interaction_id} for editing.",
            **_tool_msg(
                f"Loaded interaction {interaction_id}. Describe any changes, then say "
                f"'update' to save them.",
                tool_call_id,
            ),
        }
    )


@tool
def update_interaction(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
) -> Command:
    """Save changes to the CURRENTLY-SELECTED record back to the database.

    Use this to persist edits to a record that was opened with select_interaction (NOT to
    create a new record — use submit_interaction for that). On success the form is cleared.
    """
    if not is_configured():
        return _db_unavailable(tool_call_id)

    editing_id = state.get("editing_id")
    if not editing_id:
        return Command(
            update=_tool_msg(
                "No record is currently open. Use submit_interaction to save a new one, or "
                "select_interaction to open an existing record first.",
                tool_call_id,
            )
        )

    form = state.get("form") or empty_form()
    Session = get_sessionmaker()
    with Session() as session:
        row = session.get(Interaction, editing_id)
        if row is None:
            return Command(
                update={
                    "editing_id": None,
                    **_tool_msg(
                        f"Interaction #{editing_id} no longer exists.", tool_call_id
                    ),
                }
            )
        row.hcp_name = form.get("hcp_name", "")
        row.interaction_type = form.get("interaction_type", "Meeting")
        row.date = form.get("date", "")
        row.time = form.get("time", "")
        row.attendees = _join(form.get("attendees"))
        row.topics_discussed = form.get("topics_discussed", "")
        row.sentiment = form.get("sentiment", "")
        row.materials_shared = _join(form.get("materials_shared"))
        row.follow_up = form.get("follow_up") or ""
        session.commit()

    return Command(
        update={
            "form": empty_form(),
            "editing_id": None,
            "notification": f"Updated interaction #{editing_id}.",
            **_tool_msg(f"Interaction #{editing_id} updated.", tool_call_id),
        }
    )


@tool
def delete_interaction(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[dict, InjectedState],
    interaction_id: int,
) -> Command:
    """Delete a saved interaction record by its id.

    Use this when the rep asks to delete/remove a specific record, e.g. "delete #3".
    """
    if not is_configured():
        return _db_unavailable(tool_call_id)

    Session = get_sessionmaker()
    with Session() as session:
        row = session.get(Interaction, interaction_id)
        if row is None:
            return Command(
                update=_tool_msg(
                    f"No interaction found with id {interaction_id}.", tool_call_id
                )
            )
        session.delete(row)
        session.commit()

    update: dict = {
        "notification": f"Deleted interaction #{interaction_id}.",
        **_tool_msg(f"Interaction #{interaction_id} deleted.", tool_call_id),
    }
    # If the deleted record was the one open for editing, clear the form.
    if state.get("editing_id") == interaction_id:
        update["form"] = empty_form()
        update["editing_id"] = None
    return Command(update=update)


@tool
def clear_form(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    """Reset the interaction form to empty (does not touch saved records).

    Use this when the rep wants to clear/reset/start over on the form.
    """
    return Command(
        update={
            "form": empty_form(),
            "editing_id": None,
            "notification": "Form cleared.",
            **_tool_msg("Form cleared.", tool_call_id),
        }
    )


ALL_TOOLS = [
    log_interaction,
    edit_interaction,
    submit_interaction,
    list_interactions,
    select_interaction,
    update_interaction,
    delete_interaction,
    clear_form,
]

# Backwards-compatible alias.
PHASE1_TOOLS = [log_interaction, edit_interaction]