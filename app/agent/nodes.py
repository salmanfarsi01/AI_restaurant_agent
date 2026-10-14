"""
LangGraph node functions for AI Restaurant Agent.
Integrates Groq LLM with transactional OrderService and EmailService.
"""
import json
import re
from typing import Dict, Any, List, Tuple
from langchain_core.messages import HumanMessage

from app.agent.state import AgentState
from app.agent import prompts
from app.models.llm_loader import get_llm
from app.rag.retriever import retrieve, format_docs_for_prompt
from app.services.order_service import OrderService
from app.services.email_service import EmailService
from app.utils.logger import get_logger

log = get_logger(__name__)


def detect_language(state: AgentState) -> Dict[str, Any]:
    """Detects whether user is communicating in English or Bangla."""
    msg = state.get("user_message", "")
    # Fast Unicode block detection for Bangla
    if any("\u0980" <= ch <= "\u09FF" for ch in msg):
        lang = "bn"
    else:
        llm = get_llm(temperature=0.0)
        prompt = prompts.LANGUAGE_DETECTION_PROMPT.format(message=msg)
        result = llm.invoke([HumanMessage(content=prompt)]).content.strip().lower()
        lang = "bn" if "bn" in result else "en"
    return {"language": lang}


def classify_intent(state: AgentState) -> Dict[str, Any]:
    """Classifies user message into standard intents."""
    msg = state.get("user_message", "")
    user_id = state.get("user_id", "default_user")

    # Fast pattern match for common greetings
    clean_msg = msg.strip().lower()
    if clean_msg in ["hi", "hello", "hey", "hola", "start", "/start", "হাই", "হ্যালো", "সালাম", "assalamu alaikum"]:
        return {"intent": "greeting"}

    # Fast check for explicit email/phone pattern in message
    has_email = bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", clean_msg))
    has_phone = bool(re.search(r"(\+?88)?01[3-9]\d{8}", clean_msg))
    if has_email or has_phone:
        return {"intent": "provide_info"}

    llm = get_llm(temperature=0.0)
    prompt = prompts.INTENT_CLASSIFICATION_PROMPT.format(message=msg)
    raw = llm.invoke([HumanMessage(content=prompt)]).content.strip().lower()

    valid_intents = {"greeting", "menu_inquiry", "order_update", "provide_info", "checkout_review", "general"}
    intent = next((v for v in valid_intents if v in raw), "general")

    # Intent priority rules
    if any(w in clean_msg for w in ["confirm", "checkout", "finalize", "place order", "send email", "কনফার্ম"]):
        intent = "checkout_review"
    elif any(w in clean_msg for w in ["order", "i want", "give me", "add", "please bring", "নেব"]):
        intent = "order_update"

    return {"intent": intent}


def handle_greeting(state: AgentState) -> Dict[str, Any]:
    """Returns warm greeting with progressive category disclosure."""
    lang = state.get("language", "en")
    user_id = state.get("user_id", "default_user")
    cart = OrderService.get_cart(user_id)

    base_greeting = prompts.PROGRESSIVE_GREETING_BN if lang == "bn" else prompts.PROGRESSIVE_GREETING_EN

    if cart:
        cart_lines = "\n".join(f"• {c['quantity']}x {c['name']} (৳{c['line_total']})" for c in cart)
        if lang == "bn":
            cart_notice = f"\n\n🛒 **আপনার কার্টে থাকা খাবারসমূহ:**\n{cart_lines}\n\nআপনি কি আরও কিছু যোগ করতে চান নাকি অর্ডার চূড়ান্ত করতে চান?"
        else:
            cart_notice = f"\n\n🛒 **You have items in your cart:**\n{cart_lines}\n\nWould you like to add more items, or proceed to checkout?"
        return {"response": base_greeting + cart_notice}

    return {"response": base_greeting}


def handle_menu_inquiry(state: AgentState) -> Dict[str, Any]:
    """Uses RAG to answer questions about food, spice levels, ingredients, or policies."""
    lang = state.get("language", "en")
    msg = state.get("user_message", "")

    # Retrieve docs from Qdrant / disk
    try:
        docs = retrieve(msg, k=4)
        context = format_docs_for_prompt(docs)
    except Exception as e:
        log.warning("RAG retrieval exception: %s. Using menu database fallback.", e)
        menu_items = OrderService.get_menu_by_category()
        context = "\n".join(
            f"Category: {cat}\n" + "\n".join(f"- {i['name']}: ৳{i['price']} ({i['description']})" for i in items)
            for cat, items in menu_items.items()
        )

    llm = get_llm(temperature=0.2)
    template = prompts.RAG_ANSWER_PROMPT_BN if lang == "bn" else prompts.RAG_ANSWER_PROMPT_EN
    prompt = template.format(context=context, question=msg)
    answer = llm.invoke([HumanMessage(content=prompt)]).content.strip()

    return {"response": answer, "retrieved_context": context}


def _extract_and_apply_cart_items(user_id: str, msg: str, lang: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Helper that parses dishes/quantities from text (single or multi-item) and updates cart."""
    menu_items = OrderService.get_menu_by_category()
    menu_list = []
    for cat, items in menu_items.items():
        for i in items:
            menu_list.append(f"{i['name']} (৳{i['price']})")
    menu_context = "\n".join(menu_list)

    llm = get_llm(temperature=0.0)
    prompt = prompts.CART_ACTION_PROMPT.format(context=menu_context, message=msg)
    raw = llm.invoke([HumanMessage(content=prompt)]).content.strip()

    parsed = None
    try:
        parsed = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except Exception:
                pass

    if not isinstance(parsed, dict):
        parsed = {"action": "none", "items": []}

    action = parsed.get("action", "none")
    items = parsed.get("items", [])
    if not items and parsed.get("item_name"):
        items = [{"item_name": parsed.get("item_name"), "quantity": int(parsed.get("quantity", 1) or 1)}]

    cart = OrderService.get_cart(user_id)
    added_feedbacks = []

    if action == "clear":
        OrderService.clear_cart(user_id)
        msg_out = "আপনার কার্ট খালি করা হয়েছে।" if lang == "bn" else "Your cart has been cleared."
        return msg_out, []

    if action in ("add", "modify") and items:
        for it in items:
            it_name = it.get("item_name", "").strip()
            it_qty = int(it.get("quantity", 1) or 1)
            if it_name:
                success, feedback, updated_cart = OrderService.add_to_cart(user_id, it_name, it_qty)
                cart = updated_cart
                if success:
                    added_feedbacks.append(f"{it_qty}x {it_name}")

    elif action == "remove" and items:
        for it in items:
            it_name = it.get("item_name", "").strip()
            if it_name:
                success, feedback, updated_cart = OrderService.modify_cart_item(user_id, it_name, 0)
                cart = updated_cart
                added_feedbacks.append(f"Removed {it_name}")

    if added_feedbacks:
        if action == "remove":
            response_msg = ", ".join(added_feedbacks)
        else:
            response_msg = (
                f"কার্টে যোগ করা হয়েছে: {', '.join(added_feedbacks)}"
                if lang == "bn"
                else f"Added to your cart: {', '.join(added_feedbacks)}"
            )
        return response_msg, cart

    # Fallback keyword match if nothing was parsed
    matched_item = OrderService.find_menu_item(msg)
    if matched_item:
        success, feedback, updated_cart = OrderService.add_to_cart(user_id, matched_item.name, 1)
        return feedback, updated_cart

    return "", cart


def handle_order_update(state: AgentState) -> Dict[str, Any]:
    """Parses order dish & quantity, updates persistent cart, and checks remaining slots."""
    user_id = state.get("user_id", "default_user")
    lang = state.get("language", "en")
    msg = state.get("user_message", "")

    response_msg, cart = _extract_and_apply_cart_items(user_id, msg, lang)
    if not response_msg and not cart:
        response_msg = (
            "আমি আপনার অর্ডার বুঝতে পারছি না। দয়া করে মেনু থেকে খাবারের নাম বলুন।"
            if lang == "bn"
            else "I couldn't identify which dish you want to order. Could you please specify the dish name from our menu?"
        )

    # Calculate remaining missing slots
    missing = OrderService.get_missing_slots(user_id)
    totals = OrderService.calculate_totals(cart)

    cart_summary = "\n".join(f"• {c['quantity']}x {c['name']} (৳{c['line_total']})" for c in cart)
    if lang == "bn":
        slot_prompt = ""
        if "customer_name" in missing or "delivery_address" in missing or "customer_email" in missing:
            slot_prompt = f"\n\nঅর্ডার সম্পূর্ণ করতে অনুগ্রহ করে আপনার **নাম, ডেলিভারি ঠিকানা, ইমেইল এবং ফোন নম্বর** প্রদান করুন।"
        final_reply = f"{response_msg}\n\n🛒 **বর্তমান কার্ট (মোট: ৳{totals['total_amount']}):**\n{cart_summary}{slot_prompt}"
    else:
        slot_prompt = ""
        if "customer_name" in missing or "delivery_address" in missing or "customer_email" in missing:
            slot_prompt = f"\n\nTo proceed with delivery, please provide your **Full Name, Delivery Address, Email, and Phone Number**."
        final_reply = f"{response_msg}\n\n🛒 **Current Cart (Total: ৳{totals['total_amount']}):**\n{cart_summary}{slot_prompt}"

    return {"cart": cart, "response": final_reply}


def handle_customer_info(state: AgentState) -> Dict[str, Any]:
    """Extracts customer personal slots and updates session record."""
    user_id = state.get("user_id", "default_user")
    lang = state.get("language", "en")
    msg = state.get("user_message", "")

    llm = get_llm(temperature=0.0)
    prompt = prompts.SLOT_EXTRACTION_PROMPT.format(message=msg)
    raw = llm.invoke([HumanMessage(content=prompt)]).content.strip()

    extracted = {}
    try:
        extracted = json.loads(raw)
    except Exception:
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            try:
                extracted = json.loads(match.group())
            except Exception:
                pass

    # Regex safety enhancements
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", msg)
    if email_match and not extracted.get("customer_email"):
        extracted["customer_email"] = email_match.group()

    phone_match = re.search(r"(\+?88)?01[3-9]\d{8}", msg)
    if phone_match and not extracted.get("customer_phone"):
        extracted["customer_phone"] = phone_match.group()

    name_match = re.search(r"(?:my name is|name[:\s]+)([a-zA-Z\s\u0980-\u09FF\.\-']{2,40})", msg, re.IGNORECASE)
    if name_match and not extracted.get("customer_name"):
        extracted["customer_name"] = name_match.group(1).split(",")[0].strip()

    addr_match = re.search(r"(?:address[:\s]+|location[:\s]+|delivery[:\s]+|to[:\s]+)(.+)$", msg, re.IGNORECASE)
    if addr_match and not extracted.get("delivery_address"):
        extracted["delivery_address"] = addr_match.group(1).strip()

    info = OrderService.update_customer_info(user_id, extracted)

    # If the user also specified food items along with details in the same turn:
    added_msg, cart = _extract_and_apply_cart_items(user_id, msg, lang)
    if not cart:
        cart = OrderService.get_cart(user_id)

    missing = OrderService.get_missing_slots(user_id)

    if not cart:
        reply = (
            "আপনার তথ্য সংরক্ষিত হয়েছে। অনুগ্রহ করে আপনি কোন খাবারটি অর্ডার করতে চান তা জানান।"
            if lang == "bn"
            else "Your details have been saved! What dishes would you like to order today?"
        )
        return {"customer_info": info, "response": reply}

    totals = OrderService.calculate_totals(cart)
    cart_summary = "\n".join(f"• {c['quantity']}x {c['name']} (৳{c['line_total']})" for c in cart)

    if not missing:
        # All slots ready! Suggest checkout review
        if lang == "bn":
            reply = (
                f"ধন্যবাদ! আপনার সকল তথ্য পাওয়া গেছে।\n\n"
                f"🛒 **অর্ডারের বিবরণ:**\n{cart_summary}\n"
                f"**সর্বমোট বিল: ৳{totals['total_amount']} (ক্যাশ অন ডেলিভারি)**\n\n"
                f"👤 নাম: {info.get('customer_name')}\n"
                f"📍 ঠিকানা: {info.get('delivery_address')}\n"
                f"✉️ ইমেইল: {info.get('customer_email')}\n"
                f"📞 ফোন: {info.get('customer_phone')}\n\n"
                f"আপনি কি কনফার্মেশন ইমেইল পাঠাতে চান? বলুন 'হ্যাঁ' বা 'অর্ডার কনফার্ম করুন'।"
            )
        else:
            reply = (
                f"Great! We have all your order details:\n\n"
                f"🛒 **Your Items:**\n{cart_summary}\n"
                f"**Grand Total: ৳{totals['total_amount']} (Cash on Delivery)**\n\n"
                f"👤 Name: {info.get('customer_name')}\n"
                f"📍 Address: {info.get('delivery_address')}\n"
                f"✉️ Email: {info.get('customer_email')}\n"
                f"📞 Phone: {info.get('customer_phone')}\n\n"
                f"Ready to send your verification email? Reply 'confirm' or 'place order'."
            )
        return {"customer_info": info, "response": reply}
    else:
        # State what is still needed
        slot_names_en = {
            "customer_name": "Full Name",
            "customer_email": "Email Address",
            "customer_phone": "Phone Number",
            "delivery_address": "Delivery Address",
        }
        missing_labels = [slot_names_en.get(s, s) for s in missing]
        if lang == "bn":
            reply = f"ধন্যবাদ! অর্ডার চূড়ান্ত করতে এখনও প্রয়োজন: **{', '.join(missing_labels)}**।"
        else:
            reply = f"Got it! We still need your **{', '.join(missing_labels)}** to finalize your order."
        return {"customer_info": info, "response": reply}


def handle_checkout_review(state: AgentState) -> Dict[str, Any]:
    """Generates explicit order recap and creates draft order with email link."""
    user_id = state.get("user_id", "default_user")
    lang = state.get("language", "en")
    cart = OrderService.get_cart(user_id)
    channel = state.get("channel", "telegram")

    if not cart:
        reply = (
            "আপনার কার্ট বর্তমানে খালি। অনুগ্রহ করে কিছু খাবার অর্ডার করুন।"
            if lang == "bn"
            else "Your cart is currently empty. Please select dishes from the menu first!"
        )
        return {"response": reply}

    missing = OrderService.get_missing_slots(user_id)
    if missing:
        slot_names_en = {
            "customer_name": "Full Name",
            "customer_email": "Email Address",
            "customer_phone": "Phone Number",
            "delivery_address": "Delivery Address",
        }
        needed = ", ".join(slot_names_en.get(m, m) for m in missing)
        if lang == "bn":
            reply = f"অর্ডার কনফার্ম করার আগে অনুগ্রহ করে আপনার **{needed}** প্রদান করুন।"
        else:
            reply = f"To finalize your order, please provide your **{needed}**."
        return {"response": reply}

    # All 6 slots verified! Create draft order and send verification email
    success, msg, order = OrderService.create_draft_order(user_id, channel=channel, language=lang)
    if not success or not order:
        return {"response": f"Sorry, could not process order: {msg}"}

    # Dispatch email safely
    email_dispatched = False
    try:
        email_dispatched = EmailService.send_verification_email_sync(order.to_dict(), order.confirmation_token)
    except Exception as e:
        log.exception("Failed to dispatch verification email: %s", e)

    totals = OrderService.calculate_totals(cart)
    cart_lines = "\n".join(f"• {c['quantity']}x {c['name']} (৳{c['line_total']})" for c in cart)

    if lang == "bn":
        reply = (
            f"🎉 **আপনার অর্ডার প্রস্তুত!**\n"
            f"অর্ডার কোড: `{order.order_code}`\n\n"
            f"**খাবারের বিবরণ:**\n{cart_lines}\n"
            f"সাবটোটাল: ৳{totals['subtotal']}\n"
            f"ডেলিভারি চার্জ: ৳{totals['delivery_fee']}\n"
            f"**সর্বমোট বিল: ৳{totals['total_amount']} (ক্যাশ অন ডেলিভারি)**\n\n"
            f"ডেলিভারি ঠিকানা: {order.delivery_address}\n"
            f"ফোন: {order.customer_phone}\n\n"
            f"✉️ আমরা আপনার ইমেইল (`{order.customer_email}`)-এ একটি ভেরিফিকেশন লিংক পাঠিয়েছি।\n"
            f"দয়া করে ইমেইলটি চেক করুন এবং **'Confirm & Place Order'** বাটনে ক্লিক করুন যাতে কিচেন আপনার খাবার প্রস্তুত শুরু করতে পারে!"
        )
    else:
        reply = (
            f"🎉 **Your Order is Ready for Confirmation!**\n"
            f"Order Code: `{order.order_code}`\n\n"
            f"**Order Items:**\n{cart_lines}\n"
            f"Subtotal: ৳{totals['subtotal']}\n"
            f"Delivery Fee: ৳{totals['delivery_fee']}\n"
            f"**Grand Total: ৳{totals['total_amount']} (Cash on Delivery)**\n\n"
            f"Deliver To: {order.delivery_address}\n"
            f"Phone: {order.customer_phone}\n\n"
            f"✉️ We have dispatched a verification email to **{order.customer_email}**.\n"
            f"Please check your inbox and click **'Confirm & Place Order'** so the kitchen can begin preparing your meal immediately!"
        )

    return {
        "order_draft_created": True,
        "confirmation_link_sent": email_dispatched,
        "order_code": order.order_code,
        "response": reply,
    }


def handle_general(state: AgentState) -> Dict[str, Any]:
    """Handles small talk and general queries."""
    lang = state.get("language", "en")
    msg = state.get("user_message", "")
    llm = get_llm(temperature=0.3)

    template = prompts.GENERAL_RESPONSE_PROMPT_BN if lang == "bn" else prompts.GENERAL_RESPONSE_PROMPT_EN
    prompt = template.format(message=msg)
    answer = llm.invoke([HumanMessage(content=prompt)]).content.strip()

    return {"response": answer}
