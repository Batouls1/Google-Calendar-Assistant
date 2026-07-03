"""
Unit tests for app/cards.py

build_card() is a pure function — same inputs always produce the same
output, no I/O, no side effects — so these tests construct realistic tool
output strings (matching the exact formats returned by create_event.py,
delete_event.py, get_events.py, and find_free_slots.py) and assert on the
resulting card dict.

No network calls, no credentials, no agent invocation required.

Run with:
    pytest tests/test_cards.py -v
"""

import pytest
from app.cards import (
    build_card,
    _parse_field,
    _prettify_event_header,
    find_event_title_from_history,
)


# _parse_field 

class TestParseField:

    def test_extracts_matched_group(self):
        result = _parse_field(r"•\s*Title:\s*(.+)", "• Title: Team Meeting")
        assert result == "Team Meeting"

    def test_strips_whitespace(self):
        result = _parse_field(r"•\s*Title:\s*(.+)", "•   Title:   Team Meeting   ")
        assert result == "Team Meeting"

    def test_returns_empty_string_when_no_match(self):
        result = _parse_field(r"•\s*Title:\s*(.+)", "no title field here")
        assert result == ""


# _prettify_event_header 

class TestPrettifyEventHeader:

    def test_iso_same_day(self):
        result = _prettify_event_header("Events from 2026-07-03 to 2026-07-03")
        assert result == "Events on Friday, Jul 03, 2026"

    def test_iso_different_days(self):
        result = _prettify_event_header("Events from 2026-07-01 to 2026-07-05")
        assert result == "Events Jul 01 – Jul 05, 2026"

    def test_natural_language_same_day(self):
        result = _prettify_event_header("Events from tomorrow to tomorrow")
        assert result == "Events on Tomorrow"

    def test_natural_language_different_days(self):
        result = _prettify_event_header("Events from today to this saturday")
        assert result == "Events Today – This saturday"

    def test_unmatched_header_returned_unchanged(self):
        header = "Something entirely unexpected"
        assert _prettify_event_header(header) == header


# find_event_title_from_history 

class TestFindEventTitleFromHistory:

    def test_finds_title_by_event_id_in_history(self):
        result = {
            "messages": [
                _fake_message("human", "What events do I have today"),
                _fake_message(
                    "tool",
                    "Events from today to today:\n\n"
                    "• Team Sync | 2026-07-03T10:00:00+03:00 → 2026-07-03T11:00:00+03:00 | ID: abc123",
                    name="get_events",
                ),
            ]
        }
        title = find_event_title_from_history("abc123", result)
        assert title == "Team Sync"

    def test_returns_none_when_id_not_found(self):
        result = {
            "messages": [
                _fake_message(
                    "tool",
                    "Events from today to today:\n\n"
                    "• Team Sync | 2026-07-03T10:00:00+03:00 → 2026-07-03T11:00:00+03:00 | ID: abc123",
                    name="get_events",
                ),
            ]
        }
        title = find_event_title_from_history("nonexistent-id", result)
        assert title is None

    def test_returns_none_when_no_get_events_output_in_history(self):
        result = {"messages": [_fake_message("human", "hello")]}
        title = find_event_title_from_history("abc123", result)
        assert title is None


# build_card: no tool outputs 

class TestBuildCardNoToolOutputs:

    def test_returns_none_when_tool_outputs_empty(self):
        card = build_card([], "Just a conversational reply.", "hello", {"messages": []})
        assert card is None


# build_card: event_created 

class TestBuildCardEventCreated:

    def test_builds_full_card(self):
        tool_outputs = [{
            "name": "create_event",
            "content": (
                "Event created successfully!\n"
                "• Title: Team Meeting\n"
                "• Start: 2026-07-06T15:00:00+03:00\n"
                "• End: 2026-07-06T16:00:00+03:00\n"
                "• Event ID: abc123xyz\n"
                "• Link: https://www.google.com/calendar/event?eid=abc123"
            ),
        }]
        card = build_card(tool_outputs, "Your meeting is scheduled.", "schedule a meeting", {"messages": []})

        assert card["type"] == "event_created"
        assert card["title"] == "Team Meeting"
        assert card["start"] == "2026-07-06T15:00:00+03:00"
        assert card["end"] == "2026-07-06T16:00:00+03:00"
        assert card["event_id"] == "abc123xyz"
        assert card["link"] == "https://www.google.com/calendar/event?eid=abc123"

    def test_takes_priority_over_other_tool_outputs_in_same_turn(self):
        """When get_events (conflict check) runs before create_event succeeds,
        the created card should win — this is the real get_events + create_event
        flow every scheduling request goes through."""
        tool_outputs = [
            {"name": "get_events", "content": "Events from today to today:\n\n• Lunch | 12:00 PM → 1:00 PM"},
            {
                "name": "create_event",
                "content": (
                    "Event created successfully!\n"
                    "• Title: Gym\n"
                    "• Start: 2026-07-06T15:00:00+03:00\n"
                    "• End: 2026-07-06T16:00:00+03:00\n"
                    "• Event ID: gym123\n"
                    "• Link: https://calendar.google.com/gym123"
                ),
            },
        ]
        card = build_card(tool_outputs, "Your Gym session is scheduled.", "schedule gym", {"messages": []})
        assert card["type"] == "event_created"
        assert card["title"] == "Gym"


# build_card: event_deleted 

class TestBuildCardEventDeleted:

    def test_resolves_title_from_current_turn_get_events(self):
        """Standard delete-by-ID flow: get_events ran first (to confirm the
        event), then delete_event ran, both in the same turn."""
        tool_outputs = [
            {
                "name": "get_events",
                "content": (
                    "Events from tomorrow to tomorrow:\n\n"
                    "• Doctor Appointment | 2026-07-03T10:30:00+03:00 → 2026-07-03T11:00:00+03:00 | ID: doc456"
                ),
            },
            {"name": "delete_event", "content": "Event with ID 'doc456' was successfully deleted."},
        ]
        card = build_card(tool_outputs, "Deleted.", "delete the doctor appointment", {"messages": []})
        assert card == {"type": "event_deleted", "title": "Doctor Appointment"}

    def test_resolves_title_from_full_history_when_not_in_current_turn(self):
        """If the current turn only has the delete_event output (e.g. the ID
        was already known from an earlier turn), fall back to searching all
        history for a matching get_events output."""
        tool_outputs = [
            {"name": "delete_event", "content": "Event with ID 'hist789' was successfully deleted."},
        ]
        result = {
            "messages": [
                _fake_message(
                    "tool",
                    "Events from today to today:\n\n"
                    "• Old Meeting | 2026-07-02T09:00:00+03:00 → 2026-07-02T10:00:00+03:00 | ID: hist789",
                    name="get_events",
                ),
            ]
        }
        card = build_card(tool_outputs, "Deleted.", "delete it", result)
        assert card == {"type": "event_deleted", "title": "Old Meeting"}

    def test_resolves_title_via_direct_title_date_deletion(self):
        """delete_event's path-2 format (delete by title+date, no ID lookup)."""
        tool_outputs = [
            {"name": "delete_event", "content": "Event 'Team Sync' on this friday was successfully deleted."},
        ]
        card = build_card(tool_outputs, "Deleted.", "delete team sync", {"messages": []})
        assert card == {"type": "event_deleted", "title": "Team Sync"}

    def test_resolves_title_from_agent_response_as_last_resort(self):
        """When no get_events output exists anywhere, fall back to parsing
        the agent's own confirmation sentence. The regex expects a
        markdown-bold title (**Title**), matching GPT-4o's typical emphasis
        style — the same style renderMarkdown() on the frontend renders."""
        tool_outputs = [
            {"name": "delete_event", "content": "Event with ID 'unknown999' was successfully deleted."},
        ]
        agent_response = "The **Team Meeting** event has been deleted."
        card = build_card(tool_outputs, agent_response, "delete it", {"messages": []})
        assert card == {"type": "event_deleted", "title": "Team Meeting"}

    def test_falls_back_to_generic_label_when_title_unresolvable(self):
        """Absolute last resort: no get_events match anywhere, no parseable
        agent sentence — still returns a valid card, never crashes."""
        tool_outputs = [
            {"name": "delete_event", "content": "Event with ID 'mystery000' was successfully deleted."},
        ]
        card = build_card(tool_outputs, "It's gone now.", "delete it", {"messages": []})
        assert card == {"type": "event_deleted", "title": "Event"}


# build_card: free_slots / no_free_slots 

class TestBuildCardFreeSlots:

    def test_parses_multiple_slots(self):
        tool_outputs = [{
            "name": "find_free_slots",
            "content": (
                "Free slots on this monday (min 60 min):\n\n"
                "• 09:00 AM → 12:00 PM (180 min)\n"
                "• 01:00 PM → 02:00 PM (60 min)\n"
                "• 03:00 PM → 08:00 PM (300 min)"
            ),
        }]
        card = build_card(tool_outputs, "Here are your free slots.", "find free slots monday", {"messages": []})

        assert card["type"] == "free_slots"
        assert card["header"] == "Free slots on this monday (min 60 min)"
        assert len(card["slots"]) == 3
        assert card["slots"][0] == {"start": "09:00 AM", "end": "12:00 PM", "duration": 180}
        assert card["slots"][1] == {"start": "01:00 PM", "end": "02:00 PM", "duration": 60}

    def test_no_free_slots_card(self):
        tool_outputs = [{
            "name": "find_free_slots",
            "content": "No free slots of 30+ minutes found on tomorrow.",
        }]
        card = build_card(tool_outputs, "No availability.", "find free slots tomorrow", {"messages": []})
        assert card == {
            "type": "no_free_slots",
            "message": "No free slots of 30+ minutes found on tomorrow.",
        }

    def test_all_day_event_blocks_day_returns_no_free_slots_message(self):
        """find_free_slots' all-day-event branch doesn't contain 'No free slots'
        literally but does describe zero availability — this is a known gap:
        it currently falls through and produces no card at all, matching
        actual observed behavior rather than an idealized spec."""
        tool_outputs = [{
            "name": "find_free_slots",
            "content": "You have an all-day event on tomorrow ('Out of Office'), so the day is considered fully booked. No free slots available.",
        }]
        card = build_card(tool_outputs, "You're fully booked.", "find free slots tomorrow", {"messages": []})
        # Contains "No free slots" substring, so it correctly routes to the slots branch.
        assert card["type"] == "no_free_slots"


# build_card: event_list 

class TestBuildCardEventList:

    def test_builds_event_list_card(self):
        tool_outputs = [{
            "name": "get_events",
            "content": (
                "Events from today to today:\n\n"
                "• Lunch break | 2026-07-02T14:00:00+03:00 → 2026-07-02T15:00:00+03:00 | ID: lunch1\n"
                "• Meeting | 2026-07-02T16:00:00+03:00 → 2026-07-02T17:00:00+03:00 | 📍 Room 12 | ID: meet2"
            ),
        }]
        card = build_card(tool_outputs, "Here are your events for today.", "what events do I have today", {"messages": []})

        assert card["type"] == "event_list"
        assert len(card["events"]) == 2
        assert card["events"][0]["title"] == "Lunch break"
        assert card["events"][0]["event_id"] == "lunch1"
        assert card["events"][1]["location"] == "Room 12"
        assert card["events"][1]["event_id"] == "meet2"

    def test_suppressed_when_user_message_signals_delete_intent(self):
        """get_events runs first to locate the event before deletion — the
        list must not flash as a card mid-flow."""
        tool_outputs = [{
            "name": "get_events",
            "content": "Events from tomorrow to tomorrow:\n\n• Meeting | 2:00 PM → 3:00 PM | ID: m1",
        }]
        card = build_card(tool_outputs, "Would you like me to delete this?", "delete the meeting tomorrow", {"messages": []})
        assert card is None

    def test_suppressed_when_agent_response_signals_conflict(self):
        tool_outputs = [{
            "name": "get_events",
            "content": "Events from today to today:\n\n• Lunch | 12:00 PM → 1:00 PM | ID: l1",
        }]
        card = build_card(
            tool_outputs,
            "You already have a Lunch event then — would you like to proceed anyway?",
            "schedule something at noon",
            {"messages": []},
        )
        assert card is None

    def test_suppressed_when_other_tools_ran_in_same_turn(self):
        """Real observed case: get_events (conflict check) + create_event that
        failed (e.g. past-time rejection) — no card should render, since
        only_get_events is False and create_event didn't succeed either."""
        tool_outputs = [
            {"name": "get_events", "content": "Events from today to today:\n\n• Lunch | 12:00 PM → 1:00 PM | ID: l1"},
            {"name": "create_event", "content": "Could not complete the request: Cannot create an event in the past."},
        ]
        card = build_card(
            tool_outputs,
            "It seems I can't schedule an event in the past.",
            "schedule gym at 2pm",
            {"messages": []},
        )
        assert card is None

    def test_returns_none_when_no_events_found(self):
        tool_outputs = [{
            "name": "get_events",
            "content": "No events found between today and today.",
        }]
        card = build_card(tool_outputs, "You have no events today.", "what events do I have", {"messages": []})
        assert card is None


# Test helper 

def _fake_message(msg_type: str, content: str, name: str = ""):
    """Minimal stand-in for a LangChain BaseMessage, exposing only the
    attributes get_tool_outputs() and build_card() actually read
    (.type, .content, .name) via getattr — avoids depending on real
    LangChain message classes in these unit tests."""
    class _FakeMessage:
        pass
    msg = _FakeMessage()
    msg.type = msg_type
    msg.content = content
    msg.name = name
    return msg