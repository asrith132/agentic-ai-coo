"""
api/system/telegram_webhook.py — Telegram bot webhook.

User replies to an approval notification with "{code} yes" or "{code} no".
This endpoint finds the matching approval and processes it.

The webhook is auto-registered with Telegram on startup using public_url from settings.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["Telegram"])


@router.post("/webhook", summary="Telegram bot webhook", include_in_schema=False)
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    message = update.get("message") or update.get("edited_message")
    if not message:
        return JSONResponse({"ok": True})

    text = (message.get("text") or "").strip().lower()
    logger.info("Telegram message: %r", text)

    match = re.match(r"(\d{4})\s+(yes|no|approve|reject|y|n)", text)
    if not match:
        return JSONResponse({"ok": True})

    code   = match.group(1)
    answer = match.group(2)
    status = "approved" if answer in ("yes", "approve", "y") else "rejected"

    try:
        from app.db.supabase_client import get_client
        r = get_client().table("user_settings").select("value").eq("key", f"telegram_code:{code}").maybe_single().execute()
        if not r.data:
            _reply(message, f"Code {code} not found or already used.")
            return JSONResponse({"ok": True})

        approval_id = r.data["value"]

        from app.core.approvals import respond_to_approval, get_approval
        existing = get_approval(approval_id)
        if not existing:
            _reply(message, f"Approval #{code} not found.")
            return JSONResponse({"ok": True})
        if existing.status != "pending":
            _reply(message, f"Approval #{code} already {existing.status}.")
            return JSONResponse({"ok": True})

        respond_to_approval(approval_id=approval_id, status=status)
        get_client().table("user_settings").delete().eq("key", f"telegram_code:{code}").execute()

        if status == "approved":
            try:
                from app.schemas.triggers import AgentTrigger, TriggerType
                from app.agents.registry import get_agent
                import threading
                trigger = AgentTrigger(
                    type=TriggerType.USER_REQUEST,
                    user_input=f"execute_approved:{existing.action_type}",
                    parameters={
                        "approval_id": approval_id,
                        "action_type": existing.action_type,
                        "content": {**(existing.content or {})},
                    },
                )
                agent = get_agent(existing.agent)
                threading.Thread(target=agent.run, args=(trigger,), daemon=True).start()
            except Exception as exc:
                logger.error("Telegram webhook: agent callback failed: %s", exc)

        emoji = "✅" if status == "approved" else "❌"
        c = existing.content or {}
        title = c.get("title") or c.get("subject") or existing.action_type.replace("_", " ").title()
        _reply(message, f"{emoji} {status.capitalize()}: {title[:80]}")

    except Exception as exc:
        logger.exception("Telegram webhook error: %s", exc)

    return JSONResponse({"ok": True})


def _reply(message: dict, text: str) -> None:
    """Send a reply back to the same Telegram chat."""
    try:
        import urllib.request, json
        from app.config import settings

        if not settings.telegram_bot_token:
            return

        chat_id = message.get("chat", {}).get("id")
        if not chat_id:
            return

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:
        logger.warning("Telegram reply failed: %s", exc)


def register_webhook() -> None:
    """Register this server's webhook URL with Telegram. Called on startup."""
    try:
        import urllib.request, json
        from app.config import settings

        if not settings.telegram_bot_token:
            return

        webhook_url = f"{settings.public_url.rstrip('/')}/api/telegram/webhook"
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
        payload = json.dumps({"url": webhook_url}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        if result.get("ok"):
            logger.info("Telegram webhook registered: %s", webhook_url)
            print(f"✓ Telegram webhook registered: {webhook_url}")
        else:
            logger.warning("Telegram webhook registration failed: %s", result)
    except Exception as exc:
        logger.warning("Telegram webhook registration error: %s", exc)
