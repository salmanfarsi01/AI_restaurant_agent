"""
Order API Endpoints: Safe Two-Phase Email Verification & Confirmation.
GET /orders/verify (Safe landing page - NO state changes)
POST /api/orders/confirm (Explicit confirmation action - Atomic state change)
POST /api/orders/resend-verification (Recovery for expired links)
"""
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from app.config import settings
from app.services.order_service import OrderService
from app.services.email_service import EmailService
from app.services.worker_dispatcher import WorkerDispatcher
from app.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["Orders & Verification"])

VERIFY_PAGE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Review & Confirm Order - {{ order.order_code }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 24px; color: #1a202c; }
    .card { max-width: 540px; margin: 30px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.08); overflow: hidden; }
    .header { background: linear-gradient(135deg, #c53030, #dd6b20); color: #fff; padding: 28px 24px; text-align: center; }
    .header h2 { margin: 0 0 6px 0; font-size: 24px; }
    .content { padding: 28px 24px; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; background: #feebc8; color: #7b341e; }
    .section-title { font-size: 13px; text-transform: uppercase; color: #718096; letter-spacing: 0.5px; margin: 20px 0 8px 0; font-weight: 600; }
    .box { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; margin-bottom: 16px; font-size: 14px; line-height: 1.6; }
    .item-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #edf2f7; font-size: 14px; }
    .total-row { display: flex; justify-content: space-between; padding: 14px 0 0 0; font-size: 18px; font-weight: bold; color: #c53030; }
    .confirm-btn { width: 100%; background: #38a169; color: #ffffff; border: none; padding: 16px; font-size: 16px; font-weight: bold; border-radius: 10px; cursor: pointer; margin-top: 24px; box-shadow: 0 4px 14px rgba(56,161,105,0.4); transition: background 0.2s; }
    .confirm-btn:hover { background: #2f855a; }
    .footer { text-align: center; font-size: 12px; color: #a0aec0; margin-top: 24px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h2>{{ restaurant_name }}</h2>
      <p style="margin:0; opacity:0.9;">Review Your Order Before Placing</p>
    </div>
    <div class="content">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:15px; font-weight:600;">Order: {{ order.order_code }}</span>
        <span class="badge">{{ order.status }}</span>
      </div>

      <div class="section-title">Delivery Details</div>
      <div class="box">
        <strong>Customer:</strong> {{ order.customer_name }}<br>
        <strong>Phone:</strong> {{ order.customer_phone }}<br>
        <strong>Address:</strong> {{ order.delivery_address }}<br>
        <strong>Payment:</strong> Cash on Delivery (৳{{ "%.2f"|format(order.total_amount) }})
      </div>

      <div class="section-title">Order Items</div>
      <div class="box">
        {% for item in items %}
        <div class="item-row">
          <span>{{ item.quantity }}x {{ item.item_name }}</span>
          <span>৳{{ "%.2f"|format(item.line_total) }}</span>
        </div>
        {% endfor %}
        <div class="item-row" style="color:#718096; font-size:13px;">
          <span>Delivery Fee</span>
          <span>৳{{ "%.2f"|format(order.delivery_fee) }}</span>
        </div>
        <div class="total-row">
          <span>Total To Pay</span>
          <span>৳{{ "%.2f"|format(order.total_amount) }}</span>
        </div>
      </div>

      <!-- Explicit POST Form: Protects against email crawler scanners! -->
      <form method="POST" action="/api/orders/confirm">
        <input type="hidden" name="token" value="{{ token }}" />
        <button type="submit" class="confirm-btn">✅ Confirm Order Now</button>
      </form>
    </div>
    <div class="footer">
      Dhaka Spice House &bull; Banani, Dhaka &bull; +880 1700-000000
    </div>
  </div>
</body>
</html>
"""

CONFIRMED_SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Order Confirmed! - {{ order.order_code }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0fdf4; margin: 0; padding: 24px; color: #1a202c; }
    .card { max-width: 520px; margin: 40px auto; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); padding: 36px 28px; text-align: center; }
    .icon { font-size: 56px; margin-bottom: 16px; }
    h2 { color: #276749; margin: 0 0 12px 0; font-size: 26px; }
    p { font-size: 15px; color: #4a5568; line-height: 1.6; }
    .details { background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; text-align: left; margin: 24px 0; font-size: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🎉</div>
    <h2>Thank You For Your Order!</h2>
    <p>Your order <strong>{{ order.order_code }}</strong> has been verified and sent directly to the kitchen for preparation.</p>
    
    <div class="details">
      <strong>Order Code:</strong> {{ order.order_code }}<br>
      <strong>Customer:</strong> {{ order.customer_name }}<br>
      <strong>Deliver To:</strong> {{ order.delivery_address }}<br>
      <strong>Total Bill:</strong> ৳{{ "%.2f"|format(order.total_amount) }} (Cash on Delivery)<br>
      <strong>Estimated Delivery Time:</strong> 35 - 45 minutes
    </div>

    <p style="font-size: 13px; color: #718096;">
      Our kitchen printer has printed your ticket and our chefs have started preparing your meal!
    </p>
  </div>
</body>
</html>
"""


@router.get("/orders/verify", response_class=HTMLResponse)
def verify_landing_page(token: str):
    """
    Step 1 of Anti-Scanner Email Verification.
    Safe GET endpoint: Only displays the interactive confirmation page.
    PERFORMS ZERO DATABASE MUTATIONS (Bots crawling this link will never trigger orders).
    """
    order = OrderService.get_order_for_verification(token)
    if not order:
        return HTMLResponse(
            "<h3>Invalid or Expired Link</h3><p>This verification link is invalid or has already been used.</p>",
            status_code=400,
        )

    if order["status"] == "CONFIRMED":
        from jinja2 import Template
        return HTMLResponse(
            Template(CONFIRMED_SUCCESS_HTML).render(order=order, restaurant_name=settings.restaurant_name)
        )

    from jinja2 import Template
    html = Template(VERIFY_PAGE_HTML).render(
        order=order,
        items=order.get("items", []),
        token=token,
        restaurant_name=settings.restaurant_name,
    )
    return HTMLResponse(html)


@router.post("/api/orders/confirm")
async def confirm_order(request: Request, token: Optional[str] = Form(None)):
    """
    Step 2 of Anti-Scanner Verification.
    Explicit POST action executed when customer clicks [Confirm Order Now].
    Transitions state to CONFIRMED and enqueues fulfillment jobs.
    """
    if not token:
        # Check JSON payload if form is not present
        try:
            body = await request.json()
            token = body.get("token")
        except Exception:
            token = None

    if not token:
        raise HTTPException(status_code=400, detail="Missing verification token.")

    success, msg, order_dict = OrderService.confirm_order_by_token(token)
    if not success or not order_dict:
        return HTMLResponse(f"<h3>Verification Error</h3><p>{msg}</p>", status_code=400)

    # Immediately trigger decoupled fulfillment worker in background
    WorkerDispatcher.dispatch_pending_jobs()

    # If requested by browser HTML form, return confirmation page
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header:
        from jinja2 import Template
        return HTMLResponse(
            Template(CONFIRMED_SUCCESS_HTML).render(order=order_dict, restaurant_name=settings.restaurant_name)
        )

    return JSONResponse({
        "status": "success",
        "message": msg,
        "order": order_dict,
    })
