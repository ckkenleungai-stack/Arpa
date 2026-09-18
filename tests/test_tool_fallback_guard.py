"""Charlotte #1 — allowlist + require_parameters; assert tool_calls on tool routes."""
from __future__ import annotations

import pytest

from gateway.allowlist import NON_TOOL_MODELS, assert_model_allowed, is_tool_capable
from gateway.openrouter import build_chat_openrouter, openrouter_provider_require_parameters


def test_require_parameters_field_name():
    cfg = openrouter_provider_require_parameters()
    assert cfg["require_parameters"] is True
    # Must use openrouter_provider wrapping, not bare provider key at this helper layer
    assert "require_parameters" in cfg


def test_non_tool_model_rejected():
    bad = next(iter(NON_TOOL_MODELS))
    assert not is_tool_capable(bad)
    with pytest.raises(ValueError, match="tool-capable|allowlist"):
        assert_model_allowed(bad, for_tools=True)


def test_fallback_list_rejects_non_tool():
    bad = next(iter(NON_TOOL_MODELS))
    with pytest.raises(ValueError, match="not tool-capable"):
        build_chat_openrouter(
            tools=True,
            primary="openai/gpt-4o-mini",
            fallbacks=[bad],
            api_key="",  # offline
        )


def test_tool_route_stub_emits_tool_calls():
    """Every published tool route must surface tool_calls (offline stub asserts shape)."""
    llm = build_chat_openrouter(tools=True, api_key="")
    bound = llm.bind_tools(
        [type("T", (), {"name": "web_fetch_readonly"})()]
    )
    msg = bound.invoke([{"role": "user", "content": "fetch example.com"}])
    assert hasattr(msg, "tool_calls")
    assert msg.tool_calls, "tool_calls must not be silently empty on tool routes"
    assert msg.tool_calls[0]["name"]
    # Provider config present on stub
    assert llm.openrouter_provider.get("require_parameters") is True
