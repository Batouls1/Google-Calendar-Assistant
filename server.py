import re
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.agent.message_utils import (
    get_tool_outputs,
    split_into_turns,
    turn_tool_outputs,
    turn_final_ai_text,
)
from app.cards import build_card
from app.services.session_service import (
    init_sessions_db,
    close_sessions_db,
    record_session_if_new,
    list_sessions,
    delete_session,
)
from app.utils.datetime_utils import now_beirut
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Agent singleton 
# Initialised in lifespan() rather than at module level so that:
# 1. SqliteSaver has time to open/create the DB file before the
#    agent is constructed — module-level init runs at import time, before
#    any startup hooks, which can crash if the DB path doesn't exist yet.
# 2. Failures surface as a clean startup error rather than a cryptic
#    ImportError when the module is first loaded.

agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    from app.agent.agent import create_calendar_agent, close_agent_db
    agent = create_calendar_agent()
    logger.info("Calendar agent initialised")
 
    init_sessions_db()
 
    yield
 
    close_agent_db()
    close_sessions_db()
    logger.info("Server shutting down")
 
 
app = FastAPI(title="Calendar Assistant", lifespan=lifespan)
 
 
class ChatRequest(BaseModel):
    message: str
    thread_id: str
 
 
class ChatResponse(BaseModel):
    response: str
    thread_id: str
    card: Optional[dict] = None
 
 
DATE_ANCHOR_PATTERN = re.compile(r"^\[Today is [^\]]+\]\s*")
 
 
def _strip_date_anchor(text: str) -> str:
    """Remove the '[Today is ...] ' prefix injected before every user message
    sent to the agent. Used when replaying history so the user never sees
    the internal anchoring — only their original message."""
    return DATE_ANCHOR_PATTERN.sub("", text)
 
 
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    logger.info(f"[{request.thread_id}] User: {request.message}")
 
    # Record this thread in the sessions table if it's the first message —
    # no-op on every later message in the same thread (see session_service).
    record_session_if_new(request.thread_id, request.message)
 
    try:
        # Anchor today's date in every message to prevent date drift
        # in long conversations where the LLM loses track of "today"
        today_str = now_beirut().strftime("%A, %B %d, %Y")
        anchored_message = f"[Today is {today_str}] {request.message}"
 
        config = {"configurable": {"thread_id": request.thread_id}}
        result = agent.invoke(
            {"messages": [{"role": "user", "content": anchored_message}]},
            config=config,
        )
 
        response_text = result["messages"][-1].content
        tool_outputs  = get_tool_outputs(result, current_turn_only=True)
 
        logger.info(f"  Tools this turn: {[t['name'] for t in tool_outputs]}")
        for t in tool_outputs:
            logger.info(f"  [{t['name']}]: {t['content'][:100]}")
        logger.info(f"  Agent: {response_text[:150]}")
 
        card = build_card(tool_outputs, response_text, request.message, result)
        return ChatResponse(response=response_text, thread_id=request.thread_id, card=card)
 
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return ChatResponse(
            response="Something went wrong. Please try again.",
            thread_id=request.thread_id,
        )
 
 
@app.get("/sessions")
def get_sessions():
    """Return all chat sessions for the sidebar, most recent first."""
    return {"sessions": list_sessions()}
 
 
@app.get("/sessions/{thread_id}/messages")
def get_session_messages(thread_id: str):
    """Return a thread's full conversation history, reconstructing cards
    per turn so old sessions render the same way they did live.
 
    Splits the message history into turns (one per human message) and
    re-runs build_card() against each turn's tool outputs — the exact
    same function live /chat requests use. This keeps card logic in one
    place; nothing here duplicates build_card's matching rules.
    """
    config = {"configurable": {"thread_id": thread_id}}
    state = agent.get_state(config)
 
    if not state.values:
        raise HTTPException(status_code=404, detail="Thread not found")
 
    all_messages = state.values.get("messages", [])
    turns = split_into_turns(all_messages)
 
    replay = []
    for turn in turns:
        user_text = _strip_date_anchor(getattr(turn["human"], "content", ""))
        replay.append({"role": "user", "content": user_text})
 
        tool_outputs = turn_tool_outputs(turn)
        ai_text = turn_final_ai_text(turn)
 
        card = None
        if tool_outputs:
            # state.values has the same {'messages': [...]} shape build_card
            # expects for its history-search fallback (deleted event titles).
            card = build_card(tool_outputs, ai_text, user_text, state.values)
 
        if card:
            replay.append({"role": "assistant", "content": ai_text, "card": card})
        elif ai_text:
            replay.append({"role": "assistant", "content": ai_text})
 
    return {"thread_id": thread_id, "messages": replay}
 
 
@app.delete("/sessions/{thread_id}")
def delete_session_endpoint(thread_id: str):
    """Remove a session from the sidebar. See session_service.delete_session
    for what this does and doesn't clean up."""
    deleted = delete_session(thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": thread_id}
 
 
@app.get("/new-thread")
async def new_thread():
    return {"thread_id": str(uuid.uuid4())}
 
 
app.mount("/ui", StaticFiles(directory="ui"), name="ui")
 
 
@app.get("/")
async def root():
    return FileResponse("ui/index.html")