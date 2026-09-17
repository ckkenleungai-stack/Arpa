"""Action Recording emitter — append-only events; scrub fail-closed on export.

Honesty: export structure alone does NOT claim HG-AUD pass. Path Must events
(tool.*, jail deny, full hitl) must still be emitted by callers.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from ar.types import SCHEMA_VERSION, ActionEvent, ActionRecordingV0, missing_required_root

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|authorization|bearer|password|otp|cookie)\s*[:=]\s*\S+"),
    re.compile(r"sk-[a-zA-Z0-9]{8,}"),
    re.compile(r"(?i)openrouter[_-]?api[_-]?key"),
]


class ScrubError(ValueError):
    """Raised when export still contains secret-like material after scrub."""


class IncompleteRecordingError(ValueError):
    """Raised when missing_required_root is nonempty."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pat in _SECRET_PATTERNS:
            out = pat.sub("***", out)
        return out
    if isinstance(value, dict):
        return {k: scrub_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_value(v) for v in value]
    return value


def secret_leaks_in(value: Any) -> list[str]:
    """Return human-readable leak descriptions if secret-like substrings remain."""
    leaks: list[str] = []

    def walk(v: Any, path: str) -> None:
        if isinstance(v, str):
            for pat in _SECRET_PATTERNS:
                if pat.search(v):
                    leaks.append(f"{path}: matches {pat.pattern!r}")
                    break
        elif isinstance(v, dict):
            for k, child in v.items():
                walk(child, f"{path}.{k}" if path else k)
        elif isinstance(v, list):
            for i, child in enumerate(v):
                walk(child, f"{path}[{i}]")

    walk(value, "")
    return leaks


class ActionRecordingEmitter:
    """Append-only event log for a thread (in-memory + optional DB hydrate)."""

    def __init__(
        self,
        *,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        workflow_id: str = "research_publish_v1",
        recording_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        self.recording_id = recording_id or str(uuid.uuid4())
        self.thread_id = thread_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.workflow_id = workflow_id
        self.created_at = created_at or _utcnow_iso()
        self.events: list[ActionEvent] = []
        self.hitl: list[dict[str, Any]] = []
        self.publish: dict[str, Any] | None = None
        self.sources: list[Any] = []
        self.interview: dict[str, Any] = {"answers": [], "skipped": True}
        self.plan_summary: Any = None
        self.artifacts: dict[str, Any] = {
            "draft_html_sha256": None,
            "published_url": None,
            "published_html_sha256": None,
        }
        self._seq = 0

    def emit(
        self,
        event_type: str,
        *,
        summary: str,
        payload: dict[str, Any] | None = None,
        specialist: str | None = None,
    ) -> ActionEvent:
        self._seq += 1
        ev: ActionEvent = {
            "seq": self._seq,
            "at": _utcnow_iso(),
            "type": event_type,
            "specialist": specialist,
            "summary": scrub_value(summary) if isinstance(summary, str) else summary,
            "payload": scrub_value(payload or {}),
        }
        self.events.append(ev)
        return ev

    def load_events(self, events: list[dict[str, Any]]) -> None:
        """Hydrate from persisted rows (seq preserved)."""
        self.events = []
        max_seq = 0
        for e in sorted(events, key=lambda x: int(x.get("seq") or 0)):
            seq = int(e.get("seq") or 0)
            max_seq = max(max_seq, seq)
            self.events.append(
                {
                    "seq": seq,
                    "at": e.get("at") or _utcnow_iso(),
                    "type": e.get("type") or "status",
                    "specialist": e.get("specialist"),
                    "summary": e.get("summary") or "",
                    "payload": e.get("payload") or {},
                }
            )
        self._seq = max_seq

    def export(self, *, status_at_export: str, fail_closed: bool = True) -> ActionRecordingV0:
        """Build export doc. Scrub fail-closed: scrubbed=True only after validation.

        When fail_closed=True (default for GET): raise ScrubError / IncompleteRecordingError
        rather than shipping an unsanitized or structurally incomplete document.
        """
        # Re-scrub events defensively before integrity check
        scrubbed_events = [scrub_value(dict(e)) for e in self.events]
        publish = scrub_value(self.publish) if self.publish else None
        hitl = [scrub_value(dict(h)) for h in self.hitl]
        artifacts = {
            "draft_html_sha256": self.artifacts.get("draft_html_sha256"),
            "published_url": (publish or {}).get("url")
            if publish
            else self.artifacts.get("published_url"),
            "published_html_sha256": self.artifacts.get("published_html_sha256"),
        }
        if publish and publish.get("html_sha256"):
            artifacts["published_html_sha256"] = publish.get("html_sha256")

        events_blob = json.dumps(scrubbed_events, sort_keys=True, default=str)
        events_sha = hashlib.sha256(events_blob.encode()).hexdigest()

        doc: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "recording_id": self.recording_id,
            "thread_id": self.thread_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workflow_id": self.workflow_id,
            "created_at": self.created_at,
            "exported_at": _utcnow_iso(),
            "status_at_export": status_at_export,
            "product": {
                "name": "Arpa",
                "bots_presented": ["general", "research", "docs_ocr", "writer", "browser"],
                "specialist_tags_used": [
                    "orchestrator",
                    "research",
                    "docs_ocr",
                    "writer",
                    "browser",
                ],
            },
            "sources": scrub_value(list(self.sources)),
            "interview": scrub_value(dict(self.interview)),
            "plan_summary": scrub_value(self.plan_summary),
            "events": scrubbed_events,
            "hitl": hitl,
            "publish": publish,
            "artifacts": artifacts,
            "integrity": {
                "event_count": len(scrubbed_events),
                "events_sha256": events_sha,
                # Fail-closed: never hard-code True — set only after validation below
                "scrubbed": False,
            },
        }

        missing = missing_required_root(doc)
        if missing:
            if fail_closed:
                raise IncompleteRecordingError(
                    f"missing_required_root={missing}"
                )
            # still attach note for stub paths
            doc["_scaffold_note"] = f"incomplete roots: {missing}"

        leaks = secret_leaks_in(doc)
        if leaks:
            if fail_closed:
                raise ScrubError(f"secret-like material remains after scrub: {leaks[:5]}")
            doc["integrity"]["scrubbed"] = False
        else:
            doc["integrity"]["scrubbed"] = True

        return doc  # type: ignore[return-value]


def build_stub_recording(
    *,
    thread_id: str,
    tenant_id: str,
    user_id: str,
    workflow_id: str = "research_publish_v1",
    status: str = "running",
    events: list[dict[str, Any]] | None = None,
    hitl: list[dict[str, Any]] | None = None,
    publish: dict[str, Any] | None = None,
    plan_summary: Any = None,
    sources: list[Any] | None = None,
) -> dict[str, Any]:
    """Build a schema-shaped stub for cold GET when no persisted events exist.

    Honesty: structural stub only. Do **not** invent fake tool/HITL history for
    owned threads that already ran — callers should prefer DB hydrate first.
    """
    emitter = ActionRecordingEmitter(
        thread_id=thread_id,
        tenant_id=tenant_id,
        user_id=user_id,
        workflow_id=workflow_id,
    )
    if sources:
        emitter.sources = sources
    if plan_summary is not None:
        emitter.plan_summary = plan_summary
    if events:
        for e in events:
            emitter.emit(
                e.get("type", "status"),
                summary=e.get("summary", ""),
                payload=e.get("payload"),
                specialist=e.get("specialist"),
            )
    else:
        emitter.emit("run.started", summary="stub run started", payload={"input_ref": "stub"})
        emitter.emit(
            "status",
            summary=f"status → {status}",
            payload={"from": "running", "to": status},
            specialist="orchestrator",
        )
    if hitl:
        emitter.hitl = hitl
    if publish:
        emitter.publish = publish
    # Stub path: fail_closed=False so structural demo still returns; integrity
    # still reflects real scrub outcome (not hard-coded).
    doc = emitter.export(status_at_export=status, fail_closed=False)
    out = dict(doc)
    out["_scaffold_note"] = (
        "Cold stub export (no persisted action_events). "
        "Do not claim HG-AUD pass. "
        f"missing_required_root={missing_required_root(out)}"
    )
    return out
