"""
Telegram Bot Entrypoint for AI Restaurant Agent (Ignite Order @IgniteOrderBot).
Supports natural bilingual chat, interactive menus, quick-action keyboards,
cart management, and direct email confirmation links.

Run with: python -m app.api.telegram
"""
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    ContextTypes, filters
)

from app.agent.graph import agent_graph
from app.config import settings
from app.database.database import init_db, SessionLocal
from app.database.models import Order
from app.database.seed_menu import seed_menu
from app.services.order_service import OrderService
from app.utils.logger import get_logger

log = get_logger(__name__)

# Standard Quick Action Keyboard for Telegram Customers
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🍛 Biryani & Mains"), KeyboardButton("🍢 Kebabs & Grills")],
        [KeyboardButton("🍗 Wings & Snacks"), KeyboardButton("🥤 Drinks & Desserts")],
        [KeyboardButton("🛒 My Cart"), KeyboardButton("✅ Place Order")],
    ],
    resize_keyboard=True,
)


async def send_safe_message(update: Update, text: str, reply_markup=None):
    """Sends message with Markdown parsing, safely falling back to plain text if syntax fails."""
    try:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        await update.message.reply_text(text, reply_markup=reply_markup)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command: greets customer and presents quick-action buttons."""
    user_id = str(update.effective_user.id)
    config = {"configurable": {"thread_id": user_id}}
    result = agent_graph.invoke(
        {"user_id": user_id, "user_message": "/start", "channel": "telegram"},
        config=config,
    )
    welcome_msg = result.get("response", f"Welcome to {settings.restaurant_name}!")
    await send_safe_message(update, welcome_msg, reply_markup=MAIN_KEYBOARD)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /menu command: displays all categories and dishes with prices."""
    menu_by_cat = OrderService.get_menu_by_category()
    lines = [f"🍽️ *{settings.restaurant_name} - Food Menu*\n"]
    for cat, items in menu_by_cat.items():
        lines.append(f"*{cat}*")
        for item in items:
            lines.append(f"• *{item['name']}* — ৳{item['price']:.2f}\n  _{item['description']}_")
        lines.append("")

    lines.append("💡 _To order, just type what you want, e.g.: 'I want 2 Kachchi Biryani and 1 Borhani'_")
    await send_safe_message(update, "\n".join(lines), reply_markup=MAIN_KEYBOARD)


async def cart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /cart command: shows current cart items and totals."""
    user_id = str(update.effective_user.id)
    cart = OrderService.get_cart(user_id)
    if not cart:
        await send_safe_message(
            update,
            "🛒 *Your cart is currently empty.*\nUse the menu buttons below to choose your favorite dishes!",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    totals = OrderService.calculate_totals(cart)
    cart_lines = "\n".join(f"• {c['quantity']}x *{c['name']}* @ ৳{c['unit_price']:.2f} = ৳{c['line_total']:.2f}" for c in cart)
    missing = OrderService.get_missing_slots(user_id)

    missing_text = ""
    if missing:
        slot_labels = {
            "customer_name": "Full Name",
            "customer_email": "Email Address",
            "customer_phone": "Phone Number",
            "delivery_address": "Delivery Address",
        }
        needed = [slot_labels.get(m, m) for m in missing]
        missing_text = f"\n\n⚠️ *Still needed for delivery:* {', '.join(needed)}"

    msg = (
        f"🛒 *Your Current Cart:*\n{cart_lines}\n"
        f"------------------------------------\n"
        f"Subtotal: ৳{totals['subtotal']:.2f}\n"
        f"Delivery Fee: ৳{totals['delivery_fee']:.2f}\n"
        f"*Grand Total: ৳{totals['total_amount']:.2f} (Cash on Delivery)*"
        f"{missing_text}\n\n"
        f"Tap *✅ Place Order* or reply with your delivery details to confirm!"
    )
    await send_safe_message(update, msg, reply_markup=MAIN_KEYBOARD)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /clear command: empties customer's cart."""
    user_id = str(update.effective_user.id)
    OrderService.clear_cart(user_id)
    await send_safe_message(update, "🗑️ Your cart has been cleared.", reply_markup=MAIN_KEYBOARD)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help command."""
    help_text = (
        f"🍛 *How to Order at {settings.restaurant_name}:*\n\n"
        f"1. *Browse Menu*: Tap the category buttons below or type `/menu`.\n"
        f"2. *Add Dishes*: Simply tell me what you want, like _'2 Kachchi Biryani and 1 Borhani'_.\n"
        f"3. *Provide Delivery Info*: Tell me your Name, Email, Phone, and Address.\n"
        f"4. *Email Verification*: We'll send a confirmation link to your email to verify.\n"
        f"5. *Kitchen Prep*: Once confirmed, the kitchen prints your order ticket immediately!\n\n"
        f"Commands:\n"
        f"• `/menu` - View full categorized menu\n"
        f"• `/cart` - View current items\n"
        f"• `/clear` - Empty your cart\n"
        f"• `/help` - Show instructions"
    )
    await send_safe_message(update, help_text, reply_markup=MAIN_KEYBOARD)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all freeform conversational customer messages."""
    user_id = str(update.effective_user.id)
    text = (update.message.text or "").strip()

    # Route quick button clicks
    lower = text.lower()
    if lower == "🛒 my cart":
        return await cart_command(update, context)
    elif lower in ("✅ place order", "checkout", "confirm order"):
        text = "confirm order"
    elif "biryani & mains" in lower:
        text = "Show me the biryani and main dishes"
    elif "kebabs & grills" in lower:
        text = "Show me the kebabs and grills"
    elif "wings & snacks" in lower:
        text = "What wings and appetizers do you have?"
    elif "drinks & desserts" in lower:
        text = "What drinks and desserts do you serve?"

    try:
        config = {"configurable": {"thread_id": user_id}}
        result = agent_graph.invoke(
            {"user_id": user_id, "user_message": text, "channel": "telegram"},
            config=config,
        )
        reply_text = result.get("response", "Sorry, I had trouble processing that. Please try again.")

        # Check if an order was just created and needs confirmation
        inline_markup = None
        order_code = result.get("order_code")
        if order_code:
            db = SessionLocal()
            try:
                order = db.query(Order).filter(Order.order_code == order_code).first()
                if order and order.confirmation_token:
                    verify_url = f"{settings.server_base_url}/orders/verify?token={order.confirmation_token}"
                    inline_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Review & Confirm Order", url=verify_url)]
                    ])
            finally:
                db.close()

        await send_safe_message(update, reply_text, reply_markup=inline_markup or MAIN_KEYBOARD)
    except Exception as e:
        log.exception("Error processing message '%s' from user %s: %s", text, user_id, e)
        err_msg = "⚠️ An error occurred while processing your request. Please try again or type /cart."
        await send_safe_message(update, err_msg, reply_markup=MAIN_KEYBOARD)


def main():
    """Initializes database, seeds menu, and starts Telegram polling listener."""
    init_db()
    seed_menu()

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    log.info("Starting Telegram bot for %s...", settings.restaurant_name)
    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("cart", cart_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("help", help_command))

    # Register freeform text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Telegram bot (@IgniteOrderBot) is now running and polling for messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
