"""
FastAPI Application Entry Point for AI Restaurant Agent.
Houses Chat, Safe Verification Webhooks, Background Fulfillment, and Marketing APIs.
"""
from fastapi import FastAPI
from pydantic import BaseModel

from app.agent.graph import agent_graph
from app.database.database import init_db
from app.database.seed_menu import seed_menu
from app.api import orders, marketing
from app.services.order_service import OrderService
from app.utils.logger import get_logger

log = get_logger(__name__)

app = FastAPI(
    title="AI Restaurant Agent API",
    description="Conversational ordering, anti-scanner verification, physical POS printing, and Google Sheets CRM.",
    version="2.0.0",
)

# Register Subsystem Routers
app.include_router(orders.router)
app.include_router(marketing.router)


class ChatRequest(BaseModel):
    user_id: str
    message: str
    channel: str = "web"


@app.on_event("startup")
def startup():
    init_db()
    seed_menu()
    log.info("AI Restaurant Agent system initialized.")


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI Restaurant Agent", "version": "2.0.0"}


@app.post("/chat")
def chat(req: ChatRequest):
    """Conversational endpoint: processes customer message through LangGraph brain."""
    config = {"configurable": {"thread_id": req.user_id}}
    result = agent_graph.invoke(
        {
            "user_id": req.user_id,
            "user_message": req.message,
            "channel": req.channel,
        },
        config=config,
    )

    cart = OrderService.get_cart(req.user_id)
    missing = OrderService.get_missing_slots(req.user_id)

    return {
        "response": result.get("response"),
        "language": result.get("language", "en"),
        "intent": result.get("intent", "general"),
        "cart": cart,
        "missing_slots": missing,
        "order_code": result.get("order_code"),
    }
