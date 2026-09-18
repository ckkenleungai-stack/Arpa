# AR P0 Patch Notes — 2026-09-18 (HKT)

Authority: `/workspace/architecture/AR-REVIEW-NOTES.md`, `AR-EMIT-CHECKLIST.md`,
`action_recording_types_v0.py`, `action-recording-schema-v0.md`.

Scaffold: **`/workspace/arpa-scaffold` only** (no second fork).

## What landed

| P0 | Change |
| --- | --- |
| P0-1 tool.* | `tools_node` / `hitl_gate_node` emit `tool.requested` then `tool.completed` \| `tool.denied` via `ar.runtime` (digests, not raw args). Nodes take `RunnableConfig` so `thread_id` injects. |
| P0-2 jail → AR | On `ToolResult.status==denied` + `reason==folder_jail`, emit `tool.denied` with `payload={tool_id, reason: "folder_jail"}`. |
| P0-3 scrub fail-closed | `integrity.scrubbed` starts False; set True only after `secret_leaks_in` pass. Hard-code removed. GET raises 500 on `ScrubError`. |
| P0-4 missing roots | `get_action_recording` calls `missing_required_root` / `export(fail_closed=True)` → 500 if nonempty. |
| P0-5 hitl[] | Every gate close (approve/reject/edit for `sensitive_tool` **and** `publish`) appends `hitl[]`. |
| P0-6 re-Approve | Ledger hit → set `publish.duplicate_suppressed=true`, append hitl with `side_effect_executed=false`, **no** re-exec. |
| P0-7 artifacts | Draft/published HTML sha256 filled when available (bonus). |
| P0-8 persist | `action_events` table + Alembic `002_action_events`; flush after create/resume/pause/stop; GET hydrates after in-memory clear. Stop inventing stub timelines for owned threads that already ran. |

## Nice-to-haves

- Synced `packages/ar/ar/types.py` from architecture types (owners docstring + §2C).
- Tenancy test on `GET .../action-recording`.
- Jail deny appears in AR export test.
- Persist-after-clear test; reject hitl row; duplicate_suppressed; scrub unit test.

## Honesty

- No HG-AUD green claims in README/evals.
- `_scaffold_note` still says Felix must re-eval a GP-1 sample.

## How to test

```bash
cd /workspace/arpa-scaffold
source .venv/bin/activate
export PYTHONPATH="packages/control_plane:packages/workflows:packages/gateway:packages/tools:packages/db:packages/ar:packages/evals"
export ALLOWED_ROOT="$(pwd)/workspace_data"
pytest -q
```
