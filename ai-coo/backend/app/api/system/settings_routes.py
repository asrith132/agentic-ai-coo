"""
api/system/settings_routes.py — User settings (phone number, preferences).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.supabase_client import get_client

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class PhoneRequest(BaseModel):
    phone: str  # E.164 format e.g. +12125551234


class TelegramRequest(BaseModel):
    chat_id: str


def _get(key: str) -> str | None:
    r = get_client().table("user_settings").select("value").eq("key", key).maybe_single().execute()
    return r.data["value"] if r.data else None


def _set(key: str, value: str) -> None:
    get_client().table("user_settings").upsert({"key": key, "value": value}).execute()


@router.get("", summary="Get all user settings")
def get_settings():
    rows = get_client().table("user_settings").select("key,value").execute()
    return {r["key"]: r["value"] for r in (rows.data or [])}


@router.post("/phone", summary="Save user phone number for SMS alerts")
def save_phone(body: PhoneRequest):
    phone = body.phone.strip()
    if not phone.startswith("+"):
        raise HTTPException(status_code=400, detail="Phone must be in E.164 format, e.g. +12125551234")
    _set("phone", phone)
    return {"status": "saved", "phone": phone}


@router.delete("/phone", summary="Remove phone number")
def delete_phone():
    get_client().table("user_settings").delete().eq("key", "phone").execute()
    return {"status": "removed"}


@router.post("/telegram", summary="Save Telegram chat ID for push alerts")
def save_telegram(body: TelegramRequest):
    chat_id = body.chat_id.strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")
    _set("telegram_chat_id", chat_id)
    return {"status": "saved", "chat_id": chat_id}


@router.delete("/telegram", summary="Remove Telegram chat ID")
def delete_telegram():
    get_client().table("user_settings").delete().eq("key", "telegram_chat_id").execute()
    return {"status": "removed"}
