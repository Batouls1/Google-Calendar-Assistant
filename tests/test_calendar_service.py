"""
Unit tests for app/services/calendar_service.py

These tests verify that _handle_http_error() maps HTTP status codes to the
correct typed exceptions, and that the three public functions (fetch_events,
insert_event, remove_event) propagate those exceptions correctly.

No network calls are made — get_calendar_service() is patched out entirely.
No credentials or token.json are required to run these tests.

Run with:
    pytest tests/test_calendar_service.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError

from app.services.calendar_service import (
    _handle_http_error,
    fetch_events,
    insert_event,
    remove_event,
)
from app.utils.exceptions import (
    CalendarToolError,
    EventNotFoundError,
    RateLimitError,
    AuthError,
    InvalidEventDataError,
    GoogleServerError,
)


# Helpers 

def make_http_error(status: int) -> HttpError:
    """Construct a minimal HttpError with the given HTTP status code.

    HttpError requires a response object with a .status attribute and a
    bytes content body. We use MagicMock for the response so we don't need
    a real httplib2 Response object.
    """
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"")


# Patch target: where get_calendar_service is looked up, which is the
# calendar_service module that imports it — not the oauth module itself.
PATCH_TARGET = "app.services.calendar_service.get_calendar_service"


# _handle_http_error: status code → exception mapping 
# These tests call the private function directly so we can verify the mapping
# in isolation, independent of any service mock setup.

class TestHandleHttpError:

    def test_404_raises_event_not_found(self):
        with pytest.raises(EventNotFoundError) as exc_info:
            _handle_http_error(make_http_error(404), "Test context")
        assert "Test context" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_429_raises_rate_limit(self):
        with pytest.raises(RateLimitError) as exc_info:
            _handle_http_error(make_http_error(429), "Test context")
        assert "Test context" in str(exc_info.value)
        assert "rate limit" in str(exc_info.value)

    def test_400_raises_invalid_event_data(self):
        with pytest.raises(InvalidEventDataError) as exc_info:
            _handle_http_error(make_http_error(400), "Test context")
        assert "Test context" in str(exc_info.value)
        assert "invalid" in str(exc_info.value)

    def test_401_raises_auth_error(self):
        with pytest.raises(AuthError) as exc_info:
            _handle_http_error(make_http_error(401), "Test context")
        assert "Test context" in str(exc_info.value)
        assert "permission" in str(exc_info.value)

    def test_403_raises_auth_error(self):
        with pytest.raises(AuthError) as exc_info:
            _handle_http_error(make_http_error(403), "Test context")
        assert "Test context" in str(exc_info.value)

    def test_500_raises_google_server_error(self):
        with pytest.raises(GoogleServerError) as exc_info:
            _handle_http_error(make_http_error(500), "Test context")
        assert "Test context" in str(exc_info.value)
        assert "temporarily unavailable" in str(exc_info.value)

    def test_503_raises_google_server_error(self):
        """Any 5xx should map to GoogleServerError, not just 500."""
        with pytest.raises(GoogleServerError):
            _handle_http_error(make_http_error(503), "Test context")

    def test_unknown_status_raises_base_calendar_error(self):
        """An unmapped status (e.g. 409 Conflict) falls through to CalendarToolError."""
        with pytest.raises(CalendarToolError) as exc_info:
            _handle_http_error(make_http_error(409), "Test context")
        # Must be the base type, not a subclass
        assert type(exc_info.value) is CalendarToolError

    def test_all_exceptions_are_subclass_of_calendar_tool_error(self):
        """The entire exception hierarchy must descend from CalendarToolError
        so that @handle_tool_errors can catch everything with a single base."""
        cases = [
            (404, EventNotFoundError),
            (429, RateLimitError),
            (400, InvalidEventDataError),
            (401, AuthError),
            (500, GoogleServerError),
        ]
        for status, expected_type in cases:
            with pytest.raises(CalendarToolError) as exc_info:
                _handle_http_error(make_http_error(status), "ctx")
            assert isinstance(exc_info.value, expected_type), (
                f"Status {status}: expected {expected_type.__name__}, "
                f"got {type(exc_info.value).__name__}"
            )


# fetch_events

class TestFetchEvents:

    def test_returns_event_list_on_success(self):
        """Happy path: service returns items, function returns them as-is."""
        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = {
            "items": [{"id": "abc", "summary": "Team Meeting"}]
        }
        with patch(PATCH_TARGET, return_value=mock_service):
            result = fetch_events("2026-07-01T00:00:00+03:00", "2026-07-01T23:59:59+03:00")
        assert result == [{"id": "abc", "summary": "Team Meeting"}]

    def test_returns_empty_list_when_no_items(self):
        """When the API returns no items key, we get an empty list — not a KeyError."""
        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = {}
        with patch(PATCH_TARGET, return_value=mock_service):
            result = fetch_events("2026-07-01T00:00:00+03:00", "2026-07-01T23:59:59+03:00")
        assert result == []

    def test_404_raises_event_not_found(self):
        mock_service = MagicMock()
        mock_service.events().list().execute.side_effect = make_http_error(404)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(EventNotFoundError) as exc_info:
                fetch_events("2026-07-01T00:00:00+03:00", "2026-07-01T23:59:59+03:00")
        # Context string from fetch_events' own _handle_http_error call
        assert "Fetching events failed" in str(exc_info.value)

    def test_429_raises_rate_limit(self):
        mock_service = MagicMock()
        mock_service.events().list().execute.side_effect = make_http_error(429)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(RateLimitError):
                fetch_events("2026-07-01T00:00:00+03:00", "2026-07-01T23:59:59+03:00")

    def test_401_raises_auth_error(self):
        mock_service = MagicMock()
        mock_service.events().list().execute.side_effect = make_http_error(401)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(AuthError):
                fetch_events("2026-07-01T00:00:00+03:00", "2026-07-01T23:59:59+03:00")

    def test_500_raises_google_server_error(self):
        mock_service = MagicMock()
        mock_service.events().list().execute.side_effect = make_http_error(500)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(GoogleServerError):
                fetch_events("2026-07-01T00:00:00+03:00", "2026-07-01T23:59:59+03:00")


# insert_event 

class TestInsertEvent:

    def test_returns_created_event_on_success(self):
        """Happy path: service returns the created event dict."""
        mock_service = MagicMock()
        created = {"id": "xyz123", "htmlLink": "https://calendar.google.com/event?id=xyz123"}
        mock_service.events().insert().execute.return_value = created
        with patch(PATCH_TARGET, return_value=mock_service):
            result = insert_event({"summary": "Test", "start": {}, "end": {}})
        assert result == created
        assert result["id"] == "xyz123"

    def test_400_raises_invalid_event_data(self):
        """Malformed event body → 400 → InvalidEventDataError."""
        mock_service = MagicMock()
        mock_service.events().insert().execute.side_effect = make_http_error(400)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(InvalidEventDataError) as exc_info:
                insert_event({"summary": ""})
        assert "Creating event failed" in str(exc_info.value)

    def test_403_raises_auth_error(self):
        mock_service = MagicMock()
        mock_service.events().insert().execute.side_effect = make_http_error(403)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(AuthError):
                insert_event({"summary": "Test"})

    def test_429_raises_rate_limit(self):
        mock_service = MagicMock()
        mock_service.events().insert().execute.side_effect = make_http_error(429)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(RateLimitError):
                insert_event({"summary": "Test"})

    def test_500_raises_google_server_error(self):
        mock_service = MagicMock()
        mock_service.events().insert().execute.side_effect = make_http_error(500)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(GoogleServerError):
                insert_event({"summary": "Test"})


# remove_event

class TestRemoveEvent:

    def test_returns_none_on_success(self):
        """Google's delete API returns 204 No Content — we return None."""
        mock_service = MagicMock()
        mock_service.events().delete().execute.return_value = None
        with patch(PATCH_TARGET, return_value=mock_service):
            result = remove_event("some-event-id")
        assert result is None

    def test_verifies_correct_event_id_passed_to_api(self):
        """Verify the event_id we pass actually reaches the API call."""
        mock_service = MagicMock()
        mock_service.events().delete().execute.return_value = None
        with patch(PATCH_TARGET, return_value=mock_service):
            remove_event("target-event-id")
        mock_service.events().delete.assert_called_with(
            calendarId="primary",
            eventId="target-event-id",
        )

    def test_404_raises_event_not_found(self):
        """Deleting a non-existent event → 404 → EventNotFoundError."""
        mock_service = MagicMock()
        mock_service.events().delete().execute.side_effect = make_http_error(404)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(EventNotFoundError) as exc_info:
                remove_event("nonexistent-id")
        assert "Deleting event failed" in str(exc_info.value)

    def test_403_raises_auth_error(self):
        mock_service = MagicMock()
        mock_service.events().delete().execute.side_effect = make_http_error(403)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(AuthError):
                remove_event("some-id")

    def test_429_raises_rate_limit(self):
        mock_service = MagicMock()
        mock_service.events().delete().execute.side_effect = make_http_error(429)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(RateLimitError):
                remove_event("some-id")

    def test_500_raises_google_server_error(self):
        mock_service = MagicMock()
        mock_service.events().delete().execute.side_effect = make_http_error(500)
        with patch(PATCH_TARGET, return_value=mock_service):
            with pytest.raises(GoogleServerError):
                remove_event("some-id")