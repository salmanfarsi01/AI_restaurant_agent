"""
FastAPI app -- mainly useful as a local health-check / manual test endpoint
while you develop. The Telegram bot itself runs via `python -m app.api.telegram`.

Run with: uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from pydantic import BaseModel
from app.agent.graph import agent_graph
from app.database.database import init_db

app = FastAPI(title="Restaurant AI Agent")


class ChatRequest(BaseModel):
    user_id: str
    message: str


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    """Manual test endpoint -- lets you curl the agent without Telegram."""
    config = {"configurable": {"thread_id": req.user_id}}
    result = agent_graph.invoke({"user_id": req.user_id, "user_message": req.message}, config=config)
    return {
        "response": result.get("response"),
        "language": result.get("language"),
        "intent": result.get("intent"),
        "cart": result.get("cart", []),
    }
