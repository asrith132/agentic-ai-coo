"""
Static copy and rules for unauthenticated (guest) PM interactions.

Authenticated flows should load user / org context from Supabase instead.
"""

PUBLIC_PM_CONTEXT = {
    "assistant_name": "PM Agent",
    "product_description": "A planning agent that turns startup goals into executable tasks.",
    "guest_mode_rules": [
        "Can explain what PM Agent does",
        "Can answer basic questions",
        "Cannot create or save plans before login",
        "Must ask the user to log in before using private context"
    ],
    "starter_prompts": [
        "Help me launch my paid tier",
        "Plan my next 2 weeks",
        "Break down my startup goals into tasks"
    ],
}