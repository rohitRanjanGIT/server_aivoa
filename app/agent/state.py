from __future__ import annotations

from typing import Optional

from langgraph.prebuilt.chat_agent_executor import AgentState


class FormAgentState(AgentState):
    """Agent state = the default ReAct state (messages + remaining_steps) plus our fields.

    All custom keys use last-value-wins semantics (no reducer): tools return a Command that
    overwrites them.
      * form         — the structured interaction form (agent-owned).
      * editing_id   — DB id of the record currently loaded for editing, else None.
      * notification — a transient toast message for the UI (reset each turn).
      * records      — transient list of records from list_interactions (reset each turn).
    """

    form: dict
    editing_id: Optional[int]
    notification: Optional[str]
    records: Optional[list]
