from app.services.calendar_service import fetch_events
from app.utils.datetime_utils import parse_datetime, to_rfc3339, start_of_day, end_of_day, now_beirut
from app.utils.logger import get_logger
from app.utils.exceptions import CalendarToolError

logger = get_logger(__name__)

def get_events(start_date: str, end_date: str) -> str:
    """
    Retrieve all calendar events between two dates.

    Use this tool when the user wants to view, check, or list their upcoming
    events or schedule. Also use it when the user asks what they have planned,
    what's on their calendar, or anything about existing events in a date range.

    Args:
        start_date: The start of the date range. Accepts natural language like
                    'today', 'tomorrow', 'this monday', 'next friday', or
                    explicit dates like '2026-06-10'.
        end_date:   The end of the date range. Same format as start_date.
                    For a single day, pass the same value as start_date.

    Returns:
        A formatted string listing each event with its title, start time,
        end time, location (if any), and event ID.
    """
    
    logger.info(f"Fetching events from {start_date} to {end_date}")
    try:
        start_dt = start_of_day(parse_datetime(start_date))
        end_dt = end_of_day(parse_datetime(end_date))

        events = fetch_events(to_rfc3339(start_dt), to_rfc3339(end_dt))

        if not events:
            return f"No events found between {start_date} and {end_date}."

        lines = [f"Events from {start_date} to {end_date}:\n"]

        for event in events:
            title = event.get("summary", "Untitled")
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            location = event.get("location", "")
            event_id = event.get("id", "")

            line = f"• {title} | {start} → {end}"
            if location:
                line += f" | 📍 {location}"
            line += f" | ID: {event_id}"
            lines.append(line)

        logger.info(f"Found {len(events)} event(s)")
        return "\n".join(lines)

    except CalendarToolError:
        raise
    except Exception as e:
        logger.error(f"get_events failed: {e}")
        raise CalendarToolError(f"Error retrieving events: {str(e)}")