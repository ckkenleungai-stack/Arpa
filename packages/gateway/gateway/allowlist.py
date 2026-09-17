"""Tool-capable model allowlist (Charlotte #1)."""
from __future__ import annotations

import os

# Default allowlist — models known to support tools / tool_calls.
# Tenants may further restrict; never expand past tool-capable set for tool routes.
_DEFAULT = (
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "google/gemini-2.0-flash-001",
)

# Models that must NOT be used on tool routes (no tool_calls support / known bad fallbacks).
NON_TOOL_MODELS = frozenset(
    {
        "openai/gpt-3.5-turbo-instruct",
        "meta-llama/llama-3-8b-instruct:free",
        "nousresearch/hermes-2-pro-mistral-7b",  # example non-tool for tests
    }
)


def _parse_env_allowlist() -> frozenset[str]:
    raw = os.environ.get("OPENROUTER_ALLOWLIST", "")
    if not raw.strip():
        return frozenset(_DEFAULT)
    return frozenset(m.strip() for m in raw.split(",") if m.strip())


MODEL_ALLOWLIST: frozenset[str] = _parse_env_allowlist()


def is_tool_capable(model_id: str) -> bool:
    if model_id in NON_TOOL_MODELS:
        return False
    return model_id in MODEL_ALLOWLIST


def assert_model_allowed(model_id: str, *, for_tools: bool = True) -> None:
    if for_tools and not is_tool_capable(model_id):
        raise ValueError(
            f"Model {model_id!r} is not on the tool-capable allowlist "
            f"(supported_parameters=tools required). Refusing route."
        )
    if model_id not in MODEL_ALLOWLIST and model_id not in NON_TOOL_MODELS:
        # Still reject unknown models for tool routes
        if for_tools:
            raise ValueError(f"Model {model_id!r} not in OPENROUTER_ALLOWLIST")
