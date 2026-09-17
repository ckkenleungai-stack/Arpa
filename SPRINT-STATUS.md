# Arpa W1 — Sprint Status (Oliver)

| Field | Value |
| --- | --- |
| Time (HKT) | 2026-09-18 (landed on GitHub) |
| Scaffold | this repo (single tree — do not fork) |
| Branch | `cursor/w1-scaffold-fa2a` (requested `oliver/w1-scaffold`; Cloud Agent naming required `cursor/…-fa2a`) |
| PR URL | https://github.com/ckkenleungai-stack/Arpa/pull/1 |
| CloudAgent | landed via Cursor Cloud Agent unpack of Oliver tarball |

## Tests (this land)

```
cd /workspace && python3 -m pytest -q
# → 23 passed, 1 warning
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

1. **HG-AUD:** Stays red until emit matches checklist + Felix sample (no fake green).
2. Live OpenRouter / LangSmith optional; local path uses offline stub + tracing skip.

## Next

1. Felix HG-AUD against a real GP-1 export sample (W2–W3)
2. P1 remaining: sources[] on GP-1 path, eval evidence file, interrupt↔resume pairing completeness, `?format=md`

