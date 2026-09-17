"""ChatOpenRouter helpers — openrouter_provider.require_parameters (not bare provider)."""
from __future__ import annotations

import os
from typing import Any, Sequence

from gateway.allowlist import assert_model_allowed, is_tool_capable


def openrouter_provider_require_parameters(
    *,
    order: Sequence[str] | None = None,
    allow_fallbacks: bool = True,
) -> dict[str, Any]:
    """Build openrouter_provider kwargs for tool routes.

    Critical: field name is ``openrouter_provider``, NOT bare ``provider``.
    ``require_parameters=True`` prevents silent fallback to non-tool models.
    """
    cfg: dict[str, Any] = {
        "require_parameters": True,
        "allow_fallbacks": allow_fallbacks,
    }
    if order:
        cfg["order"] = list(order)
    return cfg


def build_chat_openrouter(
    *,
    tools: bool = True,
    primary: str | None = None,
    fallbacks: Sequence[str] | None = None,
    api_key: str | None = None,
) -> Any:
    """Construct ChatOpenRouter with primary + models fallback list.

    Returns a ChatOpenRouter instance when langchain-openrouter is installed
    and OPENROUTER_API_KEY is set; otherwise returns a lightweight stub used
    by unit tests / offline smoke.
    """
    primary_model = primary or os.environ.get(
        "OPENROUTER_PRIMARY_MODEL", "openai/gpt-4o-mini"
    )
    raw_fb = fallbacks
    if raw_fb is None:
        env_fb = os.environ.get("OPENROUTER_FALLBACK_MODELS", "")
        raw_fb = [m.strip() for m in env_fb.split(",") if m.strip()] if env_fb else []

    if tools:
        assert_model_allowed(primary_model, for_tools=True)
        for m in raw_fb:
            if not is_tool_capable(m):
                raise ValueError(
                    f"Fallback model {m!r} is not tool-capable; "
                    "refusing to configure silent non-tool fallback"
                )

    key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
    provider = openrouter_provider_require_parameters() if tools else {"require_parameters": False}

    if not key:
        return _OfflineChatStub(
            model=primary_model,
            models=list(raw_fb),
            openrouter_provider=provider,
            tools_enabled=tools,
        )

    try:
        from langchain_openrouter import ChatOpenRouter  # type: ignore
    except ImportError:
        return _OfflineChatStub(
            model=primary_model,
            models=list(raw_fb),
            openrouter_provider=provider,
            tools_enabled=tools,
        )

    kwargs: dict[str, Any] = {
        "model": primary_model,
        "api_key": key,
        "openrouter_provider": provider,
    }
    if raw_fb:
        kwargs["models"] = list(raw_fb)
    return ChatOpenRouter(**kwargs)


class _OfflineChatStub:
    """Deterministic stub when OpenRouter key/package unavailable."""

    def __init__(
        self,
        *,
        model: str,
        models: list[str],
        openrouter_provider: dict[str, Any],
        tools_enabled: bool,
    ) -> None:
        self.model = model
        self.models = models
        self.openrouter_provider = openrouter_provider
        self.tools_enabled = tools_enabled
        self._bound_tools: list[Any] = []

    def bind_tools(self, tools: list[Any]) -> "_OfflineChatStub":
        clone = _OfflineChatStub(
            model=self.model,
            models=self.models,
            openrouter_provider=self.openrouter_provider,
            tools_enabled=self.tools_enabled,
        )
        clone._bound_tools = list(tools)
        return clone

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        # Minimal AIMessage-like for graph smoke without network
        from types import SimpleNamespace

        content = "Offline stub plan: fetch sources then draft."
        tool_calls: list[dict[str, Any]] = []
        if self.tools_enabled and self._bound_tools:
            # Emit one tool_call so tool-route tests can assert presence
            name = getattr(self._bound_tools[0], "name", None) or "web_fetch_readonly"
            tool_calls = [
                {
                    "id": "stub_tc_1",
                    "name": name,
                    "args": {"url": "https://example.com"},
                }
            ]
        return SimpleNamespace(content=content, tool_calls=tool_calls)
