from app.auth.oauth import get_calendar_service
import datetime

service = get_calendar_service()

now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
result = service.events().list(
    calendarId="primary",
    timeMin=now,
    maxResults=10,
    singleEvents=True,
    orderBy="startTime"
).execute()

events = result.get("items", [])
if not events:
    print("No upcoming events found.")
else:
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, event["summary"])