from langchain_core.tools import StructuredTool
from app.tools.create_event import create_event
from app.tools.delete_event import delete_event
from app.tools.get_events import get_events
from app.tools.find_free_slots import find_free_slots

calendar_tools = [
    StructuredTool.from_function(create_event),
    StructuredTool.from_function(delete_event),
    StructuredTool.from_function(get_events),
    StructuredTool.from_function(find_free_slots),
]