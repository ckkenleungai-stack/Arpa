"""Sensitive tool allowlist — HITL gated (architecture §3A)."""
from __future__ import annotations

SENSITIVE_TOOL_IDS: frozenset[str] = frozenset(
    {
        "browser_navigate",
        "http_request_mutating",
        "send_email",
        "notify_webhook",
        "workspace_write_outside",
    }
)

# G12 specialist chip tags (metadata only — not separate agents)
TOOL_SPECIALIST: dict[str, str] = {
    "web_fetch_readonly": "research",
    "search_index_query": "research",
    "pdf_extract": "docs_ocr",
    "ocr_image": "docs_ocr",
    "draft_compose": "writer",
    "workspace_write": "writer",
    "browser_navigate": "browser",
    "http_request_mutating": "browser",
    "send_email": "orchestrator",
    "notify_webhook": "orchestrator",
    "workspace_write_outside": "docs_ocr",
}


def is_sensitive(tool_id: str) -> bool:
    return tool_id in SENSITIVE_TOOL_IDS


def specialist_for(tool_id: str) -> str:
    return TOOL_SPECIALIST.get(tool_id, "orchestrator")
