"""
agents/dev_activity/tools.py — Dev Activity agent helper functions.

Pure utility layer: no agent state, no LLM calls (those live in agent.py).

Functions:
  verify_github_signature()      — HMAC-SHA256 webhook request verification
  parse_push_event()             — extract commit data from GitHub push payload
  build_commit_analysis_prompt() — LLM prompt for commit interpretation
  parse_commit_analysis()        — safely extract JSON from LLM response
  extract_version()              — detect version strings in commit messages
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Optional


# ── Webhook verification ──────────────────────────────────────────────────────

def verify_github_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify the HMAC-SHA256 signature GitHub sends with every webhook delivery.

    Args:
        body:             Raw request body bytes.
        signature_header: Value of the X-Hub-Signature-256 header (e.g. "sha256=abc123").
        secret:           The webhook secret configured in GitHub settings.

    Returns:
        True if the signature matches; False otherwise.
    """
    if not secret:
        # No secret configured — skip verification (dev/test mode)
        return True
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Payload parsing ───────────────────────────────────────────────────────────

def parse_push_event(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Extract the head commit data from a GitHub push event payload.

    We process only the head_commit per push (most recent) to avoid making
    one LLM call per commit when someone pushes a batch of commits at once.

    Returns None if the payload has no commits (e.g. tag push with no commits).
    """
    head = payload.get("head_commit")
    if not head:
        return None

    ref = payload.get("ref", "")
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref

    # Diff stats — GitHub push payload doesn't include line counts,
    # but does include file path lists
    added    = head.get("added",    [])
    removed  = head.get("removed",  [])
    modified = head.get("modified", [])

    author_info = head.get("author") or {}

    return {
        "sha":           head.get("id", "")[:40],
        "message":       head.get("message", "").strip(),
        "author":        author_info.get("name", "") or author_info.get("username", ""),
        "timestamp":     head.get("timestamp"),      # ISO 8601 string
        "branch":        branch,
        "files_added":   added,
        "files_removed": removed,
        "files_modified": modified,
        "files_changed": len(added) + len(removed) + len(modified),
        "url":           head.get("url", ""),
        "repo_name":     (payload.get("repository") or {}).get("full_name", ""),
    }


def parse_pr_merged_event(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Extract commit-equivalent data from a GitHub pull_request (closed+merged) event.

    Returns None if the PR was closed but not merged.
    """
    pr = payload.get("pull_request", {})
    if not pr.get("merged"):
        return None

    return {
        "sha":           pr.get("merge_commit_sha", "")[:40],
        "message":       f"[PR #{pr.get('number')}] {pr.get('title', '')}",
        "author":        (pr.get("user") or {}).get("login", ""),
        "timestamp":     pr.get("merged_at"),
        "branch":        (pr.get("base") or {}).get("ref", "main"),
        "files_added":   [],
        "files_removed": [],
        "files_modified": [],
        "files_changed": pr.get("changed_files", 0),
        "url":           pr.get("html_url", ""),
        "repo_name":     (payload.get("repository") or {}).get("full_name", ""),
        "pr_body":       pr.get("body", "") or "",
    }


# ── LLM prompt builder ────────────────────────────────────────────────────────

def build_commit_analysis_prompt(
    commit_data: dict[str, Any],
    company_name: str,
    product_description: str,
    key_features: list[str],
) -> str:
    """
    Build the user message for commit analysis.

    The system prompt (set in agent.py) already carries company context.
    This user message provides the specific commit details to analyze.
    """
    features_str = ", ".join(key_features) if key_features else "(none documented yet)"

    files_sample = (
        commit_data.get("files_modified", []) +
        commit_data.get("files_added", [])
    )[:10]  # cap at 10 paths to avoid token bloat
    files_str = "\n".join(f"  {f}" for f in files_sample) if files_sample else "  (not available)"

    return f"""Analyze this code commit and return a JSON object.

COMMIT DETAILS:
  SHA:        {commit_data.get('sha', 'unknown')[:12]}
  Author:     {commit_data.get('author', 'unknown')}
  Branch:     {commit_data.get('branch', 'main')}
  Message:    {commit_data.get('message', '(no message)')}
  Files changed: {commit_data.get('files_changed', 0)}
  Files touched:
{files_str}

CURRENT PRODUCT FEATURES: {features_str}

Return ONLY a JSON object with these exact keys:

{{
  "commit_type": "feature" | "bug_fix" | "improvement" | "maintenance",
  "plain_english_summary": "<1-2 sentences explaining what changed and why it matters to the business — non-technical>",
  "feature_name": "<name of the feature this relates to, or null if not feature-related>",
  "is_new_feature": true | false,
  "notify_teams": true | false,
  "notify_reason": "<why other teams should know, or empty string>",
  "severity": "minor" | "major" | "critical" | null,
  "detected_version": "<version string if this is a release commit, e.g. '1.2.0', else null>"
}}

Rules:
- commit_type="feature" only if the commit adds genuinely new user-facing functionality
- commit_type="bug_fix" for fixes; set severity based on likely user impact
- commit_type="improvement" for refactors, performance, DX that users benefit from
- commit_type="maintenance" for tests, CI, docs, deps, build scripts
- is_new_feature=true only when commit_type="feature" AND it appears to be the first time this feature is introduced
- notify_teams=true when the change affects product behaviour, pricing, availability, or integrations
- detected_version: look for patterns like "v1.2.0", "release 2.0", "bump version to 3.1" in the message"""


# ── LLM response parsing ──────────────────────────────────────────────────────

def parse_commit_analysis(llm_response: str) -> dict[str, Any]:
    """
    Safely extract the JSON object from the LLM's commit analysis response.

    Handles markdown fences and preamble text.
    Raises ValueError if no valid JSON object is found.
    """
    text = llm_response.strip()

    # Strip ```json ... ``` fences
    fenced = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Find first { and last }
    start = text.find('{')
    end   = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not parse JSON object from LLM response. "
        f"First 300 chars: {llm_response[:300]}"
    )


# ── Version extraction ────────────────────────────────────────────────────────

# Patterns: "v1.2.3", "version 1.2", "release 2.0.0", "bump to 3.1"
_VERSION_RE = re.compile(
    r'\b(?:v(?:ersion\s*)?|release\s+|bump\s+(?:to\s+)?)?'
    r'(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?)\b',
    re.IGNORECASE,
)


def extract_version(commit_message: str) -> Optional[str]:
    """
    Extract a version string from a commit message.

    Returns the first match (e.g. "1.2.3"), or None if not found.
    """
    release_keywords = ("release", "version", "bump", "tag", " v", "\nv")
    msg_lower = commit_message.lower()
    if not any(kw in msg_lower for kw in release_keywords):
        return None
    m = _VERSION_RE.search(commit_message)
    return m.group(1) if m else None
