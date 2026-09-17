# AR Emit Checklist — Oliver (post-scaffold PR)

| Field | Value |
| --- | --- |
| For | Oliver (emit) · Felix (HG-AUD) · Kai (later) |
| Schema | `/workspace/architecture/action-recording-schema-v0.md` |
| Types | `/workspace/architecture/action_recording_types_v0.py` |
| Due | Export sample **by W3** · schema **W0 done** |
| Rule | Missing any Must field = **FAIL HG-AUD** |

---

## 1. Schema fields → emit (Must)

| Emit | Source |
| --- | --- |
| Root Must fields | `REQUIRED_ROOT_FIELDS` in `action_recording_types_v0.py` — use `missing_required_root(doc)` before return |
| `schema_version` | Always `arpa.action_recording.v0` |
| `events[]` | Append-only as run progresses; `seq` strictly increasing |
| Must event types when path hits them | `run.started`, `status`, `tool.*`, `interrupt`, `resume`, `publish`, `user.pause`/`stop`, `error` |
| `hitl[]` | One row per gate; `idempotency_key`; re-Approve → `duplicate_suppressed` / single side effect |
| `publish` | Set on Approve path; `url` required if published; reject → no public URL |
| `artifacts` | draft/published hashes + `published_url` |
| `integrity.scrubbed` | `true` only after scrub pass |
| Digests | Store `args_digest` / `result_digest` — not raw secrets |
| Folder jail | Outside-root write → `tool.denied` with `payload.reason = "folder_jail"` |

**Do not ship** if `missing_required_root` nonempty or scrub fails.

---

## 2. Endpoint (Must)

| Item | Spec |
| --- | --- |
| Method/path | `GET /v1/runs/{thread_id}/action-recording` |
| Authz | Same `conversations` tenancy as §3A — non-owner → **404/403** |
| Body | Full `action-recording.json` object |
| Optional | `?format=md` → human summary (Should; not HG-AUD Must until Ken says) |
| Persist | Append-only `action_events` (or equiv.) while graph/API runs **[ASSUMPTION]** |

Wire from run lifecycle: create → stream/status → tools/HITL → publish/stop → export reads same log.

---

## 3. Felix HG-AUD handoff

| Oliver delivers | Felix checks |
| --- | --- |
| Working export on a GP-1-like thread | File/API returns JSON |
| Sample under `eval/evidence/.../outputs/action-recording.json` (or pre-GitHub `/workspace/product/eval-evidence/...`) | `schema_version` + Must fields |
| Fixture-friendly scrub (no keys in payload) | Secret-leak → reject |
| Incomplete path still validates fail-closed | Missing field → FAIL |
| Jail denial exercised once in a sample run | `tool.denied` + `folder_jail` |

**Void rule:** publish-path fix after a sample → old AR void; new export + Felix re-eval required.

---

## 4. Done when

- [ ] Endpoint ownership-checked and returns v0 JSON  
- [ ] `missing_required_root` == `[]` on happy GP-1 path  
- [ ] Scrub + jail denial covered  
- [ ] Felix HG-AUD reds can go green against a real export sample  
- [ ] Liam notified  

**Kai later:** can take emit ownership; until then Oliver owns bandwidth (do not slip past W3 if still red).
