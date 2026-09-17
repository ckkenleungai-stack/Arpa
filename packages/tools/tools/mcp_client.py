"""MCP client wiring stub (v1 hooks only — full product Later).

Credentials: pass as headers/_meta, never URL query params.
"""
from __future__ import annotations

from typing import Any


class McpClientStub:
    """Placeholder until tenant-scoped MCP servers are configured."""

    def __init__(self, *, server_url: str, headers: dict[str, str] | None = None) -> None:
        self.server_url = server_url
        self.headers = headers or {}

    async def list_tools(self) -> list[dict[str, Any]]:
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            f"MCP tool {name!r} not wired in W1 scaffold (server={self.server_url})"
        )
