"""
Utilities for extracting structured data from LangGraph agent result messages.

Lives in app/agent/ because it operates on the raw message objects that
LangGraph produces. Imported by both server.py (for logging) and cards.py
(for card building and history search), avoiding a circular dependency.
"""

from typing import Optional


def get_tool_outputs(result: dict, current_turn_only: bool = True) -> list[dict]:
    """Extract tool outputs from a LangGraph agent result.

    Args:
        result:            The dict returned by agent.invoke().
        current_turn_only: If True, only return tool outputs from after the
                           last human message (i.e. the current turn).
                           If False, return all tool outputs in history —
                           used when searching for a deleted event's title
                           across previous turns.

    Returns:
        List of dicts with keys 'name' (tool name) and 'content' (output text).
    """
    messages = result.get("messages", [])

    if current_turn_only:
        last_human_idx = 0
        for i, msg in enumerate(messages):
            if getattr(msg, "type", None) == "human":
                last_human_idx = i
        messages = messages[last_human_idx + 1:]

    outputs = []
    for msg in messages:
        if getattr(msg, "type", None) == "tool":
            content = getattr(msg, "content", "")
            name = getattr(msg, "name", "") or ""
            if isinstance(content, list):
                text = " ".join(
                    part["text"] if isinstance(part, dict) and "text" in part else str(part)
                    for part in content
                )
            else:
                text = str(content)
            outputs.append({"name": name, "content": text})
    return outputs