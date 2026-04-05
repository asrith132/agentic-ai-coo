"""
tests/agents/legal/test_agent.py

Integration-style tests for LegalAgent.execute() and all private helpers.
All DB and LLM calls are mocked — no Supabase or Anthropic needed.

Mocking strategy:
  - get_client()      → MagicMock with chainable query builder
  - agent.llm_chat()  → patched directly on the instance
  - emit_event / send_notification / request_approval / mark_consumed
                      → patched on the instance so we can assert call counts
"""

import json
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call, PropertyMock

from app.agents.legal.agent import LegalAgent
from app.schemas.context import (
    GlobalContext, CompanyProfile, BusinessState,
    BrandVoice, TargetCustomer, CompetitiveLandscape,
)
from app.schemas.events import Event
from app.schemas.approvals import Approval
from app.schemas.triggers import AgentTrigger, TriggerType


# ── Shared fixtures ───────────────────────────────────────────────────────────

def make_global_context(**overrides) -> GlobalContext:
    cp_kwargs = dict(
        name="Acme Inc", product_name="AcmePlatform",
        product_description="B2B SaaS analytics tool",
        jurisdiction="Delaware, USA", tech_stack=["Python", "React"],
    )
    cp_kwargs.update(overrides.pop("company_profile", {}))
    return GlobalContext(
        company_profile=CompanyProfile(**cp_kwargs),
        business_state=BusinessState(phase="launched"),
        brand_voice=BrandVoice(tone="Direct"),
        target_customer=TargetCustomer(),
        competitive_landscape=CompetitiveLandscape(),
    )


def make_agent(ctx: GlobalContext | None = None) -> LegalAgent:
    """Return a LegalAgent with _global_context pre-loaded (bypasses run())."""
    agent = LegalAgent()
    agent._global_context = ctx or make_global_context()
    agent._domain_context = {}
    return agent


def chainable_db(data_per_call: list | None = None) -> MagicMock:
    """
    Build a Supabase mock where every .execute() call returns the next item
    from data_per_call (wraps in MagicMock(data=...)). If data_per_call is
    not provided, .execute() returns MagicMock(data=[]).

    The mock is fully chainable: .table().select().eq().execute() all work.
    """
    responses = []
    for d in (data_per_call or []):
        r = MagicMock()
        r.data = d
        responses.append(r)

    # Fall-through response for unexpected extra calls
    fallthrough = MagicMock()
    fallthrough.data = []

    mock = MagicMock()
    chain = MagicMock()

    side_effects = iter(responses)

    def execute_side_effect():
        try:
            return next(side_effects)
        except StopIteration:
            return fallthrough

    chain.execute.side_effect = execute_side_effect
    # Make every method on chain return chain itself (fluent interface)
    for method in [
        "select", "insert", "update", "delete",
        "eq", "neq", "lte", "gte", "in_",
        "order", "limit", "maybe_single", "single",
        "is_",
    ]:
        getattr(chain, method).return_value = chain

    # not_ is accessed as an attribute, not called
    not_obj = MagicMock()
    not_obj.is_.return_value = chain
    not_obj.contains.return_value = chain
    chain.not_ = not_obj

    mock.table.return_value = chain
    return mock


SAMPLE_CHECKLIST_ITEM = {
    "id": "item-uuid-1",
    "item": "Draft Privacy Policy",
    "description": "A privacy policy is required by law in most jurisdictions.",
    "category": "privacy",
    "priority": "high",
    "status": "pending",
    "due_date": None,
    "notes": "Deadline rule: within 30 days",
}

SAMPLE_DOCUMENT = {
    "id": "doc-uuid-1",
    "document_type": "privacy_policy",
    "title": "Privacy Policy — Acme Inc",
    "content": "This is the privacy policy content...",
    "status": "draft",
    "checklist_item_id": "item-uuid-1",
    "approval_id": None,
}

SAMPLE_APPROVAL = Approval(
    id="appr-uuid-1",
    agent="legal",
    action_type="mark_document_final",
    content={"document_id": "doc-uuid-1"},
    status="pending",
)

LLM_CHECKLIST_RESPONSE = json.dumps([
    {
        "item": "Register Business Entity",
        "description": "File with the Secretary of State.",
        "category": "incorporation",
        "priority": "urgent",
        "deadline_rule": "within 30 days",
        "typically_overdue": False,
    },
    {
        "item": "Draft Privacy Policy",
        "description": "Required by GDPR and CCPA.",
        "category": "privacy",
        "priority": "high",
        "deadline_rule": "within 60 days",
        "typically_overdue": False,
    },
])

LLM_DOCUMENT_TEXT = "PRIVACY POLICY\n\nLast updated: April 2026\n\n1. Introduction..."


# ═══════════════════════════════════════════════════════════════════════════════
# load_domain_context
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadDomainContext:
    def test_returns_counts_and_recent_docs(self):
        agent = make_agent()
        checklist_rows = [
            {"status": "pending"}, {"status": "pending"}, {"status": "done"}
        ]
        doc_rows = [SAMPLE_DOCUMENT]
        db = chainable_db([checklist_rows, doc_rows])

        with patch("app.agents.legal.agent.get_client", return_value=db):
            result = agent.load_domain_context()

        assert result["checklist_status_counts"] == {"pending": 2, "done": 1}
        assert result["total_checklist_items"] == 3
        assert len(result["recent_documents"]) == 1

    def test_empty_db_returns_zeros(self):
        agent = make_agent()
        db = chainable_db([[], []])
        with patch("app.agents.legal.agent.get_client", return_value=db):
            result = agent.load_domain_context()
        assert result["total_checklist_items"] == 0
        assert result["recent_documents"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# _generate_checklist
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerateChecklist:
    def _run(self, llm_response=LLM_CHECKLIST_RESPONSE, db_returns=None):
        agent = make_agent()
        # Each LLM-produced item gets inserted individually → 2 insert calls
        created_rows = db_returns or [
            [{"id": f"uuid-{i}", **{
                "item": f"Item {i}", "description": "desc", "category": "incorporation",
                "priority": "urgent", "status": "pending", "due_date": None,
            }}]
            for i in range(2)
        ]
        db = chainable_db(created_rows)

        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=llm_response), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification") as mock_notify:
            result = agent._generate_checklist({
                "entity_type": "C-Corp",
                "jurisdiction": "Delaware, USA",
                "stage": "seed",
                "product_type": "SaaS",
            })
        return result, mock_emit, mock_notify

    def test_success_returns_correct_counts(self):
        result, _, _ = self._run()
        assert result["status"] == "ok"
        assert result["items_created"] == 2
        assert result["overdue_count"] == 0

    def test_llm_called_with_low_temperature(self):
        agent = make_agent()
        db = chainable_db([[{"id": "u1", "item": "x", "description": "d",
                              "category": "tax", "priority": "medium",
                              "status": "pending", "due_date": None}]])
        single_item = json.dumps([{
            "item": "x", "description": "d", "category": "tax",
            "priority": "medium", "deadline_rule": "within 30 days",
            "typically_overdue": False,
        }])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=single_item) as mock_llm, \
             patch.object(agent, "emit_event"), \
             patch.object(agent, "send_notification"):
            agent._generate_checklist({"entity_type": "C-Corp", "jurisdiction": "DE",
                                        "stage": "seed", "product_type": "SaaS"})
        _, kwargs = mock_llm.call_args
        assert kwargs.get("temperature", 1.0) <= 0.5

    def test_overdue_item_emits_event_and_notifies(self):
        yesterday = date.today() - timedelta(days=1)
        overdue_llm = json.dumps([{
            "item": "File Annual Report",
            "description": "Overdue annual filing.",
            "category": "compliance",
            "priority": "urgent",
            "deadline_rule": "by January 1",  # any rule — we patch resolve_due_date below
            "typically_overdue": True,
        }])
        inserted = [{"id": "uuid-0", "item": "File Annual Report",
                     "description": "desc", "category": "compliance",
                     "priority": "urgent", "status": "overdue",
                     "due_date": yesterday.isoformat()}]
        agent = make_agent()
        db = chainable_db([inserted])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=overdue_llm), \
             patch("app.agents.legal.agent.resolve_due_date", return_value=yesterday) \
             as mock_resolve, \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification") as mock_notify:
            result = agent._generate_checklist({"entity_type": "C-Corp",
                                                "jurisdiction": "DE",
                                                "stage": "seed",
                                                "product_type": "SaaS"})
        assert result["overdue_count"] == 1
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args.kwargs
        assert call_kwargs["event_type"] == "legal.deadline_approaching"
        assert call_kwargs["priority"] == "urgent"
        mock_notify.assert_called_once()

    def test_invalid_llm_json_raises_runtime_error(self):
        agent = make_agent()
        with patch("app.agents.legal.agent.get_client"), \
             patch.object(agent, "llm_chat", return_value="not json at all"):
            with pytest.raises(RuntimeError, match="Failed to parse checklist"):
                agent._generate_checklist({})

    def test_checklist_prompt_contains_inputs(self):
        agent = make_agent()
        db = chainable_db([[{"id": "u", "item": "x", "description": "d",
                              "category": "tax", "priority": "medium",
                              "status": "pending", "due_date": None}]])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=json.dumps([{
                 "item": "x", "description": "d", "category": "tax",
                 "priority": "medium", "deadline_rule": "within 30 days",
                 "typically_overdue": False}])) as mock_llm, \
             patch.object(agent, "emit_event"), patch.object(agent, "send_notification"):
            agent._generate_checklist({"entity_type": "LLC", "jurisdiction": "Wyoming",
                                        "stage": "pre_launch", "product_type": "marketplace"})
        user_msg = mock_llm.call_args.kwargs["user_message"]
        assert "LLC" in user_msg
        assert "Wyoming" in user_msg
        assert "marketplace" in user_msg


# ═══════════════════════════════════════════════════════════════════════════════
# _draft_document
# ═══════════════════════════════════════════════════════════════════════════════

class TestDraftDocument:
    def _run(self, checklist_item=None, llm_text=LLM_DOCUMENT_TEXT):
        agent = make_agent()
        item = checklist_item or SAMPLE_CHECKLIST_ITEM
        # DB calls: maybe_single (load item), insert (doc), update (approval_id), update (checklist)
        db = chainable_db([
            item,                  # maybe_single → returns the item directly
            [SAMPLE_DOCUMENT],     # insert legal_documents
            [SAMPLE_DOCUMENT],     # update approval_id
            [item],                # update checklist status
        ])
        mock_approval = SAMPLE_APPROVAL

        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=llm_text), \
             patch.object(agent, "request_approval", return_value=mock_approval), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification") as mock_notify:
            result = agent._draft_document("item-uuid-1", {})
        return result, mock_emit, mock_notify

    def test_returns_document_id_and_approval_id(self):
        result, _, _ = self._run()
        assert result["status"] == "ok"
        assert result["document_id"] == "doc-uuid-1"
        assert result["approval_id"] == "appr-uuid-1"

    def test_infers_correct_document_type(self):
        result, _, _ = self._run()
        assert result["document_type"] == "privacy_policy"

    def test_emits_document_drafted_event(self):
        _, mock_emit, _ = self._run()
        mock_emit.assert_called_once()
        assert mock_emit.call_args.kwargs["event_type"] == "legal.document_drafted"

    def test_sends_notification(self):
        _, _, mock_notify = self._run()
        mock_notify.assert_called_once()

    def test_empty_checklist_item_id_raises(self):
        agent = make_agent()
        with pytest.raises(ValueError, match="checklist_item_id is required"):
            agent._draft_document("", {})

    def test_item_not_found_raises(self):
        agent = make_agent()
        db = chainable_db([None])   # maybe_single returns None
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat"):
            with pytest.raises(ValueError, match="not found"):
                agent._draft_document("nonexistent-id", {})

    def test_llm_receives_company_name(self):
        agent = make_agent()
        db = chainable_db([
            SAMPLE_CHECKLIST_ITEM,
            [SAMPLE_DOCUMENT], [SAMPLE_DOCUMENT], [SAMPLE_CHECKLIST_ITEM],
        ])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=LLM_DOCUMENT_TEXT) as mock_llm, \
             patch.object(agent, "request_approval", return_value=SAMPLE_APPROVAL), \
             patch.object(agent, "emit_event"), patch.object(agent, "send_notification"):
            agent._draft_document("item-uuid-1", {})
        user_msg = mock_llm.call_args.kwargs["user_message"]
        assert "Acme Inc" in user_msg

    def test_extra_context_passed_to_llm(self):
        agent = make_agent()
        db = chainable_db([
            SAMPLE_CHECKLIST_ITEM,
            [SAMPLE_DOCUMENT], [SAMPLE_DOCUMENT], [SAMPLE_CHECKLIST_ITEM],
        ])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "llm_chat", return_value=LLM_DOCUMENT_TEXT) as mock_llm, \
             patch.object(agent, "request_approval", return_value=SAMPLE_APPROVAL), \
             patch.object(agent, "emit_event"), patch.object(agent, "send_notification"):
            agent._draft_document("item-uuid-1", {"context": "Focus on GDPR compliance."})
        user_msg = mock_llm.call_args.kwargs["user_message"]
        assert "GDPR" in user_msg


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_approval_callback
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleApprovalCallback:
    def test_marks_document_final_via_nested_content(self):
        """Bug 4 fix: document_id lives under params['content']['document_id']."""
        agent = make_agent()
        db = chainable_db([[SAMPLE_DOCUMENT], [SAMPLE_CHECKLIST_ITEM]])
        params = {
            "approval_id": "appr-1",
            "action_type": "mark_document_final",
            "content": {
                "document_id":       "doc-uuid-1",
                "checklist_item_id": "item-uuid-1",
                "title":             "Privacy Policy — Acme",
            },
        }
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "send_notification"):
            result = agent._handle_approval_callback(params)

        assert result["status"] == "ok"
        assert result["document_id"] == "doc-uuid-1"
        assert result["document_status"] == "final"

    def test_marks_document_final_via_flat_params(self):
        """Also works when document_id is at the top level (backward compat)."""
        agent = make_agent()
        db = chainable_db([[SAMPLE_DOCUMENT], [SAMPLE_CHECKLIST_ITEM]])
        params = {"document_id": "doc-uuid-1", "checklist_item_id": "item-uuid-1", "content": {}}
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "send_notification"):
            result = agent._handle_approval_callback(params)
        assert result["status"] == "ok"

    def test_skips_when_no_document_id(self):
        agent = make_agent()
        result = agent._handle_approval_callback({"content": {}, "action_type": "mark_document_final"})
        assert result["status"] == "skipped"
        assert "no document_id" in result["reason"]

    def test_sends_notification_on_success(self):
        agent = make_agent()
        db = chainable_db([[SAMPLE_DOCUMENT], [SAMPLE_CHECKLIST_ITEM]])
        params = {"content": {"document_id": "doc-uuid-1", "checklist_item_id": "item-uuid-1"}}
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "send_notification") as mock_notify:
            agent._handle_approval_callback(params)
        mock_notify.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# _run_deadline_check
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunDeadlineCheck:
    def test_no_items_returns_zero(self):
        agent = make_agent()
        with patch("app.agents.legal.agent.get_pending_checklist_items", return_value=[]):
            result = agent._run_deadline_check()
        assert result == {"status": "ok", "deadlines_found": 0}

    def test_overdue_item_gets_urgent_event(self):
        agent = make_agent()
        yesterday = (date.today() - timedelta(days=3)).isoformat()
        items = [{
            "id": "item-1", "item": "File Annual Report",
            "description": "Annual compliance filing.",
            "status": "pending", "due_date": yesterday,
        }]
        db = chainable_db([[{"id": "item-1", "status": "overdue"}]])
        with patch("app.agents.legal.agent.get_pending_checklist_items", return_value=items), \
             patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification"):
            result = agent._run_deadline_check()

        assert result["reminders_sent"] == 1
        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["urgency"] == "urgent"
        assert payload["days_remaining"] < 0

    def test_upcoming_item_gets_correct_priority(self):
        agent = make_agent()
        in_5_days = (date.today() + timedelta(days=5)).isoformat()
        items = [{
            "id": "item-2", "item": "Renew Domain",
            "description": "Annual domain renewal.",
            "status": "pending", "due_date": in_5_days,
        }]
        with patch("app.agents.legal.agent.get_pending_checklist_items", return_value=items), \
             patch("app.agents.legal.agent.get_client"), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification"):
            result = agent._run_deadline_check()

        payload = mock_emit.call_args.kwargs["payload"]
        assert payload["urgency"] == "high"   # 5 days → high
        assert payload["days_remaining"] == 5

    def test_overdue_item_updates_db_status(self):
        agent = make_agent()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        items = [{"id": "item-3", "item": "Tax Filing", "description": "desc",
                  "status": "pending", "due_date": yesterday}]
        db = chainable_db([[{"id": "item-3"}]])
        with patch("app.agents.legal.agent.get_pending_checklist_items", return_value=items), \
             patch("app.agents.legal.agent.get_client", return_value=db) as mock_get_client, \
             patch.object(agent, "emit_event"), patch.object(agent, "send_notification"):
            agent._run_deadline_check()
        # Verify the DB update call was made
        assert mock_get_client.called

    def test_multiple_items_all_processed(self):
        agent = make_agent()
        dates = [
            (date.today() - timedelta(days=2)).isoformat(),  # overdue
            (date.today() + timedelta(days=5)).isoformat(),  # high
            (date.today() + timedelta(days=12)).isoformat(), # medium
        ]
        items = [
            {"id": f"i-{i}", "item": f"Item {i}", "description": "d",
             "status": "pending", "due_date": d}
            for i, d in enumerate(dates)
        ]
        db = chainable_db([[{"id": "i-0"}]])  # one DB update for overdue
        with patch("app.agents.legal.agent.get_pending_checklist_items", return_value=items), \
             patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification") as mock_notify:
            result = agent._run_deadline_check()

        assert result["reminders_sent"] == 3
        assert mock_emit.call_count == 3
        assert mock_notify.call_count == 3

    def test_item_without_due_date_is_skipped(self):
        agent = make_agent()
        items = [{"id": "i-1", "item": "No deadline item", "description": "d",
                  "status": "pending", "due_date": None}]
        with patch("app.agents.legal.agent.get_pending_checklist_items", return_value=items), \
             patch.object(agent, "emit_event") as mock_emit:
            result = agent._run_deadline_check()
        assert mock_emit.call_count == 0
        assert result["reminders_sent"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_lead_converted
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleLeadConverted:
    def _make_event(self, conversion_type="customer"):
        return Event(
            id="ev-1", event_type="lead_converted", source_agent="outreach",
            payload={"conversion_type": conversion_type}, summary="Lead converted",
            priority="medium",
        )

    def test_customer_with_no_tos_creates_checklist_item(self):
        agent = make_agent()
        new_item = {**SAMPLE_CHECKLIST_ITEM, "item": "Draft Terms of Service"}
        db = chainable_db([[new_item]])
        with patch("app.agents.legal.agent.get_existing_documents", return_value=[]), \
             patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification") as mock_notify:
            result = agent._handle_lead_converted(self._make_event("customer"))

        assert result["tos_exists"] is False
        assert "checklist_item_created" in result
        # Should emit compliance_gap_found
        mock_emit.assert_called_once()
        assert mock_emit.call_args.kwargs["event_type"] == "legal.compliance_gap_found"
        mock_notify.assert_called_once()

    def test_customer_with_existing_tos_skips(self):
        agent = make_agent()
        with patch("app.agents.legal.agent.get_existing_documents",
                   return_value=[{"id": "tos-1", "title": "ToS", "status": "final"}]), \
             patch.object(agent, "emit_event") as mock_emit:
            result = agent._handle_lead_converted(self._make_event("customer"))

        assert result["tos_exists"] is True
        mock_emit.assert_not_called()

    def test_non_customer_conversion_is_skipped(self):
        agent = make_agent()
        with patch.object(agent, "emit_event") as mock_emit:
            result = agent._handle_lead_converted(self._make_event("investor"))
        assert result["skipped"] is True
        mock_emit.assert_not_called()

    def test_inserted_item_has_no_due_date(self):
        """Bug 2 fix: due_date should be None, not a NameError placeholder."""
        agent = make_agent()
        db = chainable_db([[{**SAMPLE_CHECKLIST_ITEM, "item": "Draft Terms of Service",
                              "due_date": None}]])
        captured_insert = {}

        original_table = MagicMock()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(
            data=[{**SAMPLE_CHECKLIST_ITEM, "item": "Draft Terms of Service"}]
        )
        for m in ["select", "eq", "order", "limit", "maybe_single"]:
            getattr(chain, m).return_value = chain

        def capture_insert(row):
            captured_insert.update(row)
            return chain
        chain.insert.side_effect = capture_insert
        chain.not_ = MagicMock()
        chain.not_.is_.return_value = chain
        original_table.return_value = chain

        with patch("app.agents.legal.agent.get_existing_documents", return_value=[]), \
             patch("app.agents.legal.agent.get_client") as mock_gc, \
             patch.object(agent, "emit_event"), patch.object(agent, "send_notification"):
            mock_gc.return_value.table.return_value = chain
            agent._handle_lead_converted(self._make_event("customer"))

        # due_date key exists and is None (not a NameError)
        assert "due_date" in captured_insert
        assert captured_insert["due_date"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# _handle_revenue_recorded
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleRevenueRecorded:
    def _make_event(self, is_first=True):
        return Event(
            id="ev-2", event_type="revenue_recorded", source_agent="finance",
            payload={"is_first_revenue": is_first, "amount": 500.0},
            summary="Revenue recorded", priority="medium",
        )

    def test_first_revenue_creates_three_tax_items(self):
        agent = make_agent()
        tax_item = {"id": "tax-1", "item": "Register for Sales Tax", "category": "tax",
                    "status": "pending", "due_date": None, "description": "desc"}
        db = chainable_db([
            [],           # existing tax check → empty
            [tax_item],   # insert #1
            [tax_item],   # insert #2
            [tax_item],   # insert #3
        ])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification") as mock_notify:
            result = agent._handle_revenue_recorded(self._make_event(is_first=True))

        assert result["items_created"] == 3
        assert mock_emit.call_count == 3
        mock_notify.assert_called_once()

    def test_not_first_revenue_does_nothing(self):
        agent = make_agent()
        with patch.object(agent, "emit_event") as mock_emit:
            result = agent._handle_revenue_recorded(self._make_event(is_first=False))
        assert result["skipped"] is True
        mock_emit.assert_not_called()

    def test_existing_tax_items_skips_creation(self):
        agent = make_agent()
        db = chainable_db([[{"id": "existing-tax"}]])  # existing tax items found
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "emit_event") as mock_emit:
            result = agent._handle_revenue_recorded(self._make_event(is_first=True))
        assert result["skipped"] is True
        mock_emit.assert_not_called()

    def test_emitted_events_are_deadline_approaching(self):
        agent = make_agent()
        tax_item = {"id": "t1", "item": "Register for Sales Tax", "category": "tax",
                    "status": "pending", "due_date": None, "description": "desc"}
        db = chainable_db([[], [tax_item], [tax_item], [tax_item]])
        with patch("app.agents.legal.agent.get_client", return_value=db), \
             patch.object(agent, "emit_event") as mock_emit, \
             patch.object(agent, "send_notification"):
            agent._handle_revenue_recorded(self._make_event(is_first=True))
        for c in mock_emit.call_args_list:
            assert c.kwargs["event_type"] == "legal.deadline_approaching"


# ═══════════════════════════════════════════════════════════════════════════════
# execute() dispatch routing
# ═══════════════════════════════════════════════════════════════════════════════

class TestExecuteRouting:
    def test_scheduled_deadline_check(self):
        agent = make_agent()
        with patch.object(agent, "_run_deadline_check",
                          return_value={"status": "ok", "deadlines_found": 0}) as mock_check:
            trigger = AgentTrigger(type=TriggerType.SCHEDULED, task_name="deadline_check")
            result = agent.execute(trigger)
        mock_check.assert_called_once()
        assert result["deadlines_found"] == 0

    def test_scheduled_unknown_task_returns_skipped(self):
        agent = make_agent()
        trigger = AgentTrigger(type=TriggerType.SCHEDULED, task_name="unknown_task")
        result = agent.execute(trigger)
        assert result["status"] == "skipped"

    def test_user_request_generate_checklist(self):
        agent = make_agent()
        with patch.object(agent, "_generate_checklist",
                          return_value={"status": "ok", "items_created": 5}) as mock_gen:
            trigger = AgentTrigger(type=TriggerType.USER_REQUEST,
                                   user_input="generate_checklist",
                                   parameters={"entity_type": "C-Corp"})
            result = agent.execute(trigger)
        mock_gen.assert_called_once_with({"entity_type": "C-Corp"})

    def test_user_request_draft_document(self):
        agent = make_agent()
        with patch.object(agent, "_draft_document",
                          return_value={"status": "ok"}) as mock_draft:
            trigger = AgentTrigger(type=TriggerType.USER_REQUEST,
                                   user_input="draft_document",
                                   parameters={"checklist_item_id": "ci-1"})
            agent.execute(trigger)
        mock_draft.assert_called_once_with("ci-1", {"checklist_item_id": "ci-1"})

    def test_user_request_manual_run_calls_deadline_check(self):
        agent = make_agent()
        with patch.object(agent, "_run_deadline_check",
                          return_value={"status": "ok", "deadlines_found": 0}) as mock_check:
            trigger = AgentTrigger(type=TriggerType.USER_REQUEST, user_input="manual run")
            agent.execute(trigger)
        mock_check.assert_called_once()

    def test_approval_callback_routing(self):
        agent = make_agent()
        with patch.object(agent, "_handle_approval_callback",
                          return_value={"status": "ok"}) as mock_cb:
            trigger = AgentTrigger(
                type=TriggerType.USER_REQUEST,
                user_input="execute_approved:mark_document_final",
                parameters={"content": {"document_id": "d1"}},
            )
            agent.execute(trigger)
        mock_cb.assert_called_once()

    def test_unknown_user_input_returns_skipped(self):
        agent = make_agent()
        trigger = AgentTrigger(type=TriggerType.USER_REQUEST, user_input="do_something_unknown")
        result = agent.execute(trigger)
        assert result["status"] == "skipped"

    def test_event_trigger_lead_converted(self):
        agent = make_agent()
        with patch.object(agent, "_handle_lead_converted",
                          return_value={"status": "ok"}) as mock_handler, \
             patch.object(agent, "mark_consumed"):
            trigger = AgentTrigger(
                type=TriggerType.EVENT,
                events=[{
                    "id": "ev-1", "event_type": "lead_converted",
                    "source_agent": "outreach", "payload": {},
                    "summary": "x", "priority": "medium", "consumed_by": [],
                }],
            )
            result = agent.execute(trigger)
        mock_handler.assert_called_once()
        assert result["events_processed"] == 1

    def test_event_trigger_revenue_recorded(self):
        agent = make_agent()
        with patch.object(agent, "_handle_revenue_recorded",
                          return_value={"status": "ok"}) as mock_handler, \
             patch.object(agent, "mark_consumed"):
            trigger = AgentTrigger(
                type=TriggerType.EVENT,
                events=[{
                    "id": "ev-2", "event_type": "revenue_recorded",
                    "source_agent": "finance", "payload": {"is_first_revenue": True},
                    "summary": "x", "priority": "medium", "consumed_by": [],
                }],
            )
            agent.execute(trigger)
        mock_handler.assert_called_once()

    def test_event_dict_coerced_to_event_object(self):
        """Bug 1 fix: events arriving as dicts from Celery must become Event objects."""
        agent = make_agent()
        received_events = []

        def capture(event):
            received_events.append(event)
            return {"status": "ok"}

        with patch.object(agent, "_handle_lead_converted", side_effect=capture), \
             patch.object(agent, "mark_consumed"):
            trigger = AgentTrigger(
                type=TriggerType.EVENT,
                events=[{
                    "id": "ev-dict", "event_type": "lead_converted",
                    "source_agent": "outreach", "payload": {"conversion_type": "customer"},
                    "summary": "converted", "priority": "high", "consumed_by": [],
                }],
            )
            agent.execute(trigger)

        assert len(received_events) == 1
        # Must be an Event object, not a dict
        from app.schemas.events import Event as EventSchema
        assert isinstance(received_events[0], EventSchema)
        assert received_events[0].event_type == "lead_converted"

    def test_event_with_no_id_does_not_call_mark_consumed(self):
        """Bug 3 fix: events with id=None should not call mark_consumed."""
        agent = make_agent()
        with patch.object(agent, "_handle_lead_converted", return_value={"status": "ok"}), \
             patch.object(agent, "mark_consumed") as mock_consumed:
            trigger = AgentTrigger(
                type=TriggerType.EVENT,
                events=[{
                    "id": None,  # no id
                    "event_type": "lead_converted",
                    "source_agent": "outreach",
                    "payload": {}, "summary": "x",
                    "priority": "medium", "consumed_by": [],
                }],
            )
            agent.execute(trigger)
        mock_consumed.assert_not_called()

    def test_event_trigger_unknown_type_is_ignored(self):
        agent = make_agent()
        with patch.object(agent, "_handle_lead_converted") as mock_lc, \
             patch.object(agent, "_handle_revenue_recorded") as mock_rr, \
             patch.object(agent, "mark_consumed"):
            trigger = AgentTrigger(
                type=TriggerType.EVENT,
                events=[{
                    "id": "ev-3", "event_type": "some.unknown.event",
                    "source_agent": "other", "payload": {},
                    "summary": "x", "priority": "low", "consumed_by": [],
                }],
            )
            result = agent.execute(trigger)
        mock_lc.assert_not_called()
        mock_rr.assert_not_called()
        assert result["events_processed"] == 0  # no results added for ignored events

    def test_empty_event_list_returns_zero(self):
        agent = make_agent()
        trigger = AgentTrigger(type=TriggerType.EVENT, events=[])
        result = agent.execute(trigger)
        assert result["events_processed"] == 0
