from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Curated Groq models the UI offers in the sidebar switcher. Only ids in this catalog are
# accepted from the client (anything else falls back to the configured default), so the
# dropdown can't be used to request an arbitrary/unsupported model.
AVAILABLE_MODELS: list[dict] = [
    {
        "id": "openai/gpt-oss-20b",
        "label": "GPT-OSS 20B",
        "note": "Recommended — reliable tool routing, fast, light on tokens.",
        "recommended": True,
    },
    {
        "id": "openai/gpt-oss-120b",
        "label": "GPT-OSS 120B",
        "note": "Larger sibling — higher quality, uses more tokens per call.",
        "recommended": False,
    },
    {
        "id": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B",
        "note": "Strong reasoning, but token-heavy (free-tier daily cap hits sooner).",
        "recommended": False,
    },
    {
        "id": "llama-3.1-8b-instant",
        "label": "Llama 3.1 8B",
        "note": "Fastest, but weak at tool routing — may loop on multi-step requests.",
        "recommended": False,
    },
]

_MODEL_IDS = {m["id"] for m in AVAILABLE_MODELS}


def resolve_model(requested: str | None) -> str:
    """Return a valid model id: the requested one if it's in the catalog, else the default."""
    if requested and requested in _MODEL_IDS:
        return requested
    return get_settings().groq_model


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    groq_api_key: str = ""
    # gemma2-9b-it (named in the assignment) was decommissioned by Groq. We use
    # openai/gpt-oss-20b — a strong, reliable tool-router that's much lighter than the 70B
    # (the small llama-3.1-8b-instant is too weak here: it loops through tools instead of
    # stopping). Override via GROQ_MODEL (e.g. llama-3.3-70b-versatile for a larger model).
    groq_model: str = "openai/gpt-oss-20b"
    database_url: str = ""
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
