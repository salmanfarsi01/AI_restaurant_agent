"""
Builds the LangGraph state graph:

          START
            |
   detect_language
            |
   classify_intent
            |
     +------+-------------------+------------------+
     |                          |                   |
  order/checkout       menu_question/policy_q     general
     |                          |                   |
 handle_order              rag_retrieve             |
     |                          |                   |
     +------------ generate_response ---------------+
                            |
                           END

Per-user memory is handled by LangGraph's checkpointer, keyed on thread_id
(we use the Telegram user id as thread_id) -- so the agent remembers each
user's ongoing cart/conversation across turns.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.state import AgentState
from app.agent import nodes


def _route_after_intent(state: AgentState) -> str:
    intent = state.get("intent", "general")
    if intent in ("order", "checkout"):
        return "handle_order"
    if intent in ("menu_question", "policy_question"):
        return "rag_retrieve"
    return "generate_response"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("detect_language", nodes.detect_language)
    graph.add_node("classify_intent", nodes.classify_intent)
    graph.add_node("handle_order", nodes.handle_order)
    graph.add_node("rag_retrieve", nodes.rag_retrieve)
    graph.add_node("generate_response", nodes.generate_response)

    graph.add_edge(START, "detect_language")
    graph.add_edge("detect_language", "classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        _route_after_intent,
        {
            "handle_order": "handle_order",
            "rag_retrieve": "rag_retrieve",
            "generate_response": "generate_response",
        },
    )

    graph.add_edge("handle_order", "generate_response")
    graph.add_edge("rag_retrieve", "generate_response")
    graph.add_edge("generate_response", END)

    checkpointer = MemorySaver()  # swap for SqliteSaver/PostgresSaver for durable memory
    return graph.compile(checkpointer=checkpointer)


# a single compiled graph instance reused across requests
agent_graph = build_graph()
