"""
agents/dev_activity/agent.py — DevActivityAgent

"Push Code, Everything Updates" — watches GitHub commits, interprets them in
business terms, updates the feature map, and broadcasts context events so every
other agent stays informed about what just shipped.

AUTONOMY RULES
  Process commits      → Autonomous (stores + emits, no approval)
  Update feature map   → Autonomous
  Emit events          → Autonomous

TRIGGER HANDLING
  USER_REQUEST
    user_input="process_commit"  → _process_commit(trigger.parameters["commit_data"])
    user_input="manual run"      → _run_status_check()

  (No EVENT triggers — this agent is a pure sensor; it emits only.)

EVENTS EMITTED
  feature_shipped     — new user-facing feature detected in commit
  bug_fixed           — bug fix detected
  release_created     — commit message indicates a versioned release
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.base_agent import BaseAgent
from app.db.supabase_client import get_client
from app.schemas.triggers import AgentTrigger, TriggerType

from app.agents.dev_activity.tools import (
    build_commit_analysis_prompt,
    extract_version,
    parse_commit_analysis,
)

logger = logging.getLogger(__name__)


class DevActivityAgent(BaseAgent):
    name = "dev_activity"
    description = (
        "Watches GitHub for code changes, interprets them in business terms, "
        "and broadcasts context updates"
    )
    subscribed_events = []          # Pure sensor — emits only, never consumes
    writable_global_fields = ["business_state.last_updated"]

    _SYSTEM_PROMPT = (
        "You are a technical analyst for a software startup. Your job is to read "
        "code commits and explain them clearly in plain business language — what "
        "changed, why it matters, and whether other teams need to know. "
        "Be precise and brief. Never use jargon without explanation."
    )

    # ── BaseAgent abstract methods ────────────────────────────────────────────

    def load_domain_context(self) -> dict[str, Any]:
        """Load recent commits and current feature map for situational awareness."""
        client = get_client()

        commits_resp = (
            client.table("dev_commits")
            .select("sha, message, author, timestamp, parsed_summary, features_referenced")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )

        features_resp = (
            client.table("dev_features")
            .select("feature_name, description, status, shipped_at")
            .eq("status", "shipped")
            .order("shipped_at", desc=True)
            .limit(20)
            .execute()
        )

        return {
            "recent_commits":   commits_resp.data or [],
            "shipped_features": features_resp.data or [],
        }

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        """
        Dispatch based on trigger type.

        USER_REQUEST "process_commit" is the primary path — called by the
        webhook handler for each incoming push/PR event.
        """
        if trigger.type != TriggerType.USER_REQUEST:
            return {"status": "skipped", "reason": "dev_activity only handles USER_REQUEST triggers"}

        user_input = (trigger.user_input or "").lower().strip()
        params     = trigger.parameters or {}

        if user_input == "process_commit":
            commit_data = params.get("commit_data")
            if not commit_data:
                return {"status": "error", "reason": "missing commit_data in parameters"}
            return self._process_commit(commit_data)

        if user_input in ("manual run", "status"):
            return self._run_status_check()

        self.logger.warning("DevActivityAgent: unrecognised user_input '%s'", trigger.user_input)
        return {"status": "skipped", "reason": f"unknown user_input: {trigger.user_input}"}

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        """Dev activity state lives entirely in dev_commits / dev_features — no single state row."""
        pass

    # ── Core processing ───────────────────────────────────────────────────────

    def _process_commit(self, commit_data: dict[str, Any]) -> dict[str, Any]:
        """
        Analyse one commit via LLM and store + broadcast the results.

        Steps:
          1. Call LLM to interpret the commit in business terms
          2. Upsert dev_commits row (idempotent on SHA)
          3. If new feature → upsert dev_features, emit feature_shipped
          4. If bug fix    → emit bug_fixed
          5. If release    → emit release_created
          6. Stamp business_state.last_updated
        """
        sha     = (commit_data.get("sha") or "")[:40]
        message = commit_data.get("message", "").strip()
        author  = commit_data.get("author", "unknown")
        branch  = commit_data.get("branch", "main")

        if not sha:
            raise ValueError("commit_data must include a non-empty 'sha' field")

        self.logger.info("DevActivityAgent: processing commit %s by %s", sha[:12], author)

        # ── LLM call ──────────────────────────────────────────────────────────
        ctx = self._global_context
        cp  = ctx.company_profile

        user_msg = build_commit_analysis_prompt(
            commit_data=commit_data,
            company_name=cp.name or "the Company",
            product_description=cp.product_description or "",
            key_features=cp.key_features or [],
        )

        raw_analysis = self.llm_chat(
            system_prompt=self._SYSTEM_PROMPT,
            user_message=user_msg,
            temperature=0.2,        # low temp — structured factual output
            inject_context=True,
        )

        try:
            analysis = parse_commit_analysis(raw_analysis)
        except ValueError as exc:
            self.logger.error("DevActivityAgent: commit analysis parse failed: %s", exc)
            # Store the commit with a fallback summary so we don't lose the record
            analysis = {
                "commit_type": "maintenance",
                "plain_english_summary": message[:200],
                "feature_name": None,
                "is_new_feature": False,
                "notify_teams": False,
                "notify_reason": "",
                "severity": None,
                "detected_version": extract_version(message),
            }

        commit_type      = analysis.get("commit_type", "maintenance")
        summary          = analysis.get("plain_english_summary", message[:200])
        feature_name     = analysis.get("feature_name") or None
        is_new_feature   = bool(analysis.get("is_new_feature"))
        notify_teams     = bool(analysis.get("notify_teams"))
        severity         = analysis.get("severity")
        detected_version = analysis.get("detected_version") or extract_version(message)

        # Normalise feature_name: treat "null", "none", "n/a" strings as None
        if feature_name and feature_name.lower() in ("null", "none", "n/a", ""):
            feature_name = None

        # ── Store commit ───────────────────────────────────────────────────────
        client = get_client()

        features_referenced = [feature_name] if feature_name else []

        commit_row = {
            "sha":                sha,
            "message":            message[:2000],
            "author":             author,
            "timestamp":          commit_data.get("timestamp"),
            "branch":             branch,
            "parsed_summary":     summary,
            "commit_type":        commit_type,
            "features_referenced": features_referenced,
        }

        # Idempotency check — unique index on sha exists but PostgREST
        # on_conflict requires a named CONSTRAINT; use check-then-insert instead.
        existing_resp = (
            client.table("dev_commits")
            .select("id")
            .eq("sha", sha)
            .limit(1)
            .execute()
        )
        if existing_resp.data:
            self.logger.info("DevActivityAgent: commit %s already processed, skipping", sha[:12])
            return {"status": "skipped", "reason": "already processed", "sha": sha}

        client.table("dev_commits").insert(commit_row).execute()

        self.logger.info(
            "DevActivityAgent: stored commit %s — type=%s feature=%s",
            sha[:12], commit_type, feature_name,
        )

        events_emitted: list[str] = []

        # ── New feature → upsert dev_features + emit ───────────────────────────
        if commit_type == "feature" and feature_name:
            self._upsert_feature(
                client=client,
                feature_name=feature_name,
                description=summary,
                commit_sha=sha,
            )

            self.emit_event(
                event_type="feature_shipped",
                payload={
                    "feature_name":     feature_name,
                    "description":      summary,
                    "changelog_entry":  message,
                    "commit_sha":       sha,
                    "author":           author,
                    "branch":           branch,
                },
                summary=f"New feature shipped: {feature_name} — {summary}",
                priority="high",
            )
            events_emitted.append("feature_shipped")

            if notify_teams:
                self.send_notification(
                    title=f"Feature shipped: {feature_name}",
                    body=f"{summary}\n\n{analysis.get('notify_reason', '')}".strip(),
                    priority="high",
                )

        # ── Bug fix → emit ─────────────────────────────────────────────────────
        elif commit_type == "bug_fix":
            self.emit_event(
                event_type="bug_fixed",
                payload={
                    "description":       summary,
                    "severity":          severity or "minor",
                    "affected_feature":  feature_name or "unknown",
                    "commit_sha":        sha,
                    "author":            author,
                },
                summary=f"Bug fixed: {summary}",
                priority="medium",
            )
            events_emitted.append("bug_fixed")

            if notify_teams and severity in ("major", "critical"):
                self.send_notification(
                    title=f"{'Critical' if severity == 'critical' else 'Major'} bug fixed",
                    body=summary,
                    priority="high" if severity == "major" else "urgent",
                )

        # ── Release → emit ─────────────────────────────────────────────────────
        if detected_version or "release" in message.lower() or "version" in message.lower():
            version = detected_version or "unknown"
            self.emit_event(
                event_type="release_created",
                payload={
                    "version":               version,
                    "release_notes_summary": summary,
                    "commit_sha":            sha,
                    "author":                author,
                },
                summary=f"New release: v{version} — {summary}",
                priority="high",
            )
            events_emitted.append("release_created")

            self.send_notification(
                title=f"Release v{version} shipped",
                body=summary,
                priority="high",
            )

        # ── Always emit commit_pushed so PM can review every commit ──────────────
        self.emit_event(
            event_type="commit_pushed",
            payload={
                "sha":           sha,
                "message":       message[:500],
                "author":        author,
                "branch":        branch,
                "commit_type":   commit_type,
                "summary":       summary,
                "feature_name":  feature_name,
                "is_new_feature": is_new_feature,
                "notify_teams":  notify_teams,
                "notify_reason": analysis.get("notify_reason", ""),
            },
            summary=f"Commit by {author} on {branch}: {summary}",
            priority="medium" if notify_teams else "low",
        )
        events_emitted.append("commit_pushed")

        # ── Stamp last_updated on business state ───────────────────────────────
        try:
            self.update_global_context(
                "business_state.last_updated",
                datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            # Non-fatal — don't block commit processing for a context stamp failure
            self.logger.warning("DevActivityAgent: failed to stamp last_updated: %s", exc)

        return {
            "status":          "ok",
            "sha":             sha,
            "commit_type":     commit_type,
            "feature_name":    feature_name,
            "summary":         summary,
            "events_emitted":  events_emitted,
            "notify_teams":    notify_teams,
        }

    def _upsert_feature(
        self,
        client: Any,
        feature_name: str,
        description: str,
        commit_sha: str,
    ) -> None:
        """
        Insert or update a dev_features row for the given feature.
        Appends the commit SHA to related_commits without overwriting history.
        """
        existing_resp = (
            client.table("dev_features")
            .select("id, related_commits")
            .eq("feature_name", feature_name)
            .limit(1)
            .execute()
        )

        if existing_resp.data:
            # Update existing feature row, appending this SHA
            existing = existing_resp.data[0]
            related  = list(existing.get("related_commits") or [])
            if commit_sha not in related:
                related.append(commit_sha)
            client.table("dev_features").update({
                "description":     description,
                "status":          "shipped",
                "related_commits": related,
                "shipped_at":      datetime.now(timezone.utc).isoformat(),
            }).eq("id", existing["id"]).execute()
        else:
            # Insert new feature — unique index on feature_name guards duplicates
            try:
                client.table("dev_features").insert({
                    "feature_name":    feature_name,
                    "description":     description,
                    "status":          "shipped",
                    "related_commits": [commit_sha],
                    "shipped_at":      datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception:
                # Race condition: inserted between our select and insert — safe to ignore
                pass

    # ── Status check (manual run) ─────────────────────────────────────────────

    def _run_status_check(self) -> dict[str, Any]:
        """
        Return a summary of recent dev activity. Used by GET /api/dev/status
        and the manual run trigger.
        """
        domain = self._domain_context
        return {
            "status":           "ok",
            "recent_commits":   len(domain.get("recent_commits", [])),
            "shipped_features": len(domain.get("shipped_features", [])),
            "last_commit":      (
                domain["recent_commits"][0]["sha"][:12]
                if domain.get("recent_commits") else None
            ),
        }
