"""
agents/pm/registry.py — Agent capability manifest

The PM agent reads this when creating or assigning tasks so it can:
  1. Pick the right assigned_agent for a task
  2. Communicate what each agent needs to run
  3. Understand each agent's limitations

Each entry maps agent_id → metadata the PM can reason about.
"""

from __future__ import annotations

AGENT_REGISTRY: dict[str, dict] = {
    "finance": {
        "display_name": "Finance Agent",
        "capabilities": [
            "Analyze uploaded bank/Stripe CSV transactions",
            "Calculate monthly burn rate, revenue, and net",
            "Compute runway in months from current cash balance",
            "Detect spending anomalies and unusual category spikes",
            "Generate plain-English financial health summaries",
            "Compare month-over-month trends across snapshots",
        ],
        "required_inputs": [
            "A CSV export has already been uploaded (or will be uploaded)",
            "Optionally: current_balance to calculate runway",
        ],
        "limitations": [
            "Cannot execute transactions or move money",
            "Cannot access bank accounts directly — relies on CSV uploads",
            "Cannot forecast beyond available historical data",
        ],
        "task_types": [
            "Analyze financial data",
            "Calculate runway",
            "Investigate spending",
            "Generate financial report",
            "Detect anomalies",
        ],
    },

    "dev_activity": {
        "display_name": "Dev Activity Agent",
        "capabilities": [
            "Process and summarize GitHub push and PR events",
            "Extract features shipped from commit messages",
            "Maintain a feature map of shipped vs in-progress work",
            "Track engineering velocity across branches",
            "Classify commits by type (feat, fix, refactor, chore)",
        ],
        "required_inputs": [
            "GitHub webhook events (push or pull_request merged)",
            "Or: manual commit data passed via trigger parameters",
        ],
        "limitations": [
            "Cannot write or modify code",
            "Cannot access private repos without a configured webhook",
            "Read-only analysis only — no deployment or CI actions",
        ],
        "task_types": [
            "Analyze recent commits",
            "Update feature map",
            "Summarize engineering velocity",
            "Track what shipped",
        ],
    },

    "outreach": {
        "display_name": "Outreach Agent",
        "capabilities": [
            "Research a specific contact (name + company) and build a profile",
            "Draft personalized cold, follow-up, investor, or partnership emails",
            "Discover high-fit contacts autonomously given a focus area or ICP",
            "Maintain the contact pipeline with statuses (cold, contacted, replied, closed)",
            "Send approved messages via configured email integration",
        ],
        "required_inputs": [
            "For research: contact name and company name",
            "For drafting: contact_id and email type",
            "For discovery: optional focus area (e.g. 'B2B SaaS CTOs in fintech')",
        ],
        "limitations": [
            "Cannot send emails without user approval",
            "Web research depends on public information only",
            "Cannot access LinkedIn or other gated platforms directly",
        ],
        "task_types": [
            "Research a contact",
            "Draft outreach email",
            "Discover new prospects",
            "Follow up with contacts",
            "Build prospect list",
        ],
    },

    "legal": {
        "display_name": "Legal Agent",
        "capabilities": [
            "Generate a tailored compliance checklist for a given entity type, jurisdiction, and stage",
            "Draft legal documents (Privacy Policy, Terms of Service, NDA, etc.)",
            "Track compliance deadlines and surface upcoming due dates",
            "Flag overdue compliance items",
        ],
        "required_inputs": [
            "For checklist generation: entity_type, jurisdiction, stage, product_type",
            "For document drafting: checklist_item_id (from existing checklist)",
            "Company name and product description (from global context)",
        ],
        "limitations": [
            "Not a substitute for qualified legal counsel — all output is a first draft",
            "Cannot file documents with government agencies",
            "Cannot enforce agreements or represent the company legally",
        ],
        "task_types": [
            "Generate compliance checklist",
            "Draft legal document",
            "Review compliance deadlines",
            "Create privacy policy",
            "Create terms of service",
        ],
    },

    "marketing": {
        "display_name": "Marketing Agent",
        "capabilities": [
            "Generate blog posts, social media content, and ad copy",
            "Analyze market trends and competitor positioning",
            "Create campaign briefs and content calendars",
            "Write product launch announcements",
            "Generate SEO-optimized content based on target keywords",
        ],
        "required_inputs": [
            "Target audience / ICP persona (from global context)",
            "Product name and description (from global context)",
            "Optional: topic, keywords, tone, platform target",
        ],
        "limitations": [
            "Cannot publish content directly to external platforms",
            "All content requires human review before use",
            "Cannot run paid advertising campaigns",
        ],
        "task_types": [
            "Write blog post",
            "Create social media content",
            "Write ad copy",
            "Draft launch announcement",
            "Analyze market trends",
            "Generate campaign brief",
        ],
    },

    "pm": {
        "display_name": "PM Agent",
        "capabilities": [
            "Reprioritize the entire task backlog based on business context",
            "Create meta tasks (planning, process improvement)",
            "Update milestone progress",
            "Generate weekly roadmap summaries",
        ],
        "required_inputs": [
            "Access to the current task backlog (automatic)",
        ],
        "limitations": [
            "Cannot directly execute tasks assigned to other agents",
            "Cannot make product decisions — surfaces options for human review",
        ],
        "task_types": [
            "Reprioritize backlog",
            "Create milestone",
            "Generate roadmap summary",
            "Plan sprint",
        ],
    },
}


def registry_summary_for_llm() -> str:
    """Return a compact text block describing all agents for LLM prompts."""
    lines = ["AVAILABLE AGENTS (assign tasks to these agent IDs):"]
    for agent_id, info in AGENT_REGISTRY.items():
        lines.append(f"\n[{agent_id}] {info['display_name']}")
        lines.append("  Can do: " + " | ".join(info["capabilities"][:3]))
        lines.append("  Task types: " + ", ".join(info["task_types"][:4]))
        lines.append("  Needs: " + "; ".join(info["required_inputs"][:2]))
        lines.append("  Cannot: " + info["limitations"][0])
    return "\n".join(lines)
