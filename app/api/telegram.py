"""
Telegram bot entrypoint (polling mode -- simplest for local development).
Run with:  python -m app.api.telegram
"""
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

from app.agent.graph import agent_graph
from app.config import settings
from app.database.database import init_db
from app.utils.logger import get_logger

log = get_logger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "স্বাগতম! Welcome to Dhaka Spice House 🍛\n"
        "Ask me about the menu, place an order, or ask about delivery & policy — "
        "in English or বাংলায়।"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text

    config = {"configurable": {"thread_id": user_id}}
    result = agent_graph.invoke({"user_id": user_id, "user_message": text}, config=config)

    await update.message.reply_text(result.get("response", "Sorry, something went wrong."))


def main():
    init_db()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Telegram bot starting (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
