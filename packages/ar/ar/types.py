"""Arpa Action Recording — stub types v0 (W0).

Schema authority: action-recording-schema-v0.md
Owners: Theodore (schema) · Oliver emit W2–W3 · Felix HG-AUD
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, NotRequired, TypedDict


SCHEMA_VERSION = "arpa.action_recording.v0"


class RunStatus(str, Enum):
    running = "running"
    interrupted = "interrupted"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EventType(str, Enum):
    run_started = "run.started"
    status = "status"
    specialist = "specialist"
    tool_requested = "tool.requested"
    tool_completed = "tool.completed"
    tool_denied = "tool.denied"
    llm = "llm"
    interrupt = "interrupt"
    resume = "resume"
    publish = "publish"
    error = "error"
    user_pause = "user.pause"
    user_stop = "user.stop"


class HitlKind(str, Enum):
    sensitive_tool = "sensitive_tool"
    publish = "publish"


class HitlDecision(str, Enum):
    approve = "approve"
    reject = "reject"
    edit = "edit"


# --- Required root fields for HG-AUD (missing any = FAIL) ---
REQUIRED_ROOT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "recording_id",
    "thread_id",
    "tenant_id",
    "user_id",
    "workflow_id",
    "created_at",
    "exported_at",
    "status_at_export",
    "events",
    "hitl",
    "artifacts",
    "integrity",
)


class ActionEvent(TypedDict):
    seq: int
    at: str
    type: str
    specialist: str | None
    summary: str
    payload: dict[str, Any]


class HitlEntry(TypedDict):
    pending_action_id: str
    kind: str
    opened_at: str
    closed_at: NotRequired[str]
    decision: NotRequired[str]
    actor_user_id: NotRequired[str]
    edits_applied: bool
    side_effect_executed: bool
    idempotency_key: str


class PublishBlock(TypedDict):
    attempted: bool
    approved_at: NotRequired[str]
    url: NotRequired[str]
    visibility: NotRequired[str]
    duplicate_suppressed: bool
    html_sha256: NotRequired[str]


class ArtifactsBlock(TypedDict):
    draft_html_sha256: str | None
    published_url: str | None
    published_html_sha256: str | None


class IntegrityBlock(TypedDict):
    event_count: int
    events_sha256: str | None
    scrubbed: bool


class ActionRecordingV0(TypedDict):
    schema_version: Literal["arpa.action_recording.v0"]
    recording_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    workflow_id: str
    created_at: str
    exported_at: str
    status_at_export: str
    product: dict[str, Any]
    sources: list[Any]
    interview: dict[str, Any]
    plan_summary: Any
    events: list[ActionEvent]
    hitl: list[HitlEntry]
    publish: PublishBlock | None
    artifacts: ArtifactsBlock
    integrity: IntegrityBlock


def missing_required_root(doc: dict[str, Any]) -> list[str]:
    """Return missing structural Must root fields — non-empty => FAIL HG-AUD.

    Path Must (events, sources for GP-1, publish.url, jail deny) are separate;
    see action-recording-schema-v0.md §2C.
    """
    return [k for k in REQUIRED_ROOT_FIELDS if k not in doc]
