from app.services.calendar_service import insert_event
from app.utils.datetime_utils import parse_datetime, to_rfc3339
from app.utils.logger import get_logger
from app.utils.exceptions import CalendarToolError

logger = get_logger(__name__)


def create_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    location: str = ""
) -> str:
    """
    Create a new event on the user's Google Calendar.

    Use this tool when the user wants to schedule, add, or create a new event,
    meeting, appointment, reminder, or any calendar entry.

    Args:
        title:          The name or title of the event (e.g. 'Team Meeting').
        start_datetime: When the event starts. Accepts natural language like
                        'tomorrow at 3pm', 'this friday at 10:00', or explicit
                        strings like '2026-06-15T15:00:00'.
        end_datetime:   When the event ends. Same format as start_datetime.
                        If the user doesn't specify, default to 1 hour after start.
        description:    Optional notes or details about the event.
        location:       Optional location or meeting link for the event.

    Returns:
        A confirmation string with the event title, time, and a link to view it.
    """
    logger.info(f"Creating event: '{title}' from {start_datetime} to {end_datetime}")
    try:
        start_dt = parse_datetime(start_datetime)
        end_dt = parse_datetime(end_datetime)

        if end_dt <= start_dt:
            raise CalendarToolError("End time must be after start time.")

        event_body = {
            "summary": title,
            "start": {
                "dateTime": to_rfc3339(start_dt),
                "timeZone": "Asia/Beirut",
            },
            "end": {
                "dateTime": to_rfc3339(end_dt),
                "timeZone": "Asia/Beirut",
            },
        }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        created = insert_event(event_body)
        event_link = created.get("htmlLink", "no link available")

        logger.info(f"Event created successfully: {event_link}")
        return (
            f"Event created successfully!\n"
            f"• Title: {title}\n"
            f"• Start: {to_rfc3339(start_dt)}\n"
            f"• End: {to_rfc3339(end_dt)}\n"
            f"• Link: {event_link}"
        )

    except CalendarToolError:
        raise
    except Exception as e:
        logger.error(f"create_event failed: {e}")
        raise CalendarToolError(f"Error creating event: {str(e)}")