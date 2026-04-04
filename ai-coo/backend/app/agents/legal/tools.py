"""
agents/legal/tools.py — Legal agent helper functions.

Pure utility layer: no agent state, no LLM calls (those live in agent.py).
The agent imports these to keep its execute() method readable.

Functions:
  resolve_due_date()         — parse LLM deadline rules → actual date
  days_until()               — signed day delta (negative = overdue)
  urgency_from_days()        — bucket days into priority string
  build_checklist_prompt()   — construct the LLM prompt for checklist generation
  parse_checklist_json()     — safely extract JSON array from LLM response
  build_document_prompt()    — construct the LLM prompt for document drafting
  document_type_for_item()   — infer legal_documents.document_type from item name
  get_existing_documents()   — query legal_documents for a given type
  get_pending_checklist_items() — query items due within N days or overdue
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta
from typing import Any, Optional

# ── Date utilities ────────────────────────────────────────────────────────────

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _add_months(d: date, months: int) -> date:
    """Add calendar months to a date without dateutil dependency."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def resolve_due_date(rule: str, today: Optional[date] = None) -> Optional[date]:
    """
    Parse a plain-English deadline rule string into an actual date.

    Handles the most common patterns returned by the checklist LLM:
      "within 30 days"                → today + 30 days
      "within 3 months"               → today + 3 months
      "within 90 days of incorporation" → today + 90 days
      "annually by March 1"           → next March 1 (or this year if not yet passed)
      "by April 15"                   → next April 15
      "within 1 year"                 → today + 12 months
      "quarterly"                     → next quarter-end date

    Returns None for rules that cannot be parsed (item has no fixed deadline).
    """
    if today is None:
        today = date.today()

    rule_lower = rule.lower().strip()

    # "within N days [of ...]"
    m = re.search(r'within\s+(\d+)\s+days?', rule_lower)
    if m:
        return today + timedelta(days=int(m.group(1)))

    # "within N months [of ...]"
    m = re.search(r'within\s+(\d+)\s+months?', rule_lower)
    if m:
        return _add_months(today, int(m.group(1)))

    # "within N weeks"
    m = re.search(r'within\s+(\d+)\s+weeks?', rule_lower)
    if m:
        return today + timedelta(weeks=int(m.group(1)))

    # "within N year(s)" / "within 1 year"
    m = re.search(r'within\s+(\d+)\s+years?', rule_lower)
    if m:
        return _add_months(today, int(m.group(1)) * 12)

    # "annually by <month> <day>" or "by <month> <day>"
    m = re.search(r'by\s+([a-z]+)\s+(\d+)', rule_lower)
    if m:
        month_str, day_str = m.group(1), int(m.group(2))
        month = _MONTH_NAMES.get(month_str)
        if month:
            candidate = date(today.year, month, min(day_str, calendar.monthrange(today.year, month)[1]))
            if candidate < today:
                candidate = date(today.year + 1, month, min(day_str, calendar.monthrange(today.year + 1, month)[1]))
            return candidate

    # "quarterly" → next quarter-end
    if "quarterly" in rule_lower:
        quarter_ends = [date(today.year, 3, 31), date(today.year, 6, 30),
                        date(today.year, 9, 30), date(today.year, 12, 31)]
        for qe in quarter_ends:
            if qe >= today:
                return qe
        return date(today.year + 1, 3, 31)

    # "immediately" / "asap" / "upon incorporation" / "upon formation"
    if any(kw in rule_lower for kw in ("immediately", "asap", "upon", "at formation", "at founding")):
        return today

    return None


def days_until(due_date: date) -> int:
    """
    Signed day count to `due_date` from today.
    Negative means the deadline has already passed (overdue).
    """
    return (due_date - date.today()).days


def urgency_from_days(days: int) -> str:
    """
    Map remaining days to a priority string used in event payloads.

      overdue (days < 0)  → "urgent"
      0–7 days            → "high"
      8–14 days           → "medium"
      15+ days            → "low"
    """
    if days < 0:
        return "urgent"
    if days <= 7:
        return "high"
    if days <= 14:
        return "medium"
    return "low"


# ── LLM prompt builders ───────────────────────────────────────────────────────

def build_checklist_prompt(
    entity_type: str,
    jurisdiction: str,
    stage: str,
    product_type: str,
) -> str:
    """
    Build the system + user prompt for checklist generation.
    Returns the user message string (the system prompt is set in agent.py).
    """
    return f"""Generate a compliance checklist for this startup:

Entity type:  {entity_type}
Jurisdiction: {jurisdiction}
Stage:        {stage}
Product type: {product_type}

For each item provide:
- item: short name (max 60 chars)
- description: 1–2 plain-English sentences explaining what it is and why it matters
- category: one of [incorporation, tax, compliance, ip, contracts, employment, privacy]
- priority: one of [low, medium, high, urgent]
- deadline_rule: plain-English rule e.g. "within 30 days of incorporation", \
"annually by March 1", "within 90 days of formation", "quarterly"
- typically_overdue: true if companies at the "{stage}" stage commonly have this outstanding

Return ONLY a JSON array of 12–18 items, ordered by priority (urgent first).
No markdown, no explanation, just the raw JSON array.

Example item shape:
{{"item": "File Certificate of Incorporation", "description": "...", \
"category": "incorporation", "priority": "urgent", \
"deadline_rule": "within 30 days", "typically_overdue": false}}"""


def build_document_prompt(
    document_type: str,
    company_name: str,
    product_name: str,
    product_description: str,
    jurisdiction: str,
    stage: str,
    product_type: str,
    extra_context: str = "",
) -> str:
    """Build the user message for document drafting."""
    type_label = document_type.replace("_", " ").title()
    context_block = f"\nAdditional context: {extra_context}" if extra_context else ""

    return f"""Draft a {type_label} for the following company.

Company name:    {company_name}
Product:         {product_name} — {product_description}
Jurisdiction:    {jurisdiction}
Stage:           {stage}
Product type:    {product_type}{context_block}

Requirements:
- This should be a functional first draft, not a template with [PLACEHOLDER] blanks.
- Use the company's actual name and product details throughout.
- Keep it professional but readable by a non-lawyer.
- Include all standard clauses expected in a {type_label} for a \
{stage} {product_type} company operating under {jurisdiction} law.
- Start directly with the document title. Do not include meta-commentary.

Draft the complete {type_label} now:"""


# ── JSON parsing ──────────────────────────────────────────────────────────────

def parse_checklist_json(llm_response: str) -> list[dict[str, Any]]:
    """
    Safely extract a JSON array from the LLM's checklist response.

    Handles cases where the model wraps output in ```json ... ``` fences
    or adds a brief preamble before the array.

    Raises ValueError if no valid JSON array is found.
    """
    text = llm_response.strip()

    # Strip ```json ... ``` fences
    fenced = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Find the first '[' and last ']'
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not parse JSON array from LLM response. "
        f"First 300 chars: {llm_response[:300]}"
    )


# ── Document type inference ───────────────────────────────────────────────────

_ITEM_TO_DOC_TYPE: list[tuple[list[str], str]] = [
    (["privacy policy", "privacy notice", "gdpr"],              "privacy_policy"),
    (["terms of service", "terms of use", "tos"],               "tos"),
    (["contractor", "consulting agreement", "service agreement"], "contractor_agreement"),
    (["nda", "non-disclosure", "confidentiality agreement"],    "nda"),
    (["employee agreement", "employment contract", "offer letter"], "employee_agreement"),
    (["ip assignment", "intellectual property", "work for hire"], "ip_assignment"),
    (["certificate of incorporation", "articles", "formation"], "incorporation"),
]


def document_type_for_item(item_name: str) -> str:
    """
    Infer a legal_documents.document_type value from a checklist item name.
    Falls back to "other" if no match is found.
    """
    lower = item_name.lower()
    for keywords, doc_type in _ITEM_TO_DOC_TYPE:
        if any(kw in lower for kw in keywords):
            return doc_type
    return "other"


# ── Database helpers ──────────────────────────────────────────────────────────

def get_existing_documents(document_type: str) -> list[dict[str, Any]]:
    """
    Query legal_documents for any existing documents of the given type.
    Returns rows as dicts. Empty list if none found.
    """
    from app.db.supabase_client import get_client
    client = get_client()
    response = (
        client.table("legal_documents")
        .select("id, title, status, created_at")
        .eq("document_type", document_type)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def get_pending_checklist_items(days_window: int = 14) -> list[dict[str, Any]]:
    """
    Return checklist items that are:
      - Not done AND
      - due_date has passed (overdue) OR due_date is within `days_window` days

    Used by the daily deadline_check scheduled task.
    """
    from app.db.supabase_client import get_client
    from datetime import date

    client = get_client()
    cutoff = (date.today() + timedelta(days=days_window)).isoformat()

    response = (
        client.table("legal_checklist")
        .select("*")
        .neq("status", "done")
        .not_.is_("due_date", "null")
        .lte("due_date", cutoff)
        .order("due_date", desc=False)
        .execute()
    )
    return response.data or []
