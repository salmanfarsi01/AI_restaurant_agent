"""
FastAPI Application Entry Point for AI Restaurant Agent.
Houses Chat, Safe Verification Webhooks, Background Fulfillment, and Marketing APIs.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel

from app.agent.graph import agent_graph
from app.database.database import init_db
from app.database.seed_menu import seed_menu
from app.api import orders, marketing
from app.services.order_service import OrderService
from app.services.worker_dispatcher import WorkerDispatcher
from app.utils.logger import get_logger

log = get_logger(__name__)


async def run_periodic_worker(interval_seconds: int = 25):
    """Background worker that continuously retries pending or failed fulfillment jobs."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await asyncio.to_thread(WorkerDispatcher.dispatch_pending_jobs)
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("Periodic fulfillment worker error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_menu()
    log.info("AI Restaurant Agent system initialized.")
    worker_task = asyncio.create_task(run_periodic_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="AI Restaurant Agent API",
    description="Conversational ordering, anti-scanner verification, physical POS printing, and Google Sheets CRM.",
    version="2.0.0",
    lifespan=lifespan,
)

# Register Subsystem Routers
app.include_router(orders.router)
app.include_router(marketing.router)


class ChatRequest(BaseModel):
    user_id: str
    message: str
    channel: str = "web"


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
