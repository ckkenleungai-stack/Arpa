# Arpa — W1 first-slice scaffold

Python monorepo for **Arpa** (agent platform): FastAPI control plane + LangGraph `research_publish_v1` + OpenRouter gateway helpers + folder jail + Action Recording stub.

Target remote (later via CloudAgent): `https://github.com/ckkenleungai-stack/Arpa`

## Layout

```text
arpa-scaffold/
  pyproject.toml
  README.md
  .env.example
  docker-compose.yml
  packages/
    control_plane/   # FastAPI: health, auth, conversations, runs (+ SSE, HITL, pause/stop, AR)
    workflows/       # research_publish_v1 LangGraph (planner→tools→synthesizer+hitl_gate)
    gateway/         # ChatOpenRouter helpers + allowlist + require_parameters
    tools/           # first-party tools + folder jail
    db/              # SQLAlchemy conversations + approve_ledger + Alembic
    ar/              # Action Recording emitter stub (schema v0)
    evals/           # stub — HG-AUD red/xfail notes (no fake greens)
  scripts/dev_run.sh
  tests/
```

## Prerequisites

- Python 3.11+
- Docker (for Compose Postgres + API)
- Optional: `OPENROUTER_API_KEY` for live LLM calls (empty = offline stub)

## Quick start (Compose)

```bash
cd arpa-scaffold
cp .env.example .env          # edit secrets locally — never commit .env
docker compose up --build
# API: http://localhost:8000/health
```

Migrations run on API container start (`alembic upgrade head`).

## Local (without full Compose API)

```bash
# 1) Postgres only
docker compose up -d postgres

# 2) Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# sqlite tests need:
pip install aiosqlite

# 3) Migrate
export DATABASE_URL_SYNC=postgresql://arpa:arpa@localhost:5432/arpa
export DATABASE_URL=postgresql+asyncpg://arpa:arpa@localhost:5432/arpa
alembic -c packages/db/db/alembic.ini upgrade head

# 4) Run API
./scripts/dev_run.sh
# or: uvicorn control_plane.main:app --reload --port 8000
```

Set `PYTHONPATH` to the package roots (see `scripts/dev_run.sh`) or install editable.

## Demo curl

Mint a local HS256 JWT (Google JWKS later — claim `tenant_id` + `sub`):

```bash
python - <<'PY'
from control_plane.auth import mint_dev_token
print(mint_dev_token(user_id="user-1", tenant_id="tenant-a"))
PY
```

```bash
export TOKEN=...   # from mint_dev_token

curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/v1/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"goal":"Summarize example.com into private HTML"}'

# Snapshot (plan / pending_action / draft)
curl -s http://localhost:8000/v1/runs/$THREAD_ID \
  -H "Authorization: Bearer $TOKEN"

# SSE
curl -N http://localhost:8000/v1/runs/$THREAD_ID/events \
  -H "Authorization: Bearer $TOKEN"

# HITL approve (not the same as user pause resume-run)
curl -s -X POST http://localhost:8000/v1/runs/$THREAD_ID/resume \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve"}'

# Action Recording stub (does NOT claim HG-AUD pass)
curl -s http://localhost:8000/v1/runs/$THREAD_ID/action-recording \
  -H "Authorization: Bearer $TOKEN"
```

**Naming:** `/resume` = HITL · `/resume-run` = continue after user **Pause** · Pause while `interrupted` → **409**.

## Auth

- Missing/invalid Bearer → **401**
- Local **HS256** via `JWT_SECRET` (`.env.example`)
- Google sign-in ready: set `JWT_JWKS_URL` later; claims must resolve `tenant_id` + `sub` → `user_id`

## PostgresSaver ≠ scheduler

`PostgresSaver` checkpoints thread state. It does **not** resume work after the API process dies. Production crash-proof HITL needs Agent Server workers or Temporal (deferred; Ken choice). Unit tests use `MemorySaver` when Postgres is unavailable.

## OpenRouter

If `OPENROUTER_API_KEY` is empty, the gateway returns an offline stub that still:

- enforces tool-capable allowlists
- sets `openrouter_provider.require_parameters=True` on tool routes
- emits `tool_calls` for guard tests

Never put the org key in client payloads (HG-KEY).

## Folder jail (HG-JAIL)

Tool writes must stay under `ALLOWED_ROOT`. Outside → `FolderJailError` / `tool.denied` reason `folder_jail`. This is **not** OS/microVM isolation — do not claim “local = secure”.

## Action Recording / HG-AUD

`GET /v1/runs/{thread_id}/action-recording` returns `schema_version: arpa.action_recording.v0` stub structure.

**W1 does not claim HG-AUD pass.** See `packages/evals/evals/README.md` (red/xfail). Full Must events for GP-1 land W2–W3.

## Tests

```bash
cd /workspace/arpa-scaffold
source .venv/bin/activate   # if created
pip install -e ".[dev]" aiosqlite
pytest -q
```

Coverage intent: `test_auth_tenancy`, `test_hitl_resume` (idempotency + pause 409), `test_tool_fallback_guard`, `test_folder_jail`.

## Specialist tags (G12)

SSE / AR may tag `orchestrator|research|docs_ocr|writer|browser`. Tags are presentation metadata over **one** LangGraph graph — not multi-Bot processes.

## License

Proprietary — Arpa / Ken Agent Platform.
