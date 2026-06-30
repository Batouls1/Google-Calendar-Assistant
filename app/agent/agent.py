import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from app.agent.tools import calendar_tools
from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)


def _build_system_prompt() -> str:
    """
    Build the system prompt with today's date injected fresh each call.
    Called per-request so the date never goes stale if the server runs
    past midnight.
    """
    from app.utils.datetime_utils import now_beirut
    today = now_beirut().strftime("%A, %B %d, %Y")

    return f"""You are a helpful Google Calendar assistant. \
You help the user manage their calendar by creating events, \
viewing their schedule, deleting events, and finding free time slots.

Today's date: {today}. Timezone: Asia/Beirut (Lebanon).
When showing events for "this week" or the "current week", \
only show events from today onwards — do not include past days of the week.

Rules you must follow:
- Before deleting any event, always call get_events first to confirm \
the exact event ID and details. When asking the user to confirm deletion, \
describe the event naturally (title and time only) — never show raw event IDs.
- If the user asks to create an event but doesn't give an end time, \
default to 1 hour after the start.
- If a tool returns an error message, report it clearly to the user \
and suggest what to do next.
- Never invent or assume event details. Only report what the tools return.
- Be concise and conversational. Avoid unnecessary preamble.
- Before creating an event, always call get_events first to check \
if the requested time slot is already occupied. If a conflict exists, \
tell the user what's already there and ask if they want to proceed \
or pick a different time.
- You are strictly a calendar assistant. If the user asks about anything \
unrelated to their calendar or scheduling, politely decline and redirect \
them to calendar-related tasks.
"""


def create_calendar_agent():
    model = init_chat_model("openai:gpt-4o", temperature=0)
    checkpointer = MemorySaver()

    return create_agent(
        model=model,
        tools=calendar_tools,
        system_prompt=_build_system_prompt(), 
        checkpointer=checkpointer,
    )