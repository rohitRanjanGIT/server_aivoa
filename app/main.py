from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agent.graph import get_form, run_turn
from .config import AVAILABLE_MODELS, get_settings
from .db import init_db, is_configured
from .schemas import (
    ChatRequest,
    ChatResponse,
    FormState,
    InteractionRecord,
    ModelInfo,
    ModelsResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables if a database is configured; no-op otherwise (Phase 1 runs DB-less).
    init_db()
    yield


app = FastAPI(title="AI-First CRM — HCP Interaction API", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Allow any Vercel deployment (production + preview URLs) without hard-coding each one.
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "groq_configured": bool(settings.groq_api_key),
        "db_configured": is_configured(),
        "model": settings.groq_model,
    }


@app.get("/api/models", response_model=ModelsResponse)
def models() -> ModelsResponse:
    return ModelsResponse(
        models=[ModelInfo(**m) for m in AVAILABLE_MODELS],
        default=settings.groq_model,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    try:
        reply, form, notification, records = run_turn(
            req.thread_id, req.message, req.model
        )
    except RuntimeError as exc:
        # Configuration problems (e.g. missing GROQ_API_KEY).
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — surface provider/LLM errors cleanly
        # e.g. Groq rate limits, bad requests, transient API failures.
        # Groq nests the human-readable message under body["error"]["message"].
        detail = None
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                detail = err.get("message")
            detail = detail or body.get("message")
        detail = detail or str(exc) or exc.__class__.__name__
        raise HTTPException(status_code=502, detail=f"AI service error: {detail}")
    return ChatResponse(
        reply=reply,
        form=FormState(**form),
        notification=notification,
        records=[InteractionRecord(**r) for r in records] if records else None,
    )


@app.get("/api/session/{thread_id}/form", response_model=FormState)
def session_form(thread_id: str) -> FormState:
    # Hydration endpoint — if the agent can't be built yet (e.g. no key) just return an
    # empty form rather than erroring; the UI simply starts blank.
    try:
        return FormState(**get_form(thread_id))
    except RuntimeError:
        return FormState()
