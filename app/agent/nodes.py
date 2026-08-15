"""
LangGraph node functions. Each takes AgentState and returns a partial state update.
"""
import json
from langchain_core.messages import HumanMessage
from app.agent.state import AgentState
from app.agent import prompts
from app.models.llm_loader import get_llm
from app.rag.retriever import retrieve, format_docs_for_prompt
from app.utils.logger import get_logger

log = get_logger(__name__)


def detect_language(state: AgentState) -> dict:
    llm = get_llm(temperature=0.0)
    prompt = prompts.LANGUAGE_DETECTION_PROMPT.format(message=state["user_message"])
    result = llm.invoke([HumanMessage(content=prompt)]).content.strip().lower()
    lang = "bn" if "bn" in result else "en"
    log.info(f"Detected language: {lang}")
    return {"language": lang}


def classify_intent(state: AgentState) -> dict:
    llm = get_llm(temperature=0.0)
    prompt = prompts.INTENT_CLASSIFICATION_PROMPT.format(message=state["user_message"])
    result = llm.invoke([HumanMessage(content=prompt)]).content.strip().lower()

    valid = {"order", "checkout", "menu_question", "policy_question", "general"}
    intent = next((v for v in valid if v in result), "general")
    log.info(f"Classified intent: {intent}")
    return {"intent": intent}


def rag_retrieve(state: AgentState) -> dict:
    # Policy docs are truly bilingual (policy_en.txt / policy_bn.txt), so it's
    # worth restricting to the user's language there. Menu/restaurant docs are
    # English-only (sourced from the CSV) -- don't filter those by language,
    # since the multilingual embedding model already lets a Bangla query
    # retrieve the right English menu chunk directly (cross-lingual retrieval).
    lang_filter = state.get("language") if state.get("intent") == "policy_question" else None
    docs = retrieve(
        state["user_message"],
        lang=lang_filter,
        restaurant_name=state.get("restaurant_name"),
        k=4,
    )
    context = format_docs_for_prompt(docs)
    return {"retrieved_context": context}


def handle_order(state: AgentState) -> dict:
    """Extract an add/remove/clear action via the LLM and update the cart."""
    docs = retrieve(
        state["user_message"],
        restaurant_name=state.get("restaurant_name"),
        k=6,
    )
    menu_context = format_docs_for_prompt(docs)

    llm = get_llm(temperature=0.0)
    prompt = prompts.ORDER_EXTRACTION_PROMPT.format(context=menu_context, message=state["user_message"])
    raw = llm.invoke([HumanMessage(content=prompt)]).content.strip()

    cart = list(state.get("cart", []))
    try:
        parsed = json.loads(raw)
        action = parsed.get("action", "none")
        name = parsed.get("item_name", "")
        qty = int(parsed.get("quantity", 1) or 1)

        if action == "add" and name:
            # look up the real price from the retrieved menu docs by name match
            unit_price = 0.0
            for d in docs:
                if d.metadata.get("source") == "menu" and name.lower() in d.page_content.lower():
                    unit_price = d.metadata.get("price") or 0.0
                    break
            cart.append({"item_id": name, "name": name, "quantity": qty, "unit_price": unit_price})
        elif action == "remove" and name:
            cart = [c for c in cart if name.lower() not in c["name"].lower()]
        elif action == "clear":
            cart = []
    except (json.JSONDecodeError, ValueError) as e:
        log.warning(f"Could not parse order extraction JSON: {raw!r} ({e})")

    return {"cart": cart, "retrieved_context": menu_context}


def generate_response(state: AgentState) -> dict:
    lang = state.get("language", "en")
    intent = state.get("intent", "general")
    llm = get_llm(temperature=0.3)

    if intent in ("menu_question", "policy_question"):
        template = prompts.RAG_ANSWER_PROMPT_BN if lang == "bn" else prompts.RAG_ANSWER_PROMPT_EN
        prompt = template.format(context=state.get("retrieved_context", ""), question=state["user_message"])

    elif intent == "order":
        cart = state.get("cart", [])
        cart_lines = "\n".join(f"- {c['quantity']}x {c['name']}" for c in cart) or (
            "empty cart" if lang == "en" else "খালি কার্ট"
        )
        prefix = "Current cart:\n" if lang == "en" else "বর্তমান কার্ট:\n"
        prompt = (
            f"{prefix}{cart_lines}\n\n"
            + (f"Briefly confirm this update to the customer in English."
               if lang == "en" else "গ্রাহককে সংক্ষেপে বাংলায় এই আপডেট নিশ্চিত করুন।")
        )

    elif intent == "checkout":
        cart = state.get("cart", [])
        total = sum(c["unit_price"] * c["quantity"] for c in cart)
        prompt = (
            f"Summarize this order for confirmation and ask the customer to confirm. Cart: {cart}. Total: {total}."
            if lang == "en"
            else f"গ্রাহককে নিশ্চিতকরণের জন্য এই অর্ডারের সারাংশ দিন এবং নিশ্চিত করতে বলুন। কার্ট: {cart}। মোট: {total}।"
        )

    else:
        template = prompts.GENERAL_RESPONSE_PROMPT_BN if lang == "bn" else prompts.GENERAL_RESPONSE_PROMPT_EN
        prompt = template.format(message=state["user_message"])

    result = llm.invoke([HumanMessage(content=prompt)]).content.strip()
    return {"response": result}
