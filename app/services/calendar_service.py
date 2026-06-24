from googleapiclient.errors import HttpError
from app.auth.oauth import get_calendar_service
from app.utils.exceptions import (
    CalendarToolError,
    EventNotFoundError,
    RateLimitError,
    AuthError,
    InvalidEventDataError,
    GoogleServerError,
)


def _handle_http_error(e: HttpError, context: str):
    status = e.resp.status

    if status == 404:
        raise EventNotFoundError(f"{context}: the event was not found.")
    elif status == 429:
        raise RateLimitError(f"{context}: rate limit reached — please try again in a moment.")
    elif status == 400:
        raise InvalidEventDataError(f"{context}: invalid request data — {e}")
    elif status in (401, 403):                                         
        raise AuthError(f"{context}: authentication or permission denied.")
    elif status >= 500:
        raise GoogleServerError(f"{context}: Google Calendar is temporarily unavailable.")
    else:
        raise CalendarToolError(f"{context}: {e}")


def fetch_events(start_iso: str, end_iso: str) -> list[dict]:
    service = get_calendar_service()
    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        return result.get("items", [])
    except HttpError as e:
        _handle_http_error(e, "Fetching events failed")


def insert_event(event_body: dict) -> dict:
    service = get_calendar_service()
    try:
        return service.events().insert(
            calendarId="primary",
            body=event_body
        ).execute()
    except HttpError as e:
        _handle_http_error(e, "Creating event failed")


def remove_event(event_id: str) -> None:
    service = get_calendar_service()
    try:
        service.events().delete(
            calendarId="primary",
            eventId=event_id
        ).execute()
    except HttpError as e:
        _handle_http_error(e, "Deleting event failed")