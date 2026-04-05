"""
tests/agents/legal/test_tools.py

Pure-function tests for app/agents/legal/tools.py.
No DB, no LLM, no mocking needed — these run entirely in-process.
"""

import json
import pytest
from datetime import date, timedelta

from app.agents.legal.tools import (
    resolve_due_date,
    days_until,
    urgency_from_days,
    document_type_for_item,
    parse_checklist_json,
    build_checklist_prompt,
    build_document_prompt,
)


# ── resolve_due_date ──────────────────────────────────────────────────────────

class TestResolveDueDate:
    TODAY = date(2026, 4, 4)

    def test_within_days(self):
        d = resolve_due_date("within 30 days", self.TODAY)
        assert d == self.TODAY + timedelta(days=30)

    def test_within_days_of_incorporation(self):
        d = resolve_due_date("within 90 days of incorporation", self.TODAY)
        assert d == self.TODAY + timedelta(days=90)

    def test_within_months(self):
        d = resolve_due_date("within 3 months", self.TODAY)
        # 3 months from 2026-04-04 → 2026-07-04
        assert d == date(2026, 7, 4)

    def test_within_months_end_of_month_overflow(self):
        start = date(2026, 1, 31)
        d = resolve_due_date("within 1 month", start)
        # Feb doesn't have 31 days — should clamp to Feb 28
        assert d == date(2026, 2, 28)

    def test_within_weeks(self):
        d = resolve_due_date("within 2 weeks", self.TODAY)
        assert d == self.TODAY + timedelta(weeks=2)

    def test_within_year(self):
        d = resolve_due_date("within 1 year", self.TODAY)
        assert d == date(2027, 4, 4)

    def test_annually_by_month_day_future(self):
        # March 1 hasn't passed yet relative to TODAY=April 4 — so next year
        d = resolve_due_date("annually by March 1", self.TODAY)
        assert d == date(2027, 3, 1)

    def test_annually_by_month_day_this_year(self):
        # "by June 15" — June hasn't passed yet for April 4
        d = resolve_due_date("by June 15", self.TODAY)
        assert d == date(2026, 6, 15)

    def test_annually_by_month_day_already_passed(self):
        # "by January 1" — already passed in 2026, should roll to 2027
        d = resolve_due_date("by January 1", self.TODAY)
        assert d == date(2027, 1, 1)

    def test_quarterly(self):
        # From April 4, next quarter end is June 30
        d = resolve_due_date("quarterly", self.TODAY)
        assert d == date(2026, 6, 30)

    def test_immediately(self):
        d = resolve_due_date("immediately", self.TODAY)
        assert d == self.TODAY

    def test_upon_incorporation(self):
        d = resolve_due_date("upon incorporation", self.TODAY)
        assert d == self.TODAY

    def test_at_formation(self):
        d = resolve_due_date("at formation", self.TODAY)
        assert d == self.TODAY

    def test_unparseable_returns_none(self):
        d = resolve_due_date("when legally required", self.TODAY)
        assert d is None

    def test_empty_string_returns_none(self):
        d = resolve_due_date("", self.TODAY)
        assert d is None


# ── days_until ────────────────────────────────────────────────────────────────

class TestDaysUntil:
    def test_future_positive(self):
        future = date.today() + timedelta(days=10)
        assert days_until(future) == 10

    def test_past_negative(self):
        past = date.today() - timedelta(days=5)
        assert days_until(past) == -5

    def test_today_is_zero(self):
        assert days_until(date.today()) == 0


# ── urgency_from_days ─────────────────────────────────────────────────────────

class TestUrgencyFromDays:
    def test_overdue(self):
        assert urgency_from_days(-1) == "urgent"
        assert urgency_from_days(-100) == "urgent"

    def test_today(self):
        assert urgency_from_days(0) == "high"

    def test_within_7_days(self):
        assert urgency_from_days(1) == "high"
        assert urgency_from_days(7) == "high"

    def test_8_to_14_days(self):
        assert urgency_from_days(8) == "medium"
        assert urgency_from_days(14) == "medium"

    def test_beyond_14_days(self):
        assert urgency_from_days(15) == "low"
        assert urgency_from_days(365) == "low"


# ── document_type_for_item ────────────────────────────────────────────────────

class TestDocumentTypeForItem:
    def test_tos(self):
        assert document_type_for_item("Draft Terms of Service") == "tos"
        assert document_type_for_item("Terms of Use Agreement") == "tos"

    def test_privacy_policy(self):
        assert document_type_for_item("Privacy Policy") == "privacy_policy"
        assert document_type_for_item("GDPR Privacy Notice") == "privacy_policy"

    def test_nda(self):
        assert document_type_for_item("NDA Template") == "nda"
        assert document_type_for_item("Non-Disclosure Agreement") == "nda"
        assert document_type_for_item("Mutual Confidentiality Agreement") == "nda"

    def test_contractor_agreement(self):
        assert document_type_for_item("Contractor Agreement") == "contractor_agreement"
        assert document_type_for_item("Consulting Agreement") == "contractor_agreement"

    def test_employee_agreement(self):
        assert document_type_for_item("Employee Agreement") == "employee_agreement"
        assert document_type_for_item("Offer Letter") == "employee_agreement"

    def test_ip_assignment(self):
        assert document_type_for_item("IP Assignment Agreement") == "ip_assignment"
        assert document_type_for_item("Intellectual Property Assignment") == "ip_assignment"

    def test_incorporation(self):
        assert document_type_for_item("Certificate of Incorporation") == "incorporation"
        assert document_type_for_item("Articles of Formation") == "incorporation"

    def test_fallback_other(self):
        assert document_type_for_item("Board Meeting Minutes") == "other"
        assert document_type_for_item("Stock Option Plan") == "other"

    def test_case_insensitive(self):
        assert document_type_for_item("TERMS OF SERVICE") == "tos"
        assert document_type_for_item("privacy policy") == "privacy_policy"


# ── parse_checklist_json ──────────────────────────────────────────────────────

class TestParseChecklistJson:
    VALID_ITEM = {
        "item": "File Articles of Incorporation",
        "description": "Register your company with the state.",
        "category": "incorporation",
        "priority": "urgent",
        "deadline_rule": "within 30 days",
        "typically_overdue": False,
    }

    def test_clean_json_array(self):
        raw = json.dumps([self.VALID_ITEM])
        result = parse_checklist_json(raw)
        assert len(result) == 1
        assert result[0]["item"] == "File Articles of Incorporation"

    def test_json_with_markdown_fence(self):
        raw = f"```json\n{json.dumps([self.VALID_ITEM])}\n```"
        result = parse_checklist_json(raw)
        assert result[0]["category"] == "incorporation"

    def test_json_with_plain_fence(self):
        raw = f"```\n{json.dumps([self.VALID_ITEM])}\n```"
        result = parse_checklist_json(raw)
        assert len(result) == 1

    def test_json_with_preamble(self):
        raw = f"Here is the checklist:\n\n{json.dumps([self.VALID_ITEM])}"
        result = parse_checklist_json(raw)
        assert result[0]["priority"] == "urgent"

    def test_multiple_items(self):
        items = [self.VALID_ITEM, {**self.VALID_ITEM, "item": "Get EIN"}]
        result = parse_checklist_json(json.dumps(items))
        assert len(result) == 2

    def test_malformed_raises_value_error(self):
        with pytest.raises(ValueError, match="Could not parse"):
            parse_checklist_json("This is not JSON at all.")

    def test_object_not_array_raises(self):
        with pytest.raises(ValueError):
            parse_checklist_json('{"item": "test"}')  # object, not array


# ── build_checklist_prompt ────────────────────────────────────────────────────

class TestBuildChecklistPrompt:
    def test_contains_all_inputs(self):
        prompt = build_checklist_prompt("C-Corp", "Delaware, USA", "seed", "SaaS")
        assert "C-Corp" in prompt
        assert "Delaware, USA" in prompt
        assert "seed" in prompt
        assert "SaaS" in prompt

    def test_requests_json_output(self):
        prompt = build_checklist_prompt("LLC", "California", "pre_launch", "marketplace")
        assert "JSON" in prompt

    def test_specifies_required_fields(self):
        prompt = build_checklist_prompt("C-Corp", "Delaware, USA", "seed", "SaaS")
        assert "category" in prompt
        assert "priority" in prompt
        assert "deadline_rule" in prompt


# ── build_document_prompt ─────────────────────────────────────────────────────

class TestBuildDocumentPrompt:
    def test_contains_company_details(self):
        prompt = build_document_prompt(
            document_type="privacy_policy",
            company_name="Acme Inc",
            product_name="AcmePlatform",
            product_description="A SaaS analytics tool",
            jurisdiction="Delaware, USA",
            stage="seed",
            product_type="SaaS",
        )
        assert "Acme Inc" in prompt
        assert "AcmePlatform" in prompt
        assert "Delaware, USA" in prompt
        assert "Privacy Policy" in prompt

    def test_no_placeholder_brackets(self):
        prompt = build_document_prompt(
            document_type="tos",
            company_name="TestCo",
            product_name="TestProduct",
            product_description="A tool",
            jurisdiction="England and Wales",
            stage="launched",
            product_type="SaaS",
        )
        # The prompt instructs the LLM not to use placeholders, so actual
        # fill-in-blank tokens like [COMPANY_NAME] should not appear.
        # (The word "[PLACEHOLDER]" does appear as an anti-example in the
        #  requirements text, so we check for specific fill-in patterns instead.)
        assert "[COMPANY_NAME]" not in prompt
        assert "[PRODUCT_NAME]" not in prompt
        assert "[JURISDICTION]" not in prompt
        assert "[DATE]" not in prompt

    def test_extra_context_included(self):
        prompt = build_document_prompt(
            document_type="nda",
            company_name="Co",
            product_name="Prod",
            product_description="desc",
            jurisdiction="NY",
            stage="pre_launch",
            product_type="SaaS",
            extra_context="This NDA is for a partnership with BigCorp.",
        )
        assert "BigCorp" in prompt
