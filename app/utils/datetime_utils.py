from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil import parser as dateutil_parser

BEIRUT_TZ = ZoneInfo("Asia/Beirut")


def now_beirut() -> datetime:
    return datetime.now(BEIRUT_TZ)


def resolve_relative_date(dt_string: str) -> datetime:
    """Handle natural language date terms before passing to dateutil."""
    now = now_beirut()
    s = dt_string.strip().lower()

    time_part = None
    if " at " in s:
        date_part, time_part = s.split(" at ", 1)
        s = date_part.strip()

    resolved = None

    if s == "today":
        resolved = now
    elif s == "tomorrow":
        resolved = now + timedelta(days=1)
    elif s == "yesterday":
        resolved = now - timedelta(days=1)
    else:
        weekdays = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        for i, day in enumerate(weekdays):
            if s in (day, f"this {day}", f"next {day}"):
                days_ahead = i - now.weekday()
                if days_ahead < 0 or s.startswith("next"):
                    days_ahead += 7
                resolved = now + timedelta(days=days_ahead)
                break

        if resolved is None and s.startswith("in "):
            parts = s.split()
            if len(parts) == 3 and parts[1].isdigit():
                n = int(parts[1])
                unit = parts[2]
                if "day" in unit:
                    resolved = now + timedelta(days=n)
                elif "week" in unit:
                    resolved = now + timedelta(weeks=n)

        if resolved is None:
            if time_part:
                resolved = dateutil_parser.parse(s)
            else:
                return dateutil_parser.parse(dt_string)

    if time_part:
        parsed_time = dateutil_parser.parse(time_part)
        resolved = resolved.replace(
            hour=parsed_time.hour,
            minute=parsed_time.minute,
            second=0,
            microsecond=0
        )

    return resolved


def to_beirut(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIRUT_TZ)
    return dt.astimezone(BEIRUT_TZ)


def parse_datetime(dt_string: str) -> datetime:
    dt = resolve_relative_date(dt_string)
    return to_beirut(dt)


def to_rfc3339(dt: datetime) -> str:
    return to_beirut(dt).isoformat()


def start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=0)