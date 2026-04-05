"""
core/context.py — Global Context read/write helpers.

The Global Context is a single versioned row every agent reads at runtime.
Write access is tightly controlled — agents can only update the fields they
own. Unauthorized writes raise PermissionError immediately.

WRITE PERMISSION MAP
  company_profile               → user only (no agent writes)
  target_customer               → user only; research agent creates an approval proposal
  business_state.key_metrics    → pm, finance
  business_state.active_priorities → pm
  business_state.runway_months  → finance
  business_state.monthly_burn   → finance
  brand_voice                   → user only; marketing agent creates an approval proposal
  competitive_landscape         → research
  recent_events                 → ALL agents (append-only, capped at 50)
"""

from __future__ import annotations
from typing import Any
from datetime import datetime, timezone

from app.db.supabase_client import get_client
from app.schemas.context import GlobalContext

# ── Write permission map ──────────────────────────────────────────────────────
# Key:   field path (top-level or "top.sub")
# Value: list of agent names allowed to write; "__all__" means any agent

_WRITE_PERMISSIONS: dict[str, list[str]] = {
    # Top-level fields
    "company_profile":                  ["__all__"],  # all agents can fill from chat
    "target_customer":                  [],           # user only (research proposes via approval)
    "brand_voice":                      [],           # user only (marketing proposes via approval)
    "competitive_landscape":            ["research"],
    "recent_events":                    ["__all__"],

    # Nested business_state subfields
    "business_state.active_priorities": ["pm"],
    "business_state.runway_months":     ["finance"],
    "business_state.monthly_burn":      ["finance"],
    "business_state.key_metrics":       ["pm", "finance"],
    "business_state.phase":             ["pm"],
    "business_state.team_size":         [],           # user only
    "business_state.last_updated":      ["pm", "finance", "dev_activity"],
}

RECENT_EVENTS_CAP = 50


def _check_permission(field: str, agent_name: str) -> None:
    """
    Raise PermissionError if `agent_name` is not allowed to write `field`.
    Accepts both exact matches (e.g. "competitive_landscape") and nested
    paths (e.g. "business_state.runway_months").
    """
    allowed = _WRITE_PERMISSIONS.get(field)
    if allowed is None:
        # Unlisted field — deny by default
        raise PermissionError(
            f"Agent '{agent_name}' attempted to write unknown field '{field}'. "
            "Add it to _WRITE_PERMISSIONS in core/context.py to allow."
        )
    if "__all__" in allowed:
        return
    if agent_name not in allowed:
        raise PermissionError(
            f"Agent '{agent_name}' does not have write permission for '{field}'. "
            f"Allowed agents: {allowed or ['user only']}"
        )


def _get_raw_row() -> dict | None:
    """Fetch the single global_context row as a raw dict."""
    client = get_client()
    response = (
        client.table("global_context")
        .select("*")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_global_context() -> GlobalContext:
    """
    Read the current global context row and return it as a typed GlobalContext.

    Called by BaseAgent.load_global_context() at the start of every agent run.
    Raises RuntimeError if the table has not been seeded yet.
    """
    row = _get_raw_row()
    if row is None:
        raise RuntimeError(
            "Global context is empty. Run scripts/seed_global_context.py first."
        )
    # Strip DB-only fields (id, updated_at) before constructing the model
    row.pop("id", None)
    row.pop("updated_at", None)
    return GlobalContext(**row)


def update_global_context(field: str, value: Any, agent_name: str) -> GlobalContext:
    """
    Controlled write to a single field in the global context.

    Args:
        field:      Field path to update. Either a top-level column name
                    (e.g. "competitive_landscape") or a nested path
                    (e.g. "business_state.runway_months").
        value:      New value to set.
        agent_name: The agent requesting the write (used for permission check).

    Returns:
        Updated GlobalContext object.

    Raises:
        PermissionError:  Agent does not have write access to this field.
        RuntimeError:     Global context has not been seeded.
    """
    _check_permission(field, agent_name)

    client = get_client()
    raw = _get_raw_row()
    if raw is None:
        raise RuntimeError("Global context not seeded.")

    row_id = raw["id"]
    parts = field.split(".", 1)
    top_field = parts[0]

    if len(parts) == 1:
        # Top-level column update (e.g. "competitive_landscape")
        payload = {
            top_field: value,
            "version": raw["version"] + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        # Nested sub-field update (e.g. "business_state.runway_months")
        sub_field = parts[1]
        current_top: dict = raw.get(top_field) or {}
        current_top[sub_field] = value
        payload = {
            top_field: current_top,
            "version": raw["version"] + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    response = (
        client.table("global_context")
        .update(payload)
        .eq("id", row_id)
        .execute()
    )
    updated = response.data[0]
    updated.pop("id", None)
    updated.pop("updated_at", None)
    return GlobalContext(**updated)


# ── Chat context extraction ───────────────────────────────────────────────────

# Inject this snippet into every agent chat system prompt.
CONTEXT_EXTRACTION_PROMPT = """
CONTEXT MEMORY:
If the user tells you anything about their company — name, product, what it does, tech stack,
team size, business phase, target customers, or any other facts about the business —
extract those facts and emit a context block BEFORE your reply in this exact format:

<update_context>
{"company_profile": {"name": "...", "product_name": "...", "product_description": "...", "key_features": [...], "tech_stack": [...]}}
</update_context>

Rules:
- Only include fields the user actually mentioned. Omit everything else.
- If nothing context-worthy was said, omit the block entirely.
- The block must be valid JSON. Do not include any explanation inside it.
- Keep your natural reply separate — write it after the block.
"""


def extract_and_save_context(raw_reply: str, agent_name: str) -> str:
    """
    Parse any <update_context> blocks from a chat reply, merge the extracted
    fields into global_context, and return the reply with the block stripped.

    Args:
        raw_reply:  Full LLM response text (may contain <update_context> blocks)
        agent_name: Name of the calling agent (e.g. "pm", "finance")

    Returns:
        Cleaned reply string with the context block removed.
    """
    import re
    import json
    import logging
    logger = logging.getLogger(__name__)

    pattern = re.compile(r"<update_context>\s*([\s\S]*?)\s*</update_context>")

    def _apply_match(match: re.Match) -> str:
        try:
            data: dict = json.loads(match.group(1).strip())
        except Exception:
            logger.warning("extract_and_save_context: failed to parse JSON block")
            return ""

        raw = _get_raw_row()
        if raw is None:
            return ""

        client = get_client()

        # company_profile: merge into existing object
        if "company_profile" in data:
            new_fields: dict = data["company_profile"]
            existing: dict = raw.get("company_profile") or {}
            # Only overwrite non-empty incoming values
            merged = {**existing, **{k: v for k, v in new_fields.items() if v not in (None, "", [])}}
            try:
                client.table("global_context").update({
                    "company_profile": merged,
                    "version": raw["version"] + 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", raw["id"]).execute()
                logger.info("extract_and_save_context: updated company_profile via %s chat", agent_name)
            except Exception:
                logger.exception("extract_and_save_context: failed to save company_profile")

        return ""

    clean = pattern.sub(_apply_match, raw_reply).strip()
    return clean


def append_recent_event(event_summary: dict[str, Any]) -> None:
    """
    Append an event summary to the rolling recent_events list.
    Automatically trims the list to RECENT_EVENTS_CAP (50) entries (oldest removed).

    Called automatically by BaseAgent.emit_event() — agent builders don't call this directly.

    event_summary should include at minimum: event_type, summary, source_agent, timestamp.
    """
    client = get_client()
    raw = _get_raw_row()
    if raw is None:
        return

    recent: list = raw.get("recent_events") or []
    recent.append(event_summary)

    # Keep only the most recent N events
    if len(recent) > RECENT_EVENTS_CAP:
        recent = recent[-RECENT_EVENTS_CAP:]

    client.table("global_context").update({
        "recent_events": recent,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", raw["id"]).execute()
