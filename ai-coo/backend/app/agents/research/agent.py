"""
app/agents/research/agent.py

ResearchAgent:
- discovers likely competitors
- analyzes market sentiment
- generates founder-ready insight reports
- updates competitive_landscape in global context
- emits research events

Expected trigger.parameters:
{
    "product_name": str,                 # optional, falls back to global context
    "product_description": str,          # optional, falls back to global context
    "keywords": list[str],               # optional
    "query": str,                        # optional market sentiment query
    "max_competitors": int,              # optional
    "max_sources": int                   # optional
}
"""

from __future__ import annotations

from typing import Any

from app.core.base_agent import BaseAgent
from app.schemas.triggers import AgentTrigger, TriggerType
from app.agents.research.tools import (
    analyze_market_sentiment,
    generate_insight_report,
    get_competitors,
)


class ResearchAgent(BaseAgent):
    name = "research"
    description = "Researches competitors, market sentiment, and founder-facing insights"
    subscribed_events = ["revenue_recorded"]
    writable_global_fields = ["competitive_landscape"]

    def load_domain_context(self) -> dict[str, Any]:
        # Most research persistence already happens in:
        # - research_competitors
        # - research_cache
        # - research_reports
        return {}

    def execute(self, trigger: AgentTrigger) -> dict[str, Any]:
        params = trigger.parameters or {}

        product_name = (
            params.get("product_name")
            or self._get_global_product_name()
            or "Unknown Product"
        )
        product_description = (
            params.get("product_description")
            or self._get_global_product_description()
            or "No product description provided."
        )
        keywords = params.get("keywords") or []
        max_competitors = int(params.get("max_competitors", 8))
        max_sources = int(params.get("max_sources", 12))

        query = (
            params.get("query")
            or self._build_default_query(product_name, product_description, keywords)
        )

        competitors_result = get_competitors(
            product_name=product_name,
            product_description=product_description,
            keywords=keywords,
            max_results=max_competitors,
        )
        competitors = competitors_result.get("competitors_found", [])

        sentiment_result = analyze_market_sentiment(
            query=query,
            competitor_names=[
                c["competitor_name"]
                for c in competitors
                if c.get("competitor_name")
            ],
            max_sources=max_sources,
        )

        report_result = generate_insight_report(
            product_name=product_name,
            product_description=product_description,
            competitors=competitors,
            sentiment_data=sentiment_result,
            requesting_agent=self.name,
        )

        competitive_landscape = self._build_competitive_landscape(competitors)
        self.update_global_context("competitive_landscape", competitive_landscape)

        self._emit_competitor_events(competitors)
        self._emit_trend_event(sentiment_result)
        self._emit_insight_event(report_result)

        return {
            "agent": self.name,
            "product_name": product_name,
            "query_used": query,
            "competitors": competitors_result,
            "market_sentiment": sentiment_result,
            "insight_report": report_result,
            "global_updates": {
                "competitive_landscape": competitive_landscape,
            },
        }

    def update_domain_context(self, updates: dict[str, Any]) -> None:
        # Domain state is persisted by tools.py tables already.
        return None

    def _get_global_product_name(self) -> str | None:
        company_profile = self._global_context.get("company_profile", {}) or {}
        return company_profile.get("product_name")

    def _get_global_product_description(self) -> str | None:
        company_profile = self._global_context.get("company_profile", {}) or {}
        return company_profile.get("product_description")

    def _build_default_query(
        self,
        product_name: str,
        product_description: str,
        keywords: list[str],
    ) -> str:
        if keywords:
            return f"{product_name} {' '.join(keywords[:3])}"
        short_desc = product_description[:80].strip()
        return f"{product_name} {short_desc}"

    def _build_competitive_landscape(
        self,
        competitors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        competitor_entries = []
        for competitor in competitors:
            competitor_entries.append(
                {
                    "name": competitor.get("competitor_name"),
                    "description": competitor.get("product_name") or competitor.get("website") or "",
                    "strengths": [],
                    "weaknesses": [],
                    "differentiation": "",
                    "website": competitor.get("website"),
                }
            )

        market_position = (
            f"{self._get_global_product_name() or 'Our product'} is competing in a market "
            f"with {len(competitor_entries)} identified comparable products."
        )

        return {
            "competitors": competitor_entries,
            "market_position": market_position,
        }

    def _emit_competitor_events(self, competitors: list[dict[str, Any]]) -> None:
        for competitor in competitors[:10]:
            name = competitor.get("competitor_name")
            if not name:
                continue

            self.emit_event(
                event_type="competitor_found",
                payload={
                    "competitor_name": name,
                    "product_name": competitor.get("product_name"),
                    "website": competitor.get("website"),
                },
                summary=f"Research found competitor {name}.",
                priority="medium",
            )

    def _emit_trend_event(self, sentiment_result: dict[str, Any]) -> None:
        themes = sentiment_result.get("theme_summary", []) or []
        if not themes:
            return

        top_theme = themes[0]
        theme_name = str(top_theme.get("theme", "unknown")).replace("_", " ")

        self.emit_event(
            event_type="trend_found",
            payload={
                "theme": top_theme.get("theme"),
                "sentiment": top_theme.get("sentiment"),
                "frequency": top_theme.get("frequency"),
                "share_of_sources": top_theme.get("share_of_sources"),
            },
            summary=f"Research found a market trend around '{theme_name}'.",
            priority="medium",
        )

    def _emit_insight_event(self, report_result: dict[str, Any]) -> None:
        self.emit_event(
            event_type="insight_discovered",
            payload={
                "executive_summary": report_result.get("executive_summary"),
                "recommended_actions": report_result.get("recommended_actions", []),
                "saved_report_id": report_result.get("saved_report_id"),
            },
            summary=report_result.get(
                "executive_summary",
                "Research generated a new market insight report.",
            ),
            priority="high",
        )