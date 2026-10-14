"""
LangGraph Workflow: Connects language detection, intent routing,
progressive menu greeting, slot collection, and checkout review.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import AgentState
from app.agent import nodes


def _route_intent(state: AgentState) -> str:
    intent = state.get("intent", "general")
    valid_routes = {
        "greeting": "handle_greeting",
        "menu_inquiry": "handle_menu_inquiry",
        "order_update": "handle_order_update",
        "provide_info": "handle_customer_info",
        "checkout_review": "handle_checkout_review",
        "general": "handle_general",
    }
    return valid_routes.get(intent, "handle_general")


def build_graph():
    graph = StateGraph(AgentState)

    # Core NLU nodes
    graph.add_node("detect_language", nodes.detect_language)
    graph.add_node("classify_intent", nodes.classify_intent)

    # Action / Dialogue nodes
    graph.add_node("handle_greeting", nodes.handle_greeting)
    graph.add_node("handle_menu_inquiry", nodes.handle_menu_inquiry)
    graph.add_node("handle_order_update", nodes.handle_order_update)
    graph.add_node("handle_customer_info", nodes.handle_customer_info)
    graph.add_node("handle_checkout_review", nodes.handle_checkout_review)
    graph.add_node("handle_general", nodes.handle_general)

    # Edges
    graph.add_edge(START, "detect_language")
    graph.add_edge("detect_language", "classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "handle_greeting": "handle_greeting",
            "handle_menu_inquiry": "handle_menu_inquiry",
            "handle_order_update": "handle_order_update",
            "handle_customer_info": "handle_customer_info",
            "handle_checkout_review": "handle_checkout_review",
            "handle_general": "handle_general",
        },
    )

    graph.add_edge("handle_greeting", END)
    graph.add_edge("handle_menu_inquiry", END)
    graph.add_edge("handle_order_update", END)
    graph.add_edge("handle_customer_info", END)
    graph.add_edge("handle_checkout_review", END)
    graph.add_edge("handle_general", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


agent_graph = build_graph()
