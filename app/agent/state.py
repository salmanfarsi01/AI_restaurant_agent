"""
Shared LangGraph state object that flows through every node.
"""
from typing import TypedDict, Literal, Optional, List, Dict, Any


class AgentState(TypedDict, total=False):
    user_id: str
    user_message: str
    channel: str
    language: Literal["en", "bn"]
    intent: Literal["greeting", "menu_inquiry", "order_update", "provide_info", "checkout_review", "general"]
    cart: List[Dict[str, Any]]
    customer_info: Dict[str, Any]
    missing_slots: List[str]
    retrieved_context: str
    order_draft_created: bool
    confirmation_link_sent: bool
    order_code: Optional[str]
    response: str
