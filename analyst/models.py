"""Model configuration — GPT-5 family, right model per task."""
from __future__ import annotations

# Task → model mapping
# The idea: expensive reasoning where it matters, cheap and fast everywhere else.

MODELS = {
    # The hard task: interpret numbers, write like a plant engineer, domain insight
    # This is where quality matters most — it's the customer-facing output
    "narrative": "gpt-5.4",

    # Structured research: take search results + failure data, suggest root causes
    # Needs domain knowledge but the task is well-structured with clear format
    "research": "gpt-5.4",

    # Data classification: is this equipment or operational? what theme?
    # Simple extraction, well-defined categories — cheapest model handles it
    "classify": "gpt-5-nano",
}

# Reasoning effort per task (for models that support it: gpt-5, 5-mini, 5-nano)
# gpt-5.4 handles its own reasoning internally
REASONING_EFFORT = {
    "narrative": None,       # gpt-5.4 doesn't use reasoning_effort param
    "research": None,        # gpt-5.4 doesn't use reasoning_effort param
    "classify": "minimal",   # simple classification, don't overthink
}


def get_model(task: str) -> str:
    """Get the model ID for a given task."""
    return MODELS.get(task, "gpt-5-mini")


def get_reasoning_effort(task: str) -> str | None:
    """Get reasoning effort for a task (None = don't send the param)."""
    return REASONING_EFFORT.get(task)
