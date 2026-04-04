"""
schemas/approvals.py — Pydantic models for Approval Queue.
"""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class Approval(BaseModel):
    """Full approval row as stored in and returned from the DB."""
    id: Optional[str] = None
    agent: str
    action_type: str
    content: dict[str, Any]
    status: str = "pending"             # pending | approved | rejected
    user_edits: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Request body for POST /api/approvals/{id}/respond."""
    status: str                         # "approved" or "rejected"
    edits: Optional[dict[str, Any]] = None  # user modifications to the content
