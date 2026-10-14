"""
Email Service: Generates and dispatches responsive, branded order verification
and marketing campaign emails. Supports async SMTP and local mock file fallback.
"""
import os
import json
import asyncio
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Any, Optional

import aiosmtplib
from jinja2 import Template

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)

VERIFICATION_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Confirm Your Order - {{ restaurant_name }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7f7f9; margin: 0; padding: 20px; color: #2d3748; }
    .container { max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }
    .header { background: linear-gradient(135deg, #e53e3e, #dd6b20); color: #ffffff; padding: 30px 24px; text-align: center; }
    .header h1 { margin: 0 0 6px 0; font-size: 26px; }
    .header p { margin: 0; font-size: 14px; opacity: 0.9; }
    .body { padding: 28px 24px; }
    .recap-box { background: #fdf2f2; border: 1px solid #fed7d7; border-radius: 8px; padding: 16px; margin-bottom: 24px; }
    .items-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
    .items-table th { text-align: left; padding: 10px 8px; border-bottom: 2px solid #edf2f7; font-size: 13px; color: #718096; text-transform: uppercase; }
    .items-table td { padding: 12px 8px; border-bottom: 1px solid #edf2f7; font-size: 14px; }
    .totals-table { width: 100%; margin-top: 10px; margin-bottom: 24px; }
    .totals-table td { padding: 6px 8px; font-size: 14px; }
    .totals-table .grand-total { font-size: 18px; font-weight: bold; color: #c53030; border-top: 2px solid #edf2f7; padding-top: 10px; }
    .cta-container { text-align: center; margin: 32px 0 24px 0; }
    .cta-button { background-color: #38a169; color: #ffffff !important; padding: 16px 36px; font-size: 16px; font-weight: bold; text-decoration: none; border-radius: 8px; display: inline-block; box-shadow: 0 4px 12px rgba(56, 161, 105, 0.35); }
    .cta-button:hover { background-color: #2f855a; }
    .footer { background: #edf2f7; padding: 20px 24px; text-align: center; font-size: 12px; color: #718096; }
    .warning { font-size: 12px; color: #a0aec0; margin-top: 16px; text-align: center; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{{ restaurant_name }}</h1>
      <p>Order Verification & Confirmation</p>
    </div>
    <div class="body">
      <p>Hello <strong>{{ customer_name }}</strong>,</p>
      <p>Thank you for choosing {{ restaurant_name }}! Please review your order details below and click the button to finalize your order with the kitchen.</p>

      <div class="recap-box">
        <strong>Order Code:</strong> {{ order_code }}<br>
        <strong>Delivery Address:</strong> {{ delivery_address }}<br>
        <strong>Contact Phone:</strong> {{ customer_phone }}<br>
        <strong>Payment Method:</strong> Cash on Delivery (৳{{ "%.2f"|format(total_amount) }})
      </div>

      <table class="items-table">
        <thead>
          <tr>
            <th>Item</th>
            <th style="text-align: center;">Qty</th>
            <th style="text-align: right;">Price</th>
            <th style="text-align: right;">Total</th>
          </tr>
        </thead>
        <tbody>
          {% for item in items %}
          <tr>
            <td><strong>{{ item.item_name }}</strong></td>
            <td style="text-align: center;">{{ item.quantity }}</td>
            <td style="text-align: right;">৳{{ "%.2f"|format(item.unit_price) }}</td>
            <td style="text-align: right;">৳{{ "%.2f"|format(item.line_total) }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>

      <table class="totals-table">
        <tr>
          <td>Subtotal:</td>
          <td style="text-align: right;">৳{{ "%.2f"|format(subtotal) }}</td>
        </tr>
        <tr>
          <td>Delivery Fee:</td>
          <td style="text-align: right;">৳{{ "%.2f"|format(delivery_fee) }}</td>
        </tr>
        <tr class="grand-total">
          <td>Grand Total:</td>
          <td style="text-align: right;">৳{{ "%.2f"|format(total_amount) }}</td>
        </tr>
      </table>

      <div class="cta-container">
        <a href="{{ verification_url }}" class="cta-button">✅ Confirm & Place Order</a>
      </div>

      <p class="warning">
        Note: This verification link expires in {{ token_expiry_minutes }} minutes. If you did not place this order, please disregard this email.
      </p>
    </div>
    <div class="footer">
      {{ restaurant_name }} &bull; {{ restaurant_address }} &bull; Tel: {{ restaurant_phone }}
    </div>
  </div>
</body>
</html>
"""


class EmailService:

    @staticmethod
    def render_verification_email(order_dict: Dict[str, Any], token: str) -> str:
        """Renders HTML email content from Jinja2 template."""
        verification_url = f"{settings.server_base_url}/orders/verify?token={token}"
        template = Template(VERIFICATION_EMAIL_TEMPLATE)
        return template.render(
            restaurant_name=settings.restaurant_name,
            restaurant_address=settings.restaurant_address,
            restaurant_phone=settings.restaurant_phone,
            customer_name=order_dict.get("customer_name"),
            customer_phone=order_dict.get("customer_phone"),
            delivery_address=order_dict.get("delivery_address"),
            order_code=order_dict.get("order_code"),
            items=order_dict.get("items", []),
            subtotal=order_dict.get("subtotal", 0.0),
            delivery_fee=order_dict.get("delivery_fee", 60.0),
            total_amount=order_dict.get("total_amount", 0.0),
            token_expiry_minutes=settings.token_expiry_minutes,
            verification_url=verification_url,
        )

    @staticmethod
    async def send_verification_email(order_dict: Dict[str, Any], token: str) -> bool:
        """
        Sends order verification email to the customer.
        Falls back to local file creation if SMTP is unconfigured or in mock mode.
        """
        recipient = order_dict.get("customer_email")
        order_code = order_dict.get("order_code", "UNKNOWN")
        html_content = EmailService.render_verification_email(order_dict, token)
        verification_url = f"{settings.server_base_url}/orders/verify?token={token}"

        # 1. Mock fallback mode or missing SMTP credentials
        if settings.smtp_mock_mode or not settings.smtp_host or not settings.smtp_user:
            Path(settings.emails_dir).mkdir(parents=True, exist_ok=True)
            mock_file = Path(settings.emails_dir) / f"verification_{order_code}.html"
            with open(mock_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            log.info("=" * 70)
            log.info(" [MOCK EMAIL DISPATCHED]")
            log.info(" Recipient: %s", recipient)
            log.info(" Order Code: %s", order_code)
            log.info(" File: %s", mock_file)
            log.info(" Verification Link: %s", verification_url)
            log.info("=" * 70)
            return True

        # 2. Real SMTP dispatch
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Action Required: Confirm Your Order {order_code} - {settings.restaurant_name}"
            msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            msg["To"] = recipient
            msg.set_content(
                f"Hello {order_dict.get('customer_name')},\n\n"
                f"Please confirm your order by visiting: {verification_url}\n\n"
                f"Thank you,\n{settings.restaurant_name}"
            )
            msg.add_alternative(html_content, subtype="html")

            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=settings.smtp_use_tls,
            )
            log.info("Verification email successfully sent to %s for order %s", recipient, order_code)
            return True
        except Exception as e:
            log.exception("Failed to send verification email via SMTP: %s", e)
            return False

    @staticmethod
    def send_verification_email_sync(order_dict: Dict[str, Any], token: str) -> bool:
        """Synchronous wrapper for thread/background execution."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return asyncio.run_coroutine_threadsafe(
                    EmailService.send_verification_email(order_dict, token), loop
                ).result(timeout=10)
            else:
                return loop.run_until_complete(EmailService.send_verification_email(order_dict, token))
        except RuntimeError:
            return asyncio.run(EmailService.send_verification_email(order_dict, token))
