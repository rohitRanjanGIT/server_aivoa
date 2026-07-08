# AI-First CRM — Backend (FastAPI + LangGraph)

Backend for the HCP "Log Interaction" screen. A **LangGraph** ReAct agent (Groq LLM) drives a
read-only interaction form entirely through chat. Companion frontend repo: **client_aivoa**.

> **Model note:** the assignment names `gemma2-9b-it`, but Groq has **decommissioned** it. The
> default is **`openai/gpt-oss-20b`** — a reliable tool-router, lighter than the 70B. Override
> with `GROQ_MODEL` (e.g. `llama-3.3-70b-versatile`). Models can also be switched per request.

## Stack
FastAPI · LangGraph (`create_react_agent`) · `langchain-groq` · SQLAlchemy (PostgreSQL, lazy) ·
Pydantic v2.

## Setup & run
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env            # then set GROQ_API_KEY (and optionally DATABASE_URL)
uvicorn app.main:app --reload     # http://localhost:8000
```
Check `http://localhost:8000/api/health` — `groq_configured` should be `true`.

## LangGraph tools (8; assignment minimum is 5)
`log_interaction`, `edit_interaction` (mandatory) · `submit_interaction`, `list_interactions`,
`select_interaction`, `update_interaction`, `delete_interaction`, `clear_form` (custom CRUD).

## API
- `POST /api/chat` `{ thread_id, message, model? }` → `{ reply, form, notification?, records? }`
- `GET  /api/models` → `{ models: [{ id, label, note, recommended }], default }`
- `GET  /api/session/{thread_id}/form` → current `FormState`
- `GET  /api/health`

## Layout
```
app/
  main.py            FastAPI app + endpoints
  config.py          settings + model catalog
  schemas.py         FormState + request/response models
  db.py, models.py   lazy SQLAlchemy setup + ORM models
  agent/
    graph.py         create_react_agent + ChatGroq + MemorySaver, run_turn()
    state.py         FormAgentState
    tools.py         the 8 LangGraph tools
    prompts.py       system prompt / tool-routing rules
```

> **Secrets:** `.env` is gitignored. `.env.example` holds only placeholders — never commit real
> keys. Rotate any key that has been shared in plaintext.
