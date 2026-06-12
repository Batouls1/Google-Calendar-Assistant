from app.services.calendar_service import fetch_events
from app.utils.datetime_utils import parse_datetime, to_rfc3339, start_of_day, end_of_day, BEIRUT_TZ
from app.utils.logger import get_logger
from app.utils.exceptions import CalendarToolError
from datetime import datetime, timedelta

logger = get_logger(__name__)


def find_free_slots(date: str, duration_minutes: int = 60,
                    day_start_hour: int = 9, day_end_hour: int = 20) -> str:
    """
    Find available free time slots on a given day.

    Use this tool when the user wants to know when they are free, available,
    or has gaps in their schedule. Also use it when the user asks when they
    can schedule something for a given duration on a specific day.

    Note: if an all-day event exists on the requested day (e.g. 'Out of office',
    'Project Milestone'), the entire day is treated as unavailable.

    Args:
        date:               The day to check for free slots. Accepts natural
                            language like 'today', 'tomorrow', 'this monday',
                            or explicit dates like '2026-06-15'.
        duration_minutes:   Minimum length of a free slot in minutes.
                            Defaults to 60 (1 hour) if not specified.
        day_start_hour:     Start of the day window to check (default 9 for 9am).
        day_end_hour:       End of the day window to check (default 20 for 8pm).

    Returns:
        A formatted string listing all free time windows on that day that
        are at least as long as duration_minutes.
    """
    logger.info(f"Finding free slots on {date} for {duration_minutes} min blocks")
    try:
        day_end_hour = min(day_end_hour, 23)

        date_dt = parse_datetime(date)
        start = to_rfc3339(start_of_day(date_dt))
        end = to_rfc3339(end_of_day(date_dt))

        events = fetch_events(start, end)

        day = date_dt.date()
        window_start = datetime(day.year, day.month, day.day, day_start_hour, tzinfo=BEIRUT_TZ)
        window_end = datetime(day.year, day.month, day.day, day_end_hour, tzinfo=BEIRUT_TZ)

        busy = []
        for e in events:
            e_start = e["start"].get("dateTime")
            e_end = e["end"].get("dateTime")
            if e_start and e_end:
                busy.append((
                    datetime.fromisoformat(e_start).astimezone(BEIRUT_TZ),
                    datetime.fromisoformat(e_end).astimezone(BEIRUT_TZ)
                ))
            else:
                # all-day event — block the entire window
                title = e.get("summary", "an all-day event")
                logger.info(f"All-day event found ('{title}') — treating {date} as fully booked")
                return (
                    f"You have an all-day event on {date} ('{title}'), "
                    f"so the day is considered fully booked. No free slots available."
                )

        busy.sort(key=lambda x: x[0])

        free_slots = []
        cursor = window_start

        for busy_start, busy_end in busy:
            if cursor < busy_start:
                gap_minutes = (busy_start - cursor).seconds // 60
                if gap_minutes >= duration_minutes:
                    free_slots.append((cursor, busy_start))
            cursor = max(cursor, busy_end)

        if cursor < window_end:
            gap_minutes = (window_end - cursor).seconds // 60
            if gap_minutes >= duration_minutes:
                free_slots.append((cursor, window_end))

        if not free_slots:
            return f"No free slots of {duration_minutes}+ minutes found on {date}."

        lines = [f"Free slots on {date} (min {duration_minutes} min):\n"]
        for slot_start, slot_end in free_slots:
            duration = (slot_end - slot_start).seconds // 60
            lines.append(
                f"• {slot_start.strftime('%I:%M %p')} → {slot_end.strftime('%I:%M %p')} "
                f"({duration} min)"
            )

        return "\n".join(lines)

    except CalendarToolError:
        raise
    except Exception as e:
        logger.error(f"find_free_slots failed: {e}")
        raise CalendarToolError(f"Error finding free slots: {str(e)}")