"""
Utilities for extracting structured data from LangGraph agent result messages.

Lives in app/agent/ because it operates on the raw message objects that
LangGraph produces. Imported by server.py (live turns + history replay)
and cards.py (deleted-event title lookup across history).
"""

from typing import Optional


def _tool_message_to_dict(msg) -> dict:
    """Convert a single ToolMessage into the {'name', 'content'} shape
    build_card() expects. Shared by get_tool_outputs() and turn_tool_outputs()
    so both code paths parse tool content identically."""
    content = getattr(msg, "content", "")
    name = getattr(msg, "name", "") or ""
    if isinstance(content, list):
        text = " ".join(
            part["text"] if isinstance(part, dict) and "text" in part else str(part)
            for part in content
        )
    else:
        text = str(content)
    return {"name": name, "content": text}


def get_tool_outputs(result: dict, current_turn_only: bool = True) -> list[dict]:
    """Extract tool outputs from a LangGraph agent result.
 
    Args:
        result:            The dict returned by agent.invoke() (or state.values
                           from agent.get_state()).
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
 
    return [_tool_message_to_dict(m) for m in messages if getattr(m, "type", None) == "tool"]
 
 
def split_into_turns(messages: list) -> list[dict]:
    """Group a full message list into per-turn chunks for history replay.
 
    Each turn = one human message plus everything the agent did in response
    (tool calls, tool outputs, final text) up to the next human message.
    Used to reconstruct cards for old sessions loaded from the sidebar,
    reusing the same build_card() logic that live turns use — see
    server.py's get_session_messages().
 
    Returns:
        List of {'human': HumanMessage, 'rest': [messages after it, before
        the next human message]}.
    """
    turns = []
    current: Optional[dict] = None
 
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type == "human":
            if current is not None:
                turns.append(current)
            current = {"human": msg, "rest": []}
        elif current is not None:
            current["rest"].append(msg)
 
    if current is not None:
        turns.append(current)
 
    return turns
 
 
def turn_tool_outputs(turn: dict) -> list[dict]:
    """Extract tool outputs from a single turn produced by split_into_turns()."""
    return [_tool_message_to_dict(m) for m in turn["rest"] if getattr(m, "type", None) == "tool"]
 
 
def turn_final_ai_text(turn: dict) -> str:
    """Return the last non-empty AI message text in a turn, or '' if none.
 
    A turn can contain multiple AI messages when the agent makes several
    tool calls in sequence (e.g. get_events, then create_event) — each
    intermediate AI message has empty content (it's just a tool-call
    instruction). Only the final one carries the actual response text.
    """
    text = ""
    for m in turn["rest"]:
        if getattr(m, "type", None) == "ai" and getattr(m, "content", ""):
            text = m.content
    return text