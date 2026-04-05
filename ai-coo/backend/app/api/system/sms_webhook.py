"""
api/system/sms_webhook.py — Twilio inbound SMS webhook.

User replies to an approval SMS with "{code} yes" or "{code} no".
This endpoint finds the matching approval and responds to it.

Configure in Twilio Console:
  Phone Numbers → Manage → Active numbers → your number
  Messaging → "A message comes in" → Webhook → POST
  URL: https://<your-ngrok>.ngrok-free.app/api/sms/webhook
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Form, Response
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sms", tags=["SMS"])


def _twiml(message: str) -> Response:
    """Return a minimal TwiML response so Twilio knows the webhook succeeded."""
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{message}</Message></Response>'
    return Response(content=xml, media_type="text/xml")


@router.post("/webhook", summary="Twilio inbound SMS webhook")
async def sms_webhook(Body: str = Form(""), From: str = Form("")):
    """
    Receive an inbound SMS from Twilio.
    Expected format: "<4-digit-code> yes|no"
    e.g. "1234 yes" or "5678 no"
    """
    text = Body.strip().lower()
    logger.info("Inbound SMS from %s: %r", From, text)

    # Parse "CODE yes/no"
    match = re.match(r"(\d{4})\s+(yes|no|approve|reject|y|n)", text)
    if not match:
        return _twiml("Format not recognised. Reply '<code> yes' or '<code> no', e.g. '1234 yes'.")

    code   = match.group(1)
    answer = match.group(2)
    status = "approved" if answer in ("yes", "approve", "y") else "rejected"

    # Look up approval_id from the stored code
    try:
        from app.db.supabase_client import get_client
        r = get_client().table("user_settings").select("value").eq("key", f"sms:{code}").maybe_single().execute()
        if not r.data:
            return _twiml(f"Code {code} not found or already used.")

        approval_id = r.data["value"]

        # Respond to the approval
        from app.core.approvals import respond_to_approval, get_approval
        existing = get_approval(approval_id)
        if not existing:
            return _twiml(f"Approval {code} not found.")
        if existing.status != "pending":
            return _twiml(f"Approval #{code} already {existing.status}.")

        respond_to_approval(approval_id=approval_id, status=status)

        # Clean up the code so it can't be reused
        get_client().table("user_settings").delete().eq("key", f"sms:{code}").execute()

        # If approved, trigger the agent callback in background
        if status == "approved":
            try:
                from app.schemas.triggers import AgentTrigger, TriggerType
                from app.agents.registry import get_agent
                final_content = {**(existing.content or {})}
                trigger = AgentTrigger(
                    type=TriggerType.USER_REQUEST,
                    user_input=f"execute_approved:{existing.action_type}",
                    parameters={
                        "approval_id": approval_id,
                        "action_type": existing.action_type,
                        "content": final_content,
                    },
                )
                import threading
                agent = get_agent(existing.agent)
                threading.Thread(target=agent.run, args=(trigger,), daemon=True).start()
            except Exception as exc:
                logger.error("SMS webhook: agent callback failed: %s", exc)

        emoji = "✅" if status == "approved" else "❌"
        c = existing.content or {}
        title = c.get("title") or c.get("subject") or existing.action_type.replace("_", " ").title()
        return _twiml(f"{emoji} {status.capitalize()}: {title[:80]}")

    except Exception as exc:
        logger.exception("SMS webhook error: %s", exc)
        return _twiml("Something went wrong. Please open the app to respond.")
