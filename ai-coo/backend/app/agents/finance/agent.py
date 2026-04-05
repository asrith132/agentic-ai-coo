"""
app/agents/finance/agent.py — FinanceAgent

Tracks financial health:
  - Emits: runway_warning, spending_anomaly, weekly_summary, revenue_recorded
  - Writes: business_state.runway_months, business_state.monthly_burn, business_state.key_metrics
"""

from __future__ import annotations

from datetime import date
from typing import Any

from supabase import Client

from app.core.base_agent import BaseAgent
from app.db.supabase_client import get_client as _get_supabase_singleton
from app.schemas.triggers import AgentTrigger
from app.agents.finance.tools import (
    FinanceDataError,
    compute_financial_snapshot,
    detect_spending_anomalies,
    generate_plain_english_summary,
    ingest_financial_csv,
)


class FinanceAgent(BaseAgent):
    name = "finance"
    description = "Tracks expenses, revenue, runway and financial health"
    subscribed_events = []
    writable_global_fields = [
        "business_state.runway_months",
        "business_state.monthly_burn",
        "business_state.key_metrics",
    ]

    def load_domain_context(self) -> dict[str, Any]:
        """
        Finance state is primarily stored in:
          - finance_transactions
          - finance_snapshots

        Return a lightweight summary for the current run.
        """
        try:
            supabase = self._get_supabase()

            tx_resp = (
                supabase.table("finance_transactions")
                .select("id", count="exact")
                .execute()
            )
            snap_resp = (
                supabase.table("finance_snapshots")
                .select("*")
                .order("month", desc=True)
                .limit(1)
                .execute()
            )

            latest_snapshot = snap_resp.data[0] if snap_resp.data else None
            transaction_count = tx_resp.count if hasattr(tx_resp, "count") else len(tx_resp.data or [])

            return {
                "transaction_count": transaction_count,
                "latest_snapshot": latest_snapshot,
            }
        except Exception:
            # Keep agent resilient for MVP if DB is not ready yet
            return {
                "transaction_count": 0,
                "latest_snapshot": None,
            }

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        payload = trigger.parameters or {}

        csv_content = payload.get("csv_content")
        month = payload.get("month")
        current_balance = payload.get("current_balance")
        notes = payload.get("notes")
        replace_existing = payload.get("replace_existing", False)

        ingestion_result: dict[str, Any] | None = None

        # 1. Ingest CSV if provided
        if csv_content:
            ingestion_result = ingest_financial_csv(
                csv_content=csv_content,
                notes=notes,
                replace_existing=replace_existing,
            )

            if not month and ingestion_result.get("date_range"):
                month = ingestion_result["date_range"]["end"][:7] + "-01"

            if current_balance is None:
                current_balance = ingestion_result.get("latest_balance")

        # 2. Default month if not supplied
        if not month:
            latest_snapshot = self._domain_context.get("latest_snapshot")
            if latest_snapshot and latest_snapshot.get("month"):
                month = latest_snapshot["month"]
            else:
                month = date.today().replace(day=1).isoformat()

        # 3. Compute snapshot
        snapshot = compute_financial_snapshot(
            month=month,
            current_balance=current_balance,
        )

        # 4. Detect anomalies
        try:
            anomalies = detect_spending_anomalies(month=snapshot["month"])
        except FinanceDataError:
            anomalies = []

        # 5. Generate summary
        summary = generate_plain_english_summary(snapshot, anomalies)

        # 6. Update global context
        self.update_global_context(
            "business_state.runway_months",
            snapshot.get("runway_months"),
        )
        self.update_global_context(
            "business_state.monthly_burn",
            snapshot.get("total_expenses"),
        )
        self.update_global_context(
            "business_state.key_metrics",
            {
                "revenue": snapshot.get("total_income"),
            },
        )

        # 7. Emit weekly summary event
        self.emit_event(
            event_type="weekly_summary",
            payload={
                "total_spent": float(snapshot.get("total_expenses") or 0),
                "top_categories": self._top_categories(snapshot),
                "runway_months": snapshot.get("runway_months"),
                "plain_english_summary": summary,
                "month": snapshot.get("month"),
            },
            summary=summary,
            priority="medium",
        )

        # 8. Emit revenue event if income exists
        total_income = float(snapshot.get("total_income") or 0)
        if total_income > 0:
            self.emit_event(
                event_type="revenue_recorded",
                payload={
                    "amount": total_income,
                    "source": "csv_import",
                    "is_recurring": False,
                    "month": snapshot.get("month"),
                },
                summary=f"Recorded ${total_income:,.2f} in revenue for {snapshot.get('month')}.",
                priority="medium",
            )

        # 9. Emit runway warning if needed
        runway_months = snapshot.get("runway_months")
        if runway_months is not None and float(runway_months) <= 6:
            self.emit_event(
                event_type="runway_warning",
                payload={
                    "months_remaining": float(runway_months),
                    "threshold": 6,
                    "suggested_action": "Prioritize revenue-generating work and reduce discretionary spend.",
                },
                summary=f"Runway is down to {float(runway_months):.1f} months.",
                priority="high",
            )

        # 10. Emit anomaly events
        for anomaly in anomalies:
            self.emit_event(
                event_type="spending_anomaly",
                payload={
                    "category": anomaly.get("category"),
                    "amount": anomaly.get("amount"),
                    "deviation_from_average": anomaly.get("deviation_percent"),
                    "description": anomaly.get("description"),
                },
                summary=anomaly.get("description", "Spending anomaly detected."),
                priority="high",
            )

        return {
            "agent": self.name,
            "ingestion": ingestion_result,
            "snapshot": snapshot,
            "anomalies": anomalies,
            "summary": summary,
            "global_updates": {
                "business_state.runway_months": snapshot.get("runway_months"),
                "business_state.monthly_burn": snapshot.get("total_expenses"),
                "business_state.key_metrics": {
                    "revenue": snapshot.get("total_income"),
                },
            },
        }

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        """
        Most finance persistence happens inside tools.py via Supabase tables.
        Keep this as a no-op for now unless you later add separate finance state tables.
        """
        return None

    def _top_categories(self, snapshot: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
        by_category = snapshot.get("by_category") or {}
        sorted_categories = sorted(
            by_category.items(),
            key=lambda item: float(item[1]),
            reverse=True,
        )[:limit]

        return [
            {"category": category, "amount": float(amount)}
            for category, amount in sorted_categories
        ]

    def _get_supabase(self) -> Client:
        return _get_supabase_singleton()