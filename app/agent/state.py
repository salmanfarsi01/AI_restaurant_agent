"""
Shared state object that flows through every LangGraph node.
"""
from typing import TypedDict, Literal


class CartItem(TypedDict):
    item_id: str
    name: str
    quantity: int
    unit_price: float


class AgentState(TypedDict, total=False):
    user_id: str
    user_message: str
    language: Literal["en", "bn"]
    intent: Literal["order", "menu_question", "policy_question", "general", "checkout"]
    restaurant_name: str  # set once the user picks/confirms a restaurant; narrows retrieval
    retrieved_context: str
    cart: list[CartItem]
    response: str
