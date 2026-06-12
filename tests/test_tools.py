from app.tools.get_events import get_events
from app.tools.create_event import create_event
from app.tools.delete_event import delete_event
from app.tools.find_free_slots import find_free_slots
from datetime import datetime, timedelta

# unique title per test run — no duplicates ever
TEST_TITLE = f"Test Event {datetime.now().strftime('%H%M%S')}"


def test_get_events():
    result = get_events("today", "this saturday")
    print(result)
    assert "Events" in result or "No events" in result


def test_create_event():
    result = create_event(
        title=TEST_TITLE,
        start_datetime="this saturday at 6pm",
        end_datetime="this saturday at 7pm",
    )
    print(result)
    assert "Event created successfully" in result

    # cleanup — find and delete what we just created
    events_result = get_events("this saturday", "this saturday")
    for line in events_result.splitlines():
        if TEST_TITLE in line and "ID:" in line:
            event_id = line.split("ID:")[-1].strip()
            delete_event(event_id=event_id)
            break


def test_delete_event():
    # first create a fresh one so delete always has something to work with
    create_event(
        title=TEST_TITLE,
        start_datetime="this saturday at 6pm",
        end_datetime="this saturday at 7pm",
    )
    # find its ID
    events_result = get_events("this saturday", "this saturday")
    event_id = None
    for line in events_result.splitlines():
        if TEST_TITLE in line and "ID:" in line:
            event_id = line.split("ID:")[-1].strip()
            break

    assert event_id is not None, "Could not find created event ID"

    result = delete_event(event_id=event_id)
    print(result)
    assert "successfully deleted" in result


def test_find_free_slots():
    # default working hours
    result = find_free_slots("tomorrow", duration_minutes=30)
    print(result)
    assert "Free slots" in result or "No free slots" in result

    # full day
    result_full = find_free_slots("tomorrow", duration_minutes=30, 
                                   day_start_hour=0, day_end_hour=24)
    print(result_full)
    assert "Free slots" in result_full or "No free slots" in result_full


def test_explicit_date_with_time():
    future = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
    result = create_event(
        title=f"{TEST_TITLE} Explicit",
        start_datetime=f"{future} at 2pm",
        end_datetime=f"{future} at 3pm",
    )
    print(result)
    assert "Event created successfully" in result

    # cleanup
    events_result = get_events(future, future)
    for line in events_result.splitlines():
        if f"{TEST_TITLE} Explicit" in line and "ID:" in line:
            event_id = line.split("ID:")[-1].strip()
            delete_event(event_id=event_id)
            break