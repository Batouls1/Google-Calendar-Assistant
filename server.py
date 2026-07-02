import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from app.agent.message_utils import get_tool_outputs
from app.cards import build_card
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
    yield
    close_agent_db()
    logger.info("Server shutting down")


app = FastAPI(title="Calendar Assistant", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    thread_id: str


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    card: Optional[dict] = None


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    logger.info(f"[{request.thread_id}] User: {request.message}")
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


@app.get("/new-thread")
async def new_thread():
    return {"thread_id": str(uuid.uuid4())}


app.mount("/ui", StaticFiles(directory="ui"), name="ui")


@app.get("/")
async def root():
    return FileResponse("ui/index.html")