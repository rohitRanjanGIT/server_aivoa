"""Lazy, optional SQLAlchemy setup.

Phase 1's two tools operate entirely on LangGraph state, so the app must run even when
no database is configured. The engine/session are created on first use only when
DATABASE_URL is set. Phase 2 (submit_interaction / search_hcp) will consume these.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def is_configured() -> bool:
    return bool(get_settings().database_url)


def _normalize_url(url: str) -> str:
    """Ensure the psycopg3 driver is used (installed here), not the default psycopg2."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL is not configured.")
        _engine = create_engine(_normalize_url(url), pool_pre_ping=True, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def init_db() -> None:
    """Create tables if a database is configured. Safe no-op otherwise."""
    if not is_configured():
        return
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
