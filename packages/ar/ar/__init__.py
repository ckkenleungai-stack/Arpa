"""Action Recording emitter (schema v0)."""

from ar.emitter import (
    ActionRecordingEmitter,
    IncompleteRecordingError,
    ScrubError,
    build_stub_recording,
    scrub_value,
    secret_leaks_in,
)
from ar.types import (
    SCHEMA_VERSION,
    ActionRecordingV0,
    REQUIRED_ROOT_FIELDS,
    missing_required_root,
)

__all__ = [
    "SCHEMA_VERSION",
    "ActionRecordingV0",
    "REQUIRED_ROOT_FIELDS",
    "missing_required_root",
    "ActionRecordingEmitter",
    "build_stub_recording",
    "scrub_value",
    "secret_leaks_in",
    "ScrubError",
    "IncompleteRecordingError",
]
