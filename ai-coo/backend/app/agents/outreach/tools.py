"""
agents/outreach/tools.py — Outreach helpers for research, Gmail, and DB access.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Iterable
import base64
import json
import logging
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.core.approvals import get_approval
from app.db.supabase_client import get_client

logger = logging.getLogger(__name__)


def _extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def _company_domain(company: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", company.lower())
    return f"{normalized}.com" if normalized else ""


def _fetch_url(url: str, timeout: float = 6.0) -> str | None:
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "AI-COO-OutreachAgent/1.0"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as exc:
        logger.info("Outreach fetch failed for %s: %s", url, exc)
        return None


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """
    Lightweight HTML search against DuckDuckGo's static endpoint.
    Returns title/url/snippet triples for prompting and follow-on research.
    """
    encoded = urllib.parse.quote_plus(query)
    html = _fetch_url(f"https://html.duckduckgo.com/html/?q={encoded}", timeout=8.0)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    for result in soup.select(".result"):
        title_node = result.select_one(".result__title")
        link_node = result.select_one(".result__url")
        snippet_node = result.select_one(".result__snippet")
        title = " ".join(title_node.stripped_strings) if title_node else ""
        url = " ".join(link_node.stripped_strings) if link_node else ""
        snippet = " ".join(snippet_node.stripped_strings) if snippet_node else ""
        if title or snippet:
            results.append({"title": title, "url": url, "snippet": snippet, "query": query})
        if len(results) >= max_results:
            break
    return results


def _strip_html(html: str, max_chars: int = 2500) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    return text[:max_chars]


def _research_urls(name: str, company: str) -> list[dict[str, str]]:
    q_name = urllib.parse.quote_plus(name)
    q_company = urllib.parse.quote_plus(company)
    domain = _company_domain(company)
    urls = [
        {
            "kind": "linkedin_search",
            "url": f"https://www.google.com/search?q={q_name}+{q_company}+LinkedIn",
        },
        {
            "kind": "company_news_search",
            "url": f"https://www.google.com/search?q={q_company}+latest+news",
        },
    ]
    if domain:
        urls.append({"kind": "company_homepage", "url": f"https://{domain}"})
        urls.append({"kind": "company_about", "url": f"https://{domain}/about"})
        urls.append({"kind": "company_blog", "url": f"https://{domain}/blog"})
    return urls


def build_research_cache(name: str, company: str, context: str | None = None) -> dict[str, Any]:
    """Collect lightweight public-web signals with graceful fallback."""
    pages: list[dict[str, str]] = []
    for item in _research_urls(name, company):
        html = _fetch_url(item["url"])
        if not html:
            continue
        pages.append(
            {
                "kind": item["kind"],
                "url": item["url"],
                "excerpt": _strip_html(html),
            }
        )

    domain = _company_domain(company)
    email = f"{name.split()[0].lower()}@{domain}" if name.strip() and domain else None
    role = "Unknown"
    inferred_tenure = "Unknown"
    if context:
        lower_context = context.lower()
        if "investor" in lower_context:
            role = "Investor or operator"
        elif "partner" in lower_context:
            role = "Partnership lead or operator"
        elif "press" in lower_context:
            role = "Press or communications contact"
        elif "customer" in lower_context:
            role = "Potential customer"

    summary_parts = [p["excerpt"] for p in pages[:3] if p.get("excerpt")]
    snippets = "\n\n".join(summary_parts)

    return {
        "name": name,
        "company": company,
        "email": email,
        "role": role,
        "tenure": inferred_tenure,
        "linkedin_summary": summary_parts[0] if summary_parts else "",
        "recent_posts": [p["excerpt"] for p in pages if "blog" in p["kind"]][:2],
        "company_news": [p["excerpt"] for p in pages if "news" in p["kind"]][:2],
        "sources": pages,
        "context": context or "",
        "raw_summary": snippets,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def build_prospect_search_queries(
    *,
    company_name: str,
    product_name: str,
    product_description: str,
    persona: str,
    pain_points: list[str],
    focus: str | None = None,
) -> list[str]:
    product_anchor = product_name or company_name or "startup software"
    product_desc = product_description or "operations automation software"
    persona_anchor = persona or "startup operator"
    pain_anchor = pain_points[0] if pain_points else "manual operational work"
    focus_anchor = focus or "companies likely to benefit soon"

    queries = [
        f'"{product_anchor}" alternatives buyers {persona_anchor}',
        f'{pain_anchor} head of operations startup {focus_anchor}',
        f'{pain_anchor} founder growth lead SaaS',
        f'{product_desc} companies hiring operations',
        f'{product_desc} founder interview productivity workflow',
        f'{persona_anchor} teams complaining about {pain_anchor}',
        f'{focus_anchor} startup operations leader developer productivity',
    ]
    return queries[:6]


def get_contact(contact_id: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("outreach_contacts")
        .select("*")
        .eq("id", contact_id)
        .maybe_single()
        .execute()
    )
    return response.data if response.data else None


def upsert_contact(
    *,
    name: str,
    company: str,
    role: str | None = None,
    email: str | None = None,
    contact_type: str = "customer",
    status: str = "cold",
    source: str = "manual",
    research_cache: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    client = get_client()
    existing = (
        client.table("outreach_contacts")
        .select("*")
        .eq("name", name)
        .eq("company", company)
        .limit(1)
        .execute()
    )
    if existing.data:
        current = existing.data[0]
        payload = {
            "role": role or current.get("role"),
            "email": email or current.get("email"),
            "contact_type": contact_type or current.get("contact_type"),
            "status": status or current.get("status"),
            "source": source or current.get("source"),
            "notes": notes or current.get("notes"),
            "research_cache": {
                **(current.get("research_cache") or {}),
                **(research_cache or {}),
            },
        }
        response = (
            client.table("outreach_contacts")
            .update(payload)
            .eq("id", current["id"])
            .execute()
        )
        return response.data[0]

    payload = {
        "name": name,
        "company": company,
        "role": role,
        "email": email,
        "contact_type": contact_type,
        "status": status,
        "source": source,
        "research_cache": research_cache or {},
        "notes": notes,
    }
    response = client.table("outreach_contacts").insert(payload).execute()
    return response.data[0]


def update_contact(contact_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    response = (
        get_client()
        .table("outreach_contacts")
        .update(updates)
        .eq("id", contact_id)
        .execute()
    )
    return response.data[0]


def list_contacts(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = (
        get_client()
        .table("outreach_contacts")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    return query.execute().data


def create_message(
    *,
    contact_id: str,
    subject: str,
    body: str,
    direction: str = "sent",
    channel: str = "email",
    status: str = "draft",
    template_used: str | None = None,
    approval_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "contact_id": contact_id,
        "direction": direction,
        "subject": subject,
        "body": body,
        "channel": channel,
        "status": status,
        "template_used": template_used,
        "approval_id": approval_id,
    }
    response = get_client().table("outreach_messages").insert(payload).execute()
    return response.data[0]


def update_message(message_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    response = (
        get_client()
        .table("outreach_messages")
        .update(updates)
        .eq("id", message_id)
        .execute()
    )
    return response.data[0]


def get_message(message_id: str) -> dict[str, Any] | None:
    response = (
        get_client()
        .table("outreach_messages")
        .select("*")
        .eq("id", message_id)
        .maybe_single()
        .execute()
    )
    return response.data if response.data else None


def list_messages(contact_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = (
        get_client()
        .table("outreach_messages")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if contact_id:
        query = query.eq("contact_id", contact_id)
    return query.execute().data


def get_template(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    response = (
        get_client()
        .table("outreach_templates")
        .select("*")
        .eq("name", name)
        .maybe_single()
        .execute()
    )
    return response.data if response.data else None


def list_followup_candidates() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    response = (
        get_client()
        .table("outreach_contacts")
        .select("*")
        .lte("next_followup_at", now)
        .not_.in_("status", ["responded", "converted"])
        .execute()
    )
    return response.data


def ensure_approval_is_approved(approval_id: str | None) -> dict[str, Any]:
    if not approval_id:
        raise ValueError("Message has no approval_id")
    approval = get_approval(approval_id)
    if approval is None:
        raise ValueError(f"Approval '{approval_id}' not found")
    if approval.status != "approved":
        raise ValueError(f"Approval '{approval_id}' is {approval.status}, not approved")
    data = approval.model_dump()
    data["final_content"] = {
        **(approval.content or {}),
        **(approval.user_edits or {}),
    }
    return data


def send_via_gmail(*, to_email: str | None, subject: str, body: str) -> dict[str, Any]:
    """
    Best-effort Gmail send. Falls back to demo mode if Gmail credentials or APIs are unavailable.
    """
    if not to_email:
        return {
            "mode": "demo",
            "status": "sent",
            "provider_message_id": None,
            "detail": "No contact email available. Simulated send for demo mode.",
        }

    if not all([settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_refresh_token]):
        return {
            "mode": "demo",
            "status": "sent",
            "provider_message_id": None,
            "detail": "Gmail not configured. Simulated send for demo mode.",
        }

    try:
        import google.auth.transport.requests
        import google.oauth2.credentials
        from googleapiclient.discovery import build

        creds = google.oauth2.credentials.Credentials(
            None,
            refresh_token=settings.gmail_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
        )
        creds.refresh(google.auth.transport.requests.Request())

        msg = EmailMessage()
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        service = build("gmail", "v1", credentials=creds)
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {
            "mode": "gmail",
            "status": "sent",
            "provider_message_id": result.get("id"),
            "detail": "Sent via Gmail API.",
        }
    except Exception as exc:
        logger.warning("Gmail send failed, falling back to demo mode: %s", exc)
        return {
            "mode": "demo",
            "status": "sent",
            "provider_message_id": None,
            "detail": f"Gmail unavailable; simulated send. Root cause: {exc}",
        }


def fetch_recent_replies(max_results: int = 10) -> list[dict[str, Any]]:
    """
    Demo-safe reply polling.
    If Gmail is not configured, returns an empty list.
    """
    if not all([settings.gmail_client_id, settings.gmail_client_secret, settings.gmail_refresh_token]):
        return []

    try:
        import google.auth.transport.requests
        import google.oauth2.credentials
        from googleapiclient.discovery import build

        creds = google.oauth2.credentials.Credentials(
            None,
            refresh_token=settings.gmail_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
        )
        creds.refresh(google.auth.transport.requests.Request())
        service = build("gmail", "v1", credentials=creds)
        result = (
            service.users()
            .messages()
            .list(userId="me", q="is:inbox newer_than:7d", maxResults=max_results)
            .execute()
        )

        replies: list[dict[str, Any]] = []
        for msg_ref in result.get("messages", []):
            full = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
            headers = {
                h["name"].lower(): h["value"]
                for h in full.get("payload", {}).get("headers", [])
            }
            body_text = json.dumps(full)[:4000]
            replies.append(
                {
                    "provider_id": full.get("id"),
                    "from": headers.get("from", ""),
                    "subject": headers.get("subject", ""),
                    "body": body_text,
                    "received_at": headers.get("date"),
                    "contact_email": _extract_email(headers.get("from", "")),
                }
            )
        return replies
    except Exception as exc:
        logger.warning("Gmail reply polling failed: %s", exc)
        return []


def schedule_next_followup(contact_id: str, follow_up_sequence: Iterable[dict[str, Any]] | None) -> None:
    steps = list(follow_up_sequence or [])
    if not steps:
        return
    delay_days = int(steps[0].get("delay_days", 3))
    update_contact(
        contact_id,
        {"next_followup_at": (datetime.now(timezone.utc) + timedelta(days=delay_days)).isoformat()},
    )
