"""ORM models. Scaffolded now; the write path is exercised in Phase 2."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class HCP(Base):
    __tablename__ = "hcps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    specialty: Mapped[str] = mapped_column(String(255), default="")
    institution: Mapped[str] = mapped_column(String(255), default="")


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hcp_name: Mapped[str] = mapped_column(String(255), default="")
    interaction_type: Mapped[str] = mapped_column(String(64), default="Meeting")
    date: Mapped[str] = mapped_column(String(32), default="")
    time: Mapped[str] = mapped_column(String(32), default="")
    attendees: Mapped[str] = mapped_column(Text, default="")  # comma-separated
    topics_discussed: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str] = mapped_column(String(32), default="")
    materials_shared: Mapped[str] = mapped_column(Text, default="")  # comma-separated
    follow_up: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
