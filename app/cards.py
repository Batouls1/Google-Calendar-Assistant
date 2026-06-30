"""
Card builder for the Calendar Assistant frontend.

Inspects tool outputs from the current agent turn and constructs a typed
card dict that the frontend renders as a structured UI component. Returns
None when no structured card applies — the frontend then falls back to
rendering the agent's plain text response.

Design note: card selection relies on heuristic intent detection (keyword
matching + tool name checks) rather than structured LLM output. This is a
deliberate tradeoff — a second LLM call for classification would add latency
and cost. A production implementation would use structured outputs or a
dedicated classification layer. 
"""

import re
from typing import Optional
from app.agent.message_utils import get_tool_outputs


# Intent keyword lists 

# If the user message contains any of these, suppress the event list card
# even when get_events was the only tool called (deletion flow calls
# get_events first, and we don't want to flash a list card mid-flow).
DELETE_INTENT_KEYWORDS = [
    "delete", "remove", "cancel", "erase",
    "get rid of", "clear", "drop",
]

# If the agent response contains any of these, it's mid-flow asking for
# confirmation or clarification — suppress the event list card.
CONFLICT_KEYWORDS = [
    "would you like to proceed", "do you want to proceed",
    "already have", "conflict", "overlap",
    "shall i schedule", "would you like me to schedule",
    "different time", "another time", "which event",
    "which one", "would you like to delete", "want to delete",
    "please specify", "shall i delete", "do you want me to delete",
]


# Helpers 

def _parse_field(pattern: str, text: str) -> str:
    """Extract the first capture group from text, or return empty string."""
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def _prettify_event_header(header: str) -> str:
    """Convert raw tool output headers into human-readable date labels."""
    # Case 1: ISO dates — "Events from 2026-06-29 to 2026-06-29"
    m = re.search(r"Events from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", header)
    if m:
        try:
            from datetime import date
            d1 = date.fromisoformat(m.group(1))
            d2 = date.fromisoformat(m.group(2))
            if d1 == d2:
                return f"Events on {d1.strftime('%A, %b %d, %Y')}"
            return f"Events {d1.strftime('%b %d')} – {d2.strftime('%b %d, %Y')}"
        except Exception:
            return header

    # Case 2: natural language — "Events from tomorrow to tomorrow"
    m2 = re.search(r"Events from (.+?) to (.+?)$", header, re.IGNORECASE)
    if m2:
        start, end = m2.group(1).strip(), m2.group(2).strip()
        if start.lower() == end.lower():
            return f"Events on {start.capitalize()}"
        return f"Events {start.capitalize()} – {end.capitalize()}"

    return header


def find_event_title_from_history(deleted_id: str, result: dict) -> Optional[str]:
    """Search all get_events outputs in the full message history for a deleted event ID.

    Used as a fallback when the current turn didn't include a get_events call
    but we still want to show the event title in the deletion card.
    """
    all_outputs = get_tool_outputs(result, current_turn_only=False)
    for t in all_outputs:
        if not t["content"].startswith("Events from"):
            continue
        for line in t["content"].splitlines():
            if line.startswith("•") and deleted_id in line:
                return line.lstrip("• ").split("|")[0].strip()
    return None


# Card builder

def build_card(
    tool_outputs: list[dict],
    agent_response: str,
    user_message: str,
    result: dict,
) -> Optional[dict]:
    """Build a typed card dict from tool outputs, or return None for plain text."""
    if not tool_outputs:
        return None

    tool_names = [t["name"] for t in tool_outputs]
    response_lower = agent_response.lower()
    user_lower = user_message.lower()

    # Event created 
    create_output = next(
        (t["content"] for t in tool_outputs if "Event created successfully" in t["content"]),
        None
    )
    if create_output:
        return {
            "type":     "event_created",
            "title":    _parse_field(r"•\s*Title:\s*(.+)",          create_output),
            "start":    _parse_field(r"•\s*Start:\s*(.+)",          create_output),
            "end":      _parse_field(r"•\s*End:\s*(.+)",            create_output),
            "event_id": _parse_field(r"•\s*Event ID:\s*(\S+)",      create_output),
            "link":     _parse_field(r"•\s*Link:\s*(https?://\S+)", create_output),
        }

    # Event deleted 
    delete_output = next(
        (t["content"] for t in tool_outputs if "successfully deleted" in t["content"]),
        None
    )
    if delete_output:
        title = None

        deleted_id = _parse_field(r"ID '(.+?)' was successfully deleted", delete_output)
        if deleted_id:
            # Search current turn first
            events_this_turn = next(
                (t["content"] for t in tool_outputs
                 if t["content"].startswith("Events from") and "•" in t["content"]),
                None
            )
            if events_this_turn:
                for line in events_this_turn.splitlines():
                    if line.startswith("•") and deleted_id in line:
                        title = line.lstrip("• ").split("|")[0].strip()
                        break
            if not title:
                title = find_event_title_from_history(deleted_id, result)

        if not title:
            m = re.search(r"Event '(.+?)' on .+? was successfully deleted", delete_output)
            if m:
                title = m.group(1)

        if not title:
            m2 = re.search(
                r'\*{0,2}([^*\n]+?)\*{0,2}\s+event\s+(?:has been|was)\s+(?:successfully\s+)?deleted',
                agent_response, re.IGNORECASE
            )
            if m2:
                title = m2.group(1).strip()

        return {"type": "event_deleted", "title": title or "Event"}

    # Free slots
    slots_output = next(
        (t["content"] for t in tool_outputs
         if "Free slots on" in t["content"] or "No free slots" in t["content"]),
        None
    )
    if slots_output:
        if "No free slots" in slots_output:
            return {"type": "no_free_slots", "message": slots_output.strip()}
        slots = []
        for line in slots_output.splitlines():
            m = re.match(r"[•\-]\s*(.+?)\s*→\s*(.+?)\s*\((\d+)\s*min\)", line)
            if m:
                slots.append({
                    "start":    m.group(1).strip(),
                    "end":      m.group(2).strip(),
                    "duration": int(m.group(3)),
                })
        if slots:
            header = slots_output.splitlines()[0].rstrip(":")
            return {"type": "free_slots", "header": header, "slots": slots}

    # Event list
    # Show only when get_events is the sole tool this turn AND:
    # - User didn't ask to delete something (delete intent)
    # - Agent isn't reporting a conflict or asking for confirmation
    only_get_events = all(name == "get_events" for name in tool_names)
    user_wants_delete = any(kw in user_lower for kw in DELETE_INTENT_KEYWORDS)
    agent_is_intermediate = any(kw in response_lower for kw in CONFLICT_KEYWORDS)

    if only_get_events and not user_wants_delete and not agent_is_intermediate:
        list_output = next(
            (t["content"] for t in tool_outputs
             if t["content"].startswith("Events from") and "•" in t["content"]),
            None
        )
        if list_output:
            events = []
            for line in list_output.splitlines():
                if not line.startswith("•"):
                    continue
                parts    = [p.strip() for p in line.lstrip("• ").split("|")]
                title    = parts[0] if parts else "Untitled"
                tr       = parts[1] if len(parts) > 1 else ""
                location = next((p[2:].strip() for p in parts[2:] if p.startswith("📍")), "")
                eid      = next((p[3:].strip() for p in parts[2:] if p.startswith("ID:")), "")
                s, _, e  = tr.partition("→")
                events.append({
                    "title":    title,
                    "start":    s.strip(),
                    "end":      e.strip(),
                    "location": location,
                    "event_id": eid,
                })
            if events:
                raw_header = list_output.splitlines()[0].rstrip(":")
                header = _prettify_event_header(raw_header)
                return {"type": "event_list", "header": header, "events": events}

    return None