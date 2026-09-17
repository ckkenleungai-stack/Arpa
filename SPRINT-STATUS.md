# Arpa W1 — Sprint Status (Oliver)

| Field | Value |
| --- | --- |
| Time (HKT) | 2026-09-18 02:19 HKT |
| Scaffold | `/workspace/arpa-scaffold` (single tree — do not fork) |
| Branch target | `oliver/w1-scaffold` |
| PR URL | **None yet** |
| CloudAgent | `bc-f46b2195-1c08-58f9-9581-132a1b73c44d` → **error** (empty transcript); relaunch pending after P0 AR patches |

## Tests (pre–P0-AR patch)

```
cd /workspace/arpa-scaffold && source .venv/bin/activate
export PYTHONPATH="packages/control_plane:packages/workflows:packages/gateway:packages/tools:packages/db:packages/ar:packages/evals"
export ALLOWED_ROOT="$(pwd)/workspace_data"
pytest -q
# → 23 passed, 1 warning (P0 AR patch set applied)
```

## W1 completeness (baseline)

| Item | Status |
| --- | --- |
| FastAPI `/health` + compose (api+postgres) | Done |
| Conversations + Alembic + JWT HS256 (JWKS stub) | Done |
| LangGraph `research_publish_v1` + G12 tags | Done |
| HITL `sensitive_tool`\|`publish`; Pause≠HITL | Done |
| Folder jail (tool layer) | Done |
| Guard tests (tenancy/HITL/tool_calls/jail) | Done (15) |
| AR GET endpoint + persisted `action_events` | P0 complete; HG-AUD remains RED pending real sample |
| Live OpenRouter | Offline stub if no key |
| LangSmith | Graceful skip only |
| HG-AUD | **RED** — do not claim green |

## In flight (Ken sprint)

Theodore P0 AR patches applied on this tree (see `docs/AR-P0-PATCH-NOTES.md`):

1. Emit `tool.*` from graph/`run_tool`
2. Jail deny → AR `tool.denied` + `reason=folder_jail`
3. `integrity.scrubbed` fail-closed
4. `hitl[]` on reject + sensitive approve; re-Approve → `duplicate_suppressed`
5. Persist `action_events` (was in-memory only)

## Blockers

1. **PR:** CloudAgent errored; no commits pushed to GitHub yet. Relaunch/push after P0 patches.
2. **HG-AUD:** Stays red until emit matches checklist + Felix sample.

## Next

1. Relaunch CloudAgent on `https://github.com/ckkenleungai-stack/Arpa` branch `oliver/w1-scaffold`
2. Update this file with PR URL + final test count for Liam’s morning brief

