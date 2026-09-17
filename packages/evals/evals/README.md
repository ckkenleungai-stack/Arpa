# Arpa evals (stub)

Golden datasets and gate runners land later (brief ~week 2–4). This package is a **placeholder** so the monorepo layout matches architecture §6.

## HG-AUD — Action Recording hard gate

**Do not mark green.** Until Oliver emits a complete `action-recording.json` for GP-1 (W2–W3) and Felix re-evals:

| Check | W1 scaffold status |
| --- | --- |
| Export API returns `schema_version: arpa.action_recording.v0` | Structural stub only |
| Must root fields present | Stub may satisfy shape; **events completeness for GP-1 path = FAIL** |
| interrupt↔resume pairing | Not fully exercised E2E in scaffold |
| publish.url after Approve | Stub path only |
| Scrub secrets | Helper present; negative fixture Later |
| Cross-tenant export denied | Covered by tenancy tests on conversations |

**HG-AUD = red / xfail until evidence exists.** See:

- `/workspace/architecture/action-recording-schema-v0.md` §2A
- `/workspace/product/spec/AC-MUST-v1.md` AC-GP1-08 / AC-HG-JAIL

## HG-JAIL

Folder jail unit tests live in `tests/test_folder_jail.py`. Writes outside `ALLOWED_ROOT` must fail with `folder_jail` reason.

## Honesty

- No fake greens in CI for HG-AUD.
- Local = workspace FS + folder jail ≠ OS/microVM isolation (HG-COPY).
- PostgresSaver ≠ production scheduler (crash resume deferred).
