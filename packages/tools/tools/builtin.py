"""First-party tools — non-gated + gated stubs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tools.folder_jail import FolderJailError, assert_write_allowed, get_allowed_root
from tools.sensitive import is_sensitive, specialist_for


@dataclass
class ToolResult:
    name: str
    ok: bool
    result: Any
    status: str  # ok | denied | error
    specialist: str
    reason: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    gated: bool
    specialist: str
    handler: Callable[..., ToolResult]


def _web_fetch_readonly(url: str = "https://example.com", **_: Any) -> ToolResult:
    # Offline-safe stub — no real network in unit tests
    return ToolResult(
        name="web_fetch_readonly",
        ok=True,
        result={"url": url, "excerpt": f"[stub fetch] content from {url}"},
        status="ok",
        specialist="research",
    )


def _search_index_query(query: str = "", **_: Any) -> ToolResult:
    return ToolResult(
        name="search_index_query",
        ok=True,
        result={"query": query, "hits": []},
        status="ok",
        specialist="research",
    )


def _pdf_extract(path: str = "", **_: Any) -> ToolResult:
    return ToolResult(
        name="pdf_extract",
        ok=True,
        result={"path": path, "text": "[stub pdf text]"},
        status="ok",
        specialist="docs_ocr",
    )


def _ocr_image(path: str = "", **_: Any) -> ToolResult:
    return ToolResult(
        name="ocr_image",
        ok=True,
        result={"path": path, "text": "[stub ocr]"},
        status="ok",
        specialist="docs_ocr",
    )


def _draft_compose(plan: str = "", sources: list | None = None, **_: Any) -> ToolResult:
    body = f"<html><body><h1>Draft</h1><p>{plan or 'Research summary'}</p></body></html>"
    return ToolResult(
        name="draft_compose",
        ok=True,
        result={"html": body},
        status="ok",
        specialist="writer",
    )


def _workspace_write(path: str, content: str = "", **_: Any) -> ToolResult:
    """Write under ALLOWED_ROOT only — folder jail."""
    try:
        target = assert_write_allowed(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(
            name="workspace_write",
            ok=True,
            result={"path": str(target), "bytes": len(content.encode())},
            status="ok",
            specialist="writer",
        )
    except FolderJailError as exc:
        return ToolResult(
            name="workspace_write",
            ok=False,
            result={},
            status="denied",
            specialist="writer",
            reason="folder_jail",
        )


def _workspace_write_outside(path: str, content: str = "", **_: Any) -> ToolResult:
    """Sensitive: attempts write that may be outside jail — always jail-checked."""
    try:
        target = assert_write_allowed(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(
            name="workspace_write_outside",
            ok=True,
            result={"path": str(target)},
            status="ok",
            specialist="docs_ocr",
        )
    except FolderJailError:
        return ToolResult(
            name="workspace_write_outside",
            ok=False,
            result={},
            status="denied",
            specialist="docs_ocr",
            reason="folder_jail",
        )


def _browser_navigate(url: str = "", **_: Any) -> ToolResult:
    return ToolResult(
        name="browser_navigate",
        ok=True,
        result={"url": url, "note": "stub navigate — HITL gated"},
        status="ok",
        specialist="browser",
    )


def _http_request_mutating(url: str = "", method: str = "POST", **_: Any) -> ToolResult:
    return ToolResult(
        name="http_request_mutating",
        ok=True,
        result={"url": url, "method": method},
        status="ok",
        specialist="browser",
    )


def _send_email(to: str = "", subject: str = "", **_: Any) -> ToolResult:
    return ToolResult(
        name="send_email",
        ok=True,
        result={"to": to, "subject": subject, "sent": True},
        status="ok",
        specialist="orchestrator",
    )


def _notify_webhook(url: str = "", **_: Any) -> ToolResult:
    return ToolResult(
        name="notify_webhook",
        ok=True,
        result={"url": url, "delivered": True},
        status="ok",
        specialist="orchestrator",
    )


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "web_fetch_readonly": ToolSpec(
        "web_fetch_readonly", "Read-only URL fetch", False, "research", _web_fetch_readonly
    ),
    "search_index_query": ToolSpec(
        "search_index_query", "Search index query", False, "research", _search_index_query
    ),
    "pdf_extract": ToolSpec("pdf_extract", "Extract PDF text", False, "docs_ocr", _pdf_extract),
    "ocr_image": ToolSpec("ocr_image", "OCR image", False, "docs_ocr", _ocr_image),
    "draft_compose": ToolSpec(
        "draft_compose", "Compose HTML draft", False, "writer", _draft_compose
    ),
    "workspace_write": ToolSpec(
        "workspace_write", "Write under allowed root", False, "writer", _workspace_write
    ),
    "workspace_write_outside": ToolSpec(
        "workspace_write_outside",
        "Write that may leave jail (gated)",
        True,
        "docs_ocr",
        _workspace_write_outside,
    ),
    "browser_navigate": ToolSpec(
        "browser_navigate", "Navigate browser", True, "browser", _browser_navigate
    ),
    "http_request_mutating": ToolSpec(
        "http_request_mutating", "Mutating HTTP", True, "browser", _http_request_mutating
    ),
    "send_email": ToolSpec("send_email", "Send email", True, "orchestrator", _send_email),
    "notify_webhook": ToolSpec(
        "notify_webhook", "Notify webhook", True, "orchestrator", _notify_webhook
    ),
}


def get_tool(name: str) -> ToolSpec:
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}")
    return TOOL_REGISTRY[name]


def list_tools(*, gated: bool | None = None) -> list[ToolSpec]:
    specs = list(TOOL_REGISTRY.values())
    if gated is None:
        return specs
    return [s for s in specs if s.gated is gated]


def run_tool(name: str, **kwargs: Any) -> ToolResult:
    spec = get_tool(name)
    return spec.handler(**kwargs)
