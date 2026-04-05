"""
core/llm.py — Shared LLM client wrapper (Anthropic Claude primary).

All agents import `call_llm()` from here — never instantiate the Anthropic
client directly in agent code. This centralizes:
  - API key management
  - Model selection (easy to swap or A/B test)
  - Token usage logging
  - Error handling and retries

NOTE: Actual LLM calls are wired up in Prompt 2 (BaseAgent). This file is a
      clean wrapper that agents will use once that's done.
"""

from __future__ import annotations
from typing import Any
import anthropic
from app.config import settings

# Module-level singleton — created once per worker process
_anthropic_client: anthropic.AsyncAnthropic | None = None

# Default model — override per-call if needed
DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 4096


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return (or create) the shared async Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


async def call_llm(
    system: str,
    messages: list[dict[str, Any]],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 1.0,
) -> anthropic.types.Message:
    """
    Send a messages-API request to Claude and return the full response object.

    Args:
        system:     System prompt string
        messages:   List of {role, content} dicts (OpenAI-compatible format)
        model:      Claude model ID — defaults to claude-opus-4-6
        max_tokens: Maximum tokens in the response
        tools:      Optional list of tool definitions (for tool-use agents)
        temperature: Sampling temperature (0-1, default 1.0 per Anthropic recommendation)

    Returns:
        anthropic.types.Message — callers inspect .content[0].text or tool_use blocks

    Usage in agents:
        response = await call_llm(system=SYSTEM_PROMPT, messages=conversation)
        text = response.content[0].text
    """
    client = get_anthropic_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = tools

    response = await client.messages.create(**kwargs)
    return response


async def call_llm_text(
    system: str,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> str:
    """
    Convenience wrapper — returns just the text string from a text response.
    Raises ValueError if the response contains tool_use blocks instead.
    """
    response = await call_llm(system=system, messages=messages, **kwargs)
    first = response.content[0]
    if first.type != "text":
        raise ValueError(f"Expected text response, got: {first.type}")
    return first.text
