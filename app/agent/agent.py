import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.sqlite import SqliteSaver
from app.agent.tools import calendar_tools
from app.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "memory.db"
 
# Held at module level so the connection survives for the life of the
# process — reopening per-request would be wasteful and risks losing
# in-flight writes. Closed explicitly via close_agent_db() on shutdown.
_db_connection: sqlite3.Connection | None = None

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
    global _db_connection
 
    model = init_chat_model("openai:gpt-4o", temperature=0)
 
    # check_same_thread=False: FastAPI may invoke agent.invoke() from a
    # different thread per request. SqliteSaver serializes its own writes
    # internally, so sharing one connection across threads is safe here.
    _db_connection = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    checkpointer = SqliteSaver(_db_connection)
 
    # Creates the checkpoint tables on first run. Safe to call every time
    # the agent is created — it's a no-op if the tables already exist.
    checkpointer.setup()
 
    logger.info(f"SQLite checkpointer ready at {DB_PATH}")
 
    return create_agent(
        model=model,
        tools=calendar_tools,
        system_prompt=_build_system_prompt(),
        checkpointer=checkpointer,
    )
 
 
def close_agent_db() -> None:
    """Close the SQLite connection. Call this on FastAPI shutdown."""
    global _db_connection
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None
        logger.info("SQLite checkpointer connection closed")