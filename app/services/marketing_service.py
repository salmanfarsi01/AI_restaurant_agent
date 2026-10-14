"""
Marketing Broadcast Service:
Extracts verified customer leads from Google Sheets / Database CRM,
personalizes promotional messages, and broadcasts discount campaigns with rate limiting.
"""
import asyncio
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Any, List, Tuple

import aiosmtplib
from jinja2 import Template

from app.config import settings
from app.services.sheets_service import SheetsService
from app.utils.logger import get_logger

log = get_logger(__name__)

MARKETING_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ subject }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #fdf2f2; margin: 0; padding: 20px; color: #2d3748; }
    .card { max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }
    .header { background: linear-gradient(135deg, #c53030, #e53e3e); color: #fff; padding: 32px 24px; text-align: center; }
    .header h1 { margin: 0 0 8px 0; font-size: 26px; }
    .body { padding: 28px 24px; font-size: 15px; line-height: 1.6; }
    .promo-box { background: #fffaf0; border: 2px dashed #dd6b20; border-radius: 10px; padding: 18px; text-align: center; margin: 24px 0; }
    .promo-code { font-size: 24px; font-weight: bold; color: #c05621; letter-spacing: 2px; }
    .cta-btn { display: inline-block; background: #c53030; color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: bold; margin-top: 16px; }
    .footer { background: #edf2f7; padding: 18px 24px; text-align: center; font-size: 12px; color: #718096; }
    .unsub { color: #a0aec0; text-decoration: underline; font-size: 11px; margin-top: 10px; display: inline-block; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>{{ restaurant_name }}</h1>
      <p style="margin:0; opacity:0.9;">{{ headline }}</p>
    </div>
    <div class="body">
      <p>Hello <strong>{{ name }}</strong>,</p>
      <p>{{ message_body }}</p>

      {% if discount_code %}
      <div class="promo-box">
        <p style="margin:0 0 6px 0; font-size:13px; color:#718096; text-transform:uppercase;">Use Special Promo Code:</p>
        <div class="promo-code">{{ discount_code }}</div>
      </div>
      {% endif %}

      <div style="text-align: center; margin-top: 24px;">
        <a href="{{ cta_url }}" class="cta-btn">{{ cta_text }}</a>
      </div>
    </div>
    <div class="footer">
      {{ restaurant_name }} &bull; {{ restaurant_address }}<br>
      <a href="{{ unsubscribe_url }}" class="unsub">Unsubscribe from promotional emails</a>
    </div>
  </div>
</body>
</html>
"""


class MarketingService:

    @classmethod
    def render_campaign_preview(cls, payload: Dict[str, Any]) -> str:
        """Renders sample promotional email preview."""
        template = Template(MARKETING_EMAIL_TEMPLATE)
        return template.render(
            restaurant_name=settings.restaurant_name,
            restaurant_address=settings.restaurant_address,
            subject=payload.get("subject", "Special Offer!"),
            headline=payload.get("headline", "A Delicious Deal Just For You"),
            name="Valued Customer",
            message_body=payload.get("message_body", "Enjoy discounts on your next delicious meal with us!"),
            discount_code=payload.get("discount_code"),
            cta_text=payload.get("cta_text", "Order Now"),
            cta_url=payload.get("cta_url", "http://localhost:8000"),
            unsubscribe_url=f"{settings.server_base_url}/api/marketing/unsubscribe?email=sample@example.com",
        )

    @classmethod
    async def broadcast_campaign(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends targeted email broadcast to all verified customer leads extracted from Google Sheets.
        Includes rate-limiting (throttling) to avoid spam triggers.
        """
        leads = SheetsService.get_all_leads()
        total_leads = len(leads)
        sent_count = 0
        failed_count = 0

        subject = payload.get("subject", f"Special Discount from {settings.restaurant_name}")
        headline = payload.get("headline", "Limited Time Offer!")
        message_body = payload.get("message_body", "")
        discount_code = payload.get("discount_code", "")
        cta_text = payload.get("cta_text", "Order on Chat Now")
        cta_url = payload.get("cta_url", settings.server_base_url)

        log.info("Starting marketing campaign broadcast to %d leads...", total_leads)
        template = Template(MARKETING_EMAIL_TEMPLATE)

        for lead in leads:
            email = lead.get("email")
            name = lead.get("name") or "Valued Guest"
            if not email:
                continue

            unsub_url = f"{settings.server_base_url}/api/marketing/unsubscribe?email={email}"
            html_body = template.render(
                restaurant_name=settings.restaurant_name,
                restaurant_address=settings.restaurant_address,
                subject=subject,
                headline=headline,
                name=name,
                message_body=message_body,
                discount_code=discount_code,
                cta_text=cta_text,
                cta_url=cta_url,
                unsubscribe_url=unsub_url,
            )

            # 1. Mock file write if SMTP unconfigured
            if settings.smtp_mock_mode or not settings.smtp_host or not settings.smtp_user:
                mock_file = Path(settings.emails_dir) / f"campaign_{email.replace('@', '_at_')}.html"
                with open(mock_file, "w", encoding="utf-8") as f:
                    f.write(html_body)
                sent_count += 1
            else:
                # 2. Live SMTP send
                try:
                    msg = EmailMessage()
                    msg["Subject"] = subject
                    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
                    msg["To"] = email
                    msg.set_content(message_body)
                    msg.add_alternative(html_body, subtype="html")

                    await aiosmtplib.send(
                        msg,
                        hostname=settings.smtp_host,
                        port=settings.smtp_port,
                        username=settings.smtp_user,
                        password=settings.smtp_password,
                        start_tls=settings.smtp_use_tls,
                    )
                    sent_count += 1
                    # Small throttle delay
                    await asyncio.sleep(0.2)
                except Exception as e:
                    failed_count += 1
                    log.warning("Failed to send marketing email to %s: %s", email, e)

        return {
            "total_leads": total_leads,
            "sent": sent_count,
            "failed": failed_count,
            "campaign_subject": subject,
        }
