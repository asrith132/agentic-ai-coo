"""
schemas/approvals.py — Pydantic models for Approval Queue.
"""

from __future__ import annotations
from typing import Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class Approval(BaseModel):
    """Full approval row as returned from the database."""
    id: UUID
    agent: str
    action_type: str
    content: dict[str, Any]
    status: str = "pending"       # pending | approved | rejected
    user_edits: dict[str, Any] | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ApprovalResponse(BaseModel):
    """Request body for POST /api/approvals/{id}/respond."""
    decision: str                 # "approved" or "rejected"
    user_edits: dict[str, Any] | None = None
