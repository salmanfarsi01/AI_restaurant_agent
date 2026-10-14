"""
Notification Service: Dispatches real-time order acknowledgments
back to the customer's chat channel (Telegram / Web Chat).
"""
import asyncio
from typing import Dict, Any

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class NotificationService:

    @staticmethod
    def notify_order_confirmed(order: Dict[str, Any]) -> bool:
        """Pushes confirmation message to the customer's active chat session."""
        user_id = order.get("user_id")
        order_code = order.get("order_code")
        lang = order.get("language", "en")

        if lang == "bn":
            msg = (
                f"✅ **আপনার অর্ডার নিশ্চিত করা হয়েছে!**\n\n"
                f"অর্ডার কোড: `{order_code}`\n"
                f"আমাদের কিচেন টিকিট প্রিন্ট হয়েছে এবং খাবার প্রস্তুত করা শুরু হয়েছে।\n"
                f"সম্ভাব্য ডেলিভারি সময়: ৩৫ - ৪৫ মিনিট।\n\n"
                f"ঢাকা স্পাইস হাউসের সাথে থাকার জন্য ধন্যবাদ! 🍛"
            )
        else:
            msg = (
                f"✅ **Your Order is Confirmed!**\n\n"
                f"Order Code: `{order_code}`\n"
                f"Our kitchen POS printer has received your order and our chefs have started preparing it.\n"
                f"Estimated delivery time: 35 - 45 minutes.\n\n"
                f"Thank you for choosing Dhaka Spice House! 🍛"
            )

        # Telegram delivery if configured
        if settings.telegram_bot_token and user_id and user_id.isdigit():
            try:
                from telegram import Bot
                bot = Bot(token=settings.telegram_bot_token)
                asyncio.run(bot.send_message(chat_id=int(user_id), text=msg, parse_mode="Markdown"))
                log.info("Telegram notification sent to %s for order %s", user_id, order_code)
                return True
            except Exception as e:
                log.warning("Could not dispatch Telegram push notification: %s", e)

        log.info("Chat Notification ready for user %s: %s", user_id, msg[:80])
        return True
