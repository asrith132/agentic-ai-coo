"""
core/llm.py — Shared LLM client wrapper (Anthropic Claude).

All agent LLM calls flow through this module. Never instantiate the Anthropic
client directly in agent code. Centralizing here gives us:
  - Single place to swap models or add A/B testing
  - Retry logic with exponential backoff
  - Structured error logging
  - Token usage tracking (future)

Model: claude-sonnet-4-6 (current production model)
"""

from __future__ import annotations
import logging
import sys
import time
from typing import Any, List, Optional

import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # seconds; doubles each retry


def _emit_claude_raw(kind: str, text: str | None) -> None:
    """Stderr is always tied to the uvicorn terminal; logging INFO often is not."""
    logger.info("Claude API response (%s):\n%s", kind, text or "")
    if not settings.log_claude_raw_to_stderr:
        return
    body = text if text else "(no text)"
    print(
        f"\n========== Claude raw ({kind}) ==========\n{body}\n========== /Claude ==========\n",
        file=sys.stderr,
        flush=True,
    )


class LLMClient:
    """
    Synchronous wrapper around the Anthropic Messages API.

    Use `llm.chat()` for simple text exchanges.
    Use `llm.chat_with_tools()` when the agent uses tool calling.
    Use `llm.summarize()` for quick summarization tasks.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model

    # ── Core call with retry ──────────────────────────────────────────────────

    def _call(self, **kwargs: Any) -> anthropic.types.Message:
        """
        Internal: call the Messages API with exponential-backoff retry.
        Retries on RateLimitError and APIStatusError (5xx). Raises on others.
        """
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return self._client.messages.create(**kwargs)
            except anthropic.RateLimitError as exc:
                wait = BASE_RETRY_DELAY * (2 ** attempt)
                logger.warning("Rate limited by Anthropic (attempt %d/%d). Waiting %.1fs.", attempt + 1, MAX_RETRIES, wait)
                time.sleep(wait)
                last_exc = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    wait = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning("Anthropic server error %d (attempt %d/%d). Waiting %.1fs.", exc.status_code, attempt + 1, MAX_RETRIES, wait)
                    time.sleep(wait)
                    last_exc = exc
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    # ── Public interface ──────────────────────────────────────────────────────

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """
        Single-turn text chat. Returns the assistant's text response as a string.

        Args:
            system_prompt: Instructions for the model (agent's system context)
            user_message:  The user / task message
            temperature:   Sampling temperature (0.0–1.0)
            max_tokens:    Max response tokens

        Returns:
            Plain text string of the assistant's response.
        """
        response = self._call(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
        )
        block = response.content[0]
        if block.type != "text":
            raise ValueError(f"Expected text response, got: {block.type}")
        text = block.text
        _emit_claude_raw("chat", text)
        return text

    def chat_conversation(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """
        Multi-turn Messages API call. ``messages`` are Anthropic-shaped dicts with
        ``role`` in (``user``, ``assistant``) and ``content`` str. Must be non-empty.
        Concatenates all text blocks from the assistant turn.
        """
        if not messages:
            raise ValueError("messages must be non-empty")
        response = self._call(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
        )
        text_parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        if not text_parts:
            raise ValueError("Expected at least one text block from Claude")
        out = "".join(text_parts)
        _emit_claude_raw("chat_conversation", out)
        return out

    def chat_with_tools(
        self,
        system_prompt: str,
        user_message: str,
        tools: List[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict[str, Any]:
        """
        Chat with tool use enabled. Returns a dict with the full response.

        Returns a dict with keys:
          - "text":       str | None  — any text content blocks concatenated
          - "tool_calls": list[dict]  — list of {name, input} dicts for each tool_use block
          - "stop_reason": str        — "end_turn" | "tool_use"

        Usage:
            result = llm.chat_with_tools(system, message, tools=[...])
            if result["tool_calls"]:
                for tc in result["tool_calls"]:
                    output = execute_tool(tc["name"], tc["input"])
        """
        response = self._call(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            tools=tools,
            temperature=temperature,
        )

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

        text_out = "\n".join(text_parts) if text_parts else None
        if text_out:
            _emit_claude_raw("chat_with_tools", text_out)
        elif tool_calls:
            names = [tc["name"] for tc in tool_calls]
            logger.info(
                "Claude API response (chat_with_tools): text empty, tool_calls=%s",
                names,
            )
            if settings.log_claude_raw_to_stderr:
                print(
                    f"\n========== Claude raw (chat_with_tools) ==========\n"
                    f"(no text; tool_calls={names})\n========== /Claude ==========\n",
                    file=sys.stderr,
                    flush=True,
                )
        return {
            "text": text_out,
            "tool_calls": tool_calls,
            "stop_reason": response.stop_reason,
        }

    def conversation(
        self,
        system_prompt: str,
        messages: List[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """
        Multi-turn chat. `messages` is a list of {"role": "user"|"assistant", "content": str}.
        Returns the assistant's text response as a string.
        """
        response = self._call(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
        )
        block = response.content[0]
        if block.type != "text":
            raise ValueError(f"Expected text response, got: {block.type}")
        return block.text

    def summarize(self, text: str, max_length: int = 200) -> str:
        """
        Convenience method: summarize `text` in at most `max_length` words.
        Used by agents to produce summaries for notifications and recent_events.
        """
        return self.chat(
            system_prompt=(
                f"You are a concise summarizer. Summarize the provided text in at most "
                f"{max_length} words. Output only the summary — no preamble, no labels."
            ),
            user_message=text,
            temperature=0.3,
            max_tokens=512,
        )


# Module-level singleton — import and use everywhere
llm = LLMClient()
