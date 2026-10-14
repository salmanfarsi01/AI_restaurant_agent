"""
Comprehensive Integration Tests for AI Restaurant Agent:
- Menu catalog and decimal pricing
- Persistent session cart & slot filling
- Two-phase anti-scanner email verification
- Idempotent confirmation
- Decoupled fulfillment workers (POS receipt printing & Sheets daily logging)
- Marketing campaign broadcast
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database.database import init_db, SessionLocal
from app.database.models import MenuItem, Order, FulfillmentJob, CustomerLead
from app.database.seed_menu import seed_menu
from app.services.order_service import OrderService
from app.services.worker_dispatcher import WorkerDispatcher
from app.services.marketing_service import MarketingService


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()
    seed_menu()


@pytest.fixture
def client():
    return TestClient(app)


def test_menu_seeded():
    db = SessionLocal()
    try:
        count = db.query(MenuItem).count()
        assert count >= 10, f"Expected at least 10 dishes, found {count}"
        biryani = db.query(MenuItem).filter(MenuItem.name.ilike("%kachchi%")).first()
        assert biryani is not None
        assert float(biryani.price) > 0
    finally:
        db.close()


def test_chat_greeting(client):
    res = client.post("/chat", json={"user_id": "test_guest_1", "message": "hi"})
    assert res.status_code == 200
    data = res.json()
    assert "Dhaka Spice House" in data["response"]
    assert "Biryani & Mains" in data["response"]


def test_cart_operations():
    user_id = "test_user_cart"
    OrderService.clear_cart(user_id)

    # 1. Add item
    ok, msg, cart = OrderService.add_to_cart(user_id, "Kachchi Biryani", quantity=2)
    assert ok is True
    assert len(cart) == 1
    assert cart[0]["quantity"] == 2

    # 2. Add second item
    ok, msg, cart = OrderService.add_to_cart(user_id, "Special Borhani", quantity=1)
    assert ok is True
    assert len(cart) == 2

    # 3. Check totals
    totals = OrderService.calculate_totals(cart)
    # 2 * 350 + 1 * 90 = 790 subtotal + 60 delivery = 850
    assert float(totals["subtotal"]) == 790.00
    assert float(totals["total_amount"]) == 850.00


def test_end_to_end_order_and_anti_scanner_verification(client):
    user_id = "e2e_customer_99"
    OrderService.clear_cart(user_id)

    # Step 1: Add dish to cart
    OrderService.add_to_cart(user_id, "Kachchi Biryani (Mutton)", quantity=2)

    # Step 2: Provide customer info
    OrderService.update_customer_info(user_id, {
        "customer_name": "Tariqul Islam",
        "customer_email": "tariqul@example.com",
        "customer_phone": "01755112233",
        "delivery_address": "House 15, Road 7, Sector 4, Uttara, Dhaka",
    })

    # Step 3: Verify missing slots are now satisfied
    missing = OrderService.get_missing_slots(user_id)
    assert len(missing) == 0, f"Expected 0 missing slots, got {missing}"

    # Step 4: Create draft order
    ok, msg, order = OrderService.create_draft_order(user_id, channel="web", language="en")
    assert ok is True
    assert order is not None
    assert order.status == "PENDING_EMAIL_CONFIRMATION"
    token = order.confirmation_token
    assert token is not None

    # Step 5: ANTI-SCANNER TEST - Crawler hits GET /orders/verify
    # State MUST NOT change to CONFIRMED!
    get_res = client.get(f"/orders/verify?token={token}")
    assert get_res.status_code == 200
    assert "Review Your Order Before Placing" in get_res.text

    db = SessionLocal()
    try:
        check_order = db.query(Order).filter(Order.confirmation_token == token).first()
        assert check_order.status == "PENDING_EMAIL_CONFIRMATION", "Security violation: GET request changed order state!"
    finally:
        db.close()

    # Step 6: Customer clicks [Confirm Order Now] -> POST /api/orders/confirm
    post_res = client.post("/api/orders/confirm", data={"token": token}, headers={"Accept": "text/html"})
    assert post_res.status_code == 200
    assert "Thank You For Your Order!" in post_res.text

    db = SessionLocal()
    try:
        confirmed_order = db.query(Order).filter(Order.confirmation_token == token).first()
        assert confirmed_order.status == "CONFIRMED"
        assert confirmed_order.email_verification_status == "VERIFIED"

        # Check that fulfillment jobs were enqueued
        jobs = db.query(FulfillmentJob).filter(FulfillmentJob.order_id == confirmed_order.id).all()
        job_types = {j.job_type for j in jobs}
        assert "KITCHEN_PRINT" in job_types
        assert "GSHEETS_SYNC" in job_types
        assert "CUSTOMER_NOTIFY" in job_types
    finally:
        db.close()

    # Step 7: IDEMPOTENCY TEST - Repeated POST request
    repeat_res = client.post("/api/orders/confirm", data={"token": token}, headers={"Accept": "text/html"})
    assert repeat_res.status_code == 200
    assert "Thank You For Your Order!" in repeat_res.text


def test_decoupled_worker_execution():
    # Insert a test print job into fulfillment_jobs
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.status == "CONFIRMED").first()
        assert order is not None
        job = FulfillmentJob(order_id=order.id, job_type="KITCHEN_PRINT", status="PENDING")
        db.add(job)
        db.commit()
    finally:
        db.close()

    # Dispatch pending fulfillment jobs
    summary = WorkerDispatcher.dispatch_pending_jobs()
    assert summary["processed"] >= 1
    assert summary["succeeded"] >= 1


def test_marketing_broadcast_endpoint(client):
    payload = {
        "subject": "Weekend Delight: 20% OFF Biryani!",
        "headline": "Special Treat for Foodies",
        "message_body": "Use coupon code FEAST20 to get 20% off all Biryanis this weekend.",
        "discount_code": "FEAST20",
        "cta_text": "Order on Chat Now",
        "cta_url": "http://localhost:8000",
    }

    # 1. Unauthorized request should fail
    unauth_res = client.post("/api/marketing/broadcast", json=payload)
    assert unauth_res.status_code == 401

    # 2. Authorized request should succeed
    auth_res = client.post(
        "/api/marketing/broadcast",
        json=payload,
        headers={"X-Admin-Api-Key": settings.admin_api_key},
    )
    assert auth_res.status_code == 200
    data = auth_res.json()
    assert data["status"] == "success"
    assert data["details"]["sent"] >= 1
