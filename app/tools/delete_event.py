from app.services.calendar_service import fetch_events, remove_event
from app.utils.datetime_utils import parse_datetime, to_rfc3339, start_of_day, end_of_day, now_beirut
from app.utils.logger import get_logger
from app.utils.exceptions import CalendarToolError, EventNotFoundError
from datetime import timedelta

logger = get_logger(__name__)


def delete_event(event_id: str = "", title: str = "", date: str = "") -> str:
    """
    Delete an event from the user's Google Calendar.

    Use this tool when the user wants to cancel, remove, or delete a calendar
    event. You can delete by event ID (preferred, most precise) or by searching
    for the event title on a specific date.

    Args:
        event_id:   The unique ID of the event to delete. Use this when the ID
                    is already known from a previous get_events call. If provided,
                    title and date are ignored.
        title:      The title or name of the event to delete. Used together with
                    date to find the event when ID is not known.
        date:       The date to search on when deleting by title. Accepts natural
                    language like 'today', 'tomorrow', 'this friday', or explicit
                    dates like '2026-06-15'.

    Returns:
        A confirmation string that the event was deleted, or an error message.
    """
    logger.info(f"Deleting event — id='{event_id}' title='{title}' date='{date}'")
    try:
        # path 1: delete directly by ID
        if event_id:
            remove_event(event_id)
            logger.info(f"Deleted event with ID: {event_id}")
            return f"Event with ID '{event_id}' was successfully deleted."

        # path 2: find by title + date
        if not title or not date:
            raise CalendarToolError(
                "Please provide either an event ID, or both a title and date to find the event."
            )

        date_dt = parse_datetime(date)
        start = to_rfc3339(start_of_day(date_dt))
        end = to_rfc3339(end_of_day(date_dt))
        events = fetch_events(start, end)

        matches = [
            e for e in events
            if title.lower() in e.get("summary", "").lower()
        ]

        if not matches:
            raise EventNotFoundError(
                f"No event found with title '{title}' on {date}."
            )

        if len(matches) > 1:
            names = "\n".join(
                f"• {e.get('summary')} | ID: {e.get('id')}" for e in matches
            )
            return (
                f"Found {len(matches)} events matching '{title}' on {date}. "
                f"Please specify the event ID to delete the correct one:\n{names}"
            )

        target = matches[0]
        remove_event(target["id"])
        logger.info(f"Deleted event: '{target.get('summary')}' ID: {target.get('id')}")
        return f"Event '{target.get('summary')}' on {date} was successfully deleted."

    except (CalendarToolError, EventNotFoundError):
        raise
    except Exception as e:
        logger.error(f"delete_event failed: {e}")
        raise CalendarToolError(f"Error deleting event: {str(e)}")