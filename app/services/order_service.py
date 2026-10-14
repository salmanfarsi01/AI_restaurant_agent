"""
Transactional Order Service: Single source of truth for Menu, Cart,
Slot Validation, Pricing, and Order State Machine Transitions.
"""
import re
import json
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Tuple, Any

from app.config import settings
from app.database.database import SessionLocal
from app.database.models import (
    MenuItem, Order, OrderItem, CustomerLead, FulfillmentJob, AgentSession
)
from app.utils.logger import get_logger

log = get_logger(__name__)

# Permissive international name regex: supports English, Bangla, accents, spaces, hyphens, apostrophes
NAME_REGEX = re.compile(r"^[\w\s\-\.'`\u0980-\u09FF]{2,100}$", re.UNICODE)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-()]{7,20}$")


class OrderService:

    # -------------------------------------------------------------------------
    # Menu & Item Resolution
    # -------------------------------------------------------------------------
    @staticmethod
    def get_menu_by_category() -> Dict[str, List[Dict[str, Any]]]:
        """Returns all available menu items grouped by category."""
        db = SessionLocal()
        try:
            items = db.query(MenuItem).filter(MenuItem.is_available == True).all()
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for item in items:
                grouped.setdefault(item.category, []).append(item.to_dict())
            return grouped
        finally:
            db.close()

    @staticmethod
    def find_menu_item(query: str) -> Optional[MenuItem]:
        """Fuzzy-matches a dish name against the database menu catalog."""
        clean_query = query.strip().lower()
        if not clean_query:
            return None
        db = SessionLocal()
        try:
            # 1. Exact match on name
            item = db.query(MenuItem).filter(MenuItem.name.ilike(clean_query)).first()
            if item:
                return item

            # 2. Substring match
            items = db.query(MenuItem).filter(MenuItem.is_available == True).all()
            for it in items:
                if clean_query in it.name.lower() or it.name.lower() in clean_query:
                    return it

            # 3. Token-based overlap
            q_words = set(clean_query.split())
            best_match = None
            max_overlap = 0
            for it in items:
                name_words = set(it.name.lower().split())
                overlap = len(q_words & name_words)
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_match = it

            if max_overlap >= 1:
                return best_match

            return None
        finally:
            db.close()

    # -------------------------------------------------------------------------
    # Persistent Session & Cart
    # -------------------------------------------------------------------------
    @staticmethod
    def get_session(user_id: str) -> AgentSession:
        db = SessionLocal()
        try:
            session = db.query(AgentSession).filter(AgentSession.user_id == user_id).first()
            if not session:
                session = AgentSession(
                    user_id=user_id,
                    active_cart_json="[]",
                    customer_info_json="{}",
                )
                db.add(session)
                db.commit()
                db.refresh(session)
            return session
        finally:
            db.close()

    @staticmethod
    def get_cart(user_id: str) -> List[Dict[str, Any]]:
        session = OrderService.get_session(user_id)
        try:
            return json.loads(session.active_cart_json) or []
        except Exception:
            return []

    @staticmethod
    def update_cart(user_id: str, cart: List[Dict[str, Any]]) -> None:
        db = SessionLocal()
        try:
            session = db.query(AgentSession).filter(AgentSession.user_id == user_id).first()
            if not session:
                session = AgentSession(user_id=user_id)
                db.add(session)
            session.active_cart_json = json.dumps(cart, ensure_ascii=False)
            session.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()

    @staticmethod
    def add_to_cart(user_id: str, item_name: str, quantity: int = 1) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Adds an item to the persistent cart with live price snapshot from DB."""
        menu_item = OrderService.find_menu_item(item_name)
        if not menu_item:
            return False, f"Sorry, '{item_name}' is not currently on our menu.", OrderService.get_cart(user_id)

        cart = OrderService.get_cart(user_id)
        found = False
        for c in cart:
            if c["item_id"] == menu_item.id:
                c["quantity"] += quantity
                found = True
                break

        if not found:
            cart.append({
                "item_id": menu_item.id,
                "name": menu_item.name,
                "quantity": quantity,
                "unit_price": float(menu_item.price),
                "line_total": float(menu_item.price * quantity),
            })

        # Recalculate line totals
        for c in cart:
            c["line_total"] = round(c["unit_price"] * c["quantity"], 2)

        OrderService.update_cart(user_id, cart)
        return True, f"Added {quantity}x {menu_item.name} (৳{menu_item.price} each) to your cart.", cart

    @staticmethod
    def modify_cart_item(user_id: str, item_name: str, quantity: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Sets an exact quantity or removes an item if quantity <= 0."""
        cart = OrderService.get_cart(user_id)
        updated = []
        target_name = item_name.lower().strip()
        found = False

        for c in cart:
            if target_name in c["name"].lower() or c["name"].lower() in target_name:
                found = True
                if quantity > 0:
                    c["quantity"] = quantity
                    c["line_total"] = round(c["unit_price"] * quantity, 2)
                    updated.append(c)
            else:
                updated.append(c)

        if not found:
            return False, f"Item matching '{item_name}' was not found in your cart.", cart

        OrderService.update_cart(user_id, updated)
        msg = f"Updated '{item_name}' quantity to {quantity}." if quantity > 0 else f"Removed '{item_name}' from cart."
        return True, msg, updated

    @staticmethod
    def clear_cart(user_id: str) -> None:
        OrderService.update_cart(user_id, [])

    # -------------------------------------------------------------------------
    # Customer Details & Slot Filling
    # -------------------------------------------------------------------------
    @staticmethod
    def get_customer_info(user_id: str) -> Dict[str, Any]:
        session = OrderService.get_session(user_id)
        try:
            return json.loads(session.customer_info_json) or {}
        except Exception:
            return {}

    @staticmethod
    def update_customer_info(user_id: str, new_info: Dict[str, Any]) -> Dict[str, Any]:
        info = OrderService.get_customer_info(user_id)
        for k, v in new_info.items():
            if v:
                info[k] = str(v).strip()

        db = SessionLocal()
        try:
            session = db.query(AgentSession).filter(AgentSession.user_id == user_id).first()
            if session:
                session.customer_info_json = json.dumps(info, ensure_ascii=False)
                session.updated_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
        return info

    @staticmethod
    def validate_customer_info(info: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
        """Validates the customer details slots. Returns (is_valid, errors_dict)."""
        errors = {}
        name = info.get("customer_name") or info.get("full_name") or ""
        email = info.get("customer_email") or info.get("email") or ""
        phone = info.get("customer_phone") or info.get("phone") or ""
        address = info.get("delivery_address") or info.get("exact_location") or ""

        if not name:
            errors["customer_name"] = "Full name is missing."
        elif not NAME_REGEX.match(name.strip()):
            errors["customer_name"] = "Full name must be at least 2 characters."

        if not email:
            errors["customer_email"] = "Email address is missing."
        elif not EMAIL_REGEX.match(email.strip()):
            errors["customer_email"] = "Invalid email format. Please provide a valid email (e.g. name@example.com)."

        if not phone:
            errors["customer_phone"] = "Phone number is missing."
        elif not PHONE_REGEX.match(phone.strip()):
            errors["customer_phone"] = "Invalid phone number format."

        if not address or len(address.strip()) < 5:
            errors["delivery_address"] = "Delivery address is missing or too brief. Please provide house/road/area details."

        return (len(errors) == 0), errors

    @staticmethod
    def get_missing_slots(user_id: str) -> List[str]:
        """Returns list of missing requirements needed to finalize an order."""
        missing = []
        cart = OrderService.get_cart(user_id)
        if not cart:
            missing.append("items")

        info = OrderService.get_customer_info(user_id)
        if not (info.get("customer_name") or info.get("full_name")):
            missing.append("customer_name")
        if not (info.get("customer_email") or info.get("email")):
            missing.append("customer_email")
        if not (info.get("customer_phone") or info.get("phone")):
            missing.append("customer_phone")
        if not (info.get("delivery_address") or info.get("exact_location")):
            missing.append("delivery_address")
        return missing

    # -------------------------------------------------------------------------
    # Pricing & Order Creation
    # -------------------------------------------------------------------------
    @staticmethod
    def calculate_totals(cart: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        subtotal = Decimal("0.00")
        for item in cart:
            qty = Decimal(str(item["quantity"]))
            unit = Decimal(str(item["unit_price"]))
            subtotal += (qty * unit)
        delivery_fee = Decimal(str(settings.delivery_fee))
        discount = Decimal("0.00")
        total = subtotal + delivery_fee - discount
        return {
            "subtotal": subtotal.quantize(Decimal("0.01")),
            "delivery_fee": delivery_fee.quantize(Decimal("0.01")),
            "discount_amount": discount.quantize(Decimal("0.01")),
            "total_amount": total.quantize(Decimal("0.01")),
        }

    @staticmethod
    def create_draft_order(
        user_id: str, channel: str = "telegram", language: str = "en"
    ) -> Tuple[bool, str, Optional[Order]]:
        """Creates an order in PENDING_EMAIL_CONFIRMATION status with secure token."""
        missing = OrderService.get_missing_slots(user_id)
        if missing:
            return False, f"Cannot place order yet. Missing: {', '.join(missing)}", None

        cart = OrderService.get_cart(user_id)
        info = OrderService.get_customer_info(user_id)
        is_valid, errors = OrderService.validate_customer_info(info)
        if not is_valid:
            return False, f"Validation error: {list(errors.values())[0]}", None

        totals = OrderService.calculate_totals(cart)
        token = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(minutes=settings.token_expiry_minutes)

        db = SessionLocal()
        try:
            # Generate readable order code
            today_str = datetime.utcnow().strftime("%Y%m%d")
            rand_suffix = secrets.token_hex(2).upper()
            order_code = f"ORD-{today_str}-{rand_suffix}"

            order = Order(
                order_code=order_code,
                user_id=user_id,
                channel=channel,
                language=language,
                customer_name=info.get("customer_name") or info.get("full_name"),
                customer_email=(info.get("customer_email") or info.get("email")).lower(),
                customer_phone=info.get("customer_phone") or info.get("phone"),
                delivery_address=info.get("delivery_address") or info.get("exact_location"),
                special_notes=info.get("special_notes"),
                subtotal=totals["subtotal"],
                delivery_fee=totals["delivery_fee"],
                discount_amount=totals["discount_amount"],
                total_amount=totals["total_amount"],
                status="PENDING_EMAIL_CONFIRMATION",
                payment_status="PENDING_COD",
                payment_method="CASH_ON_DELIVERY",
                email_verification_status="UNVERIFIED",
                print_status="PENDING",
                sheets_sync_status="PENDING",
                confirmation_token=token,
                token_expires_at=expiry,
            )
            db.add(order)
            db.flush()

            # Add OrderItems with frozen prices
            for c in cart:
                order_item = OrderItem(
                    order_id=order.id,
                    menu_item_id=c.get("item_id"),
                    item_name=c["name"],
                    quantity=c["quantity"],
                    unit_price=Decimal(str(c["unit_price"])),
                    line_total=Decimal(str(c["line_total"])),
                )
                db.add(order_item)

            db.commit()
            db.refresh(order)
            log.info("Created pending order %s (id=%d) for %s", order.order_code, order.id, order.customer_email)
            return True, "Order draft created successfully.", order
        except Exception as e:
            db.rollback()
            log.exception("Failed to create order draft: %s", e)
            return False, f"Internal error creating order: {e}", None
        finally:
            db.close()

    # -------------------------------------------------------------------------
    # Email Confirmation & Outbox Enqueue (Idempotent)
    # -------------------------------------------------------------------------
    @staticmethod
    def confirm_order_by_token(token: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates token, ensures idempotency, transitions order to CONFIRMED,
        and enqueues decoupled fulfillment jobs (Print, Sheets, Notification).
        """
        if not token:
            return False, "Invalid or missing token.", None

        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.confirmation_token == token).first()
            if not order:
                return False, "Order verification link is invalid or already consumed.", None

            # Check if already confirmed (Idempotency guarantee!)
            if order.status == "CONFIRMED":
                return True, "Your order is already confirmed and is currently being prepared!", order.to_dict()

            # Check expiration
            if order.token_expires_at and datetime.utcnow() > order.token_expires_at:
                order.status = "EXPIRED"
                order.email_verification_status = "EXPIRED"
                db.commit()
                return False, "This verification link has expired (45-minute limit). You can request a new link.", None

            # Transition to CONFIRMED
            order.status = "CONFIRMED"
            order.email_verification_status = "VERIFIED"
            order.confirmed_at = datetime.utcnow()

            # Enqueue independent fulfillment jobs
            jobs = [
                FulfillmentJob(order_id=order.id, job_type="KITCHEN_PRINT"),
                FulfillmentJob(order_id=order.id, job_type="GSHEETS_SYNC"),
                FulfillmentJob(order_id=order.id, job_type="CUSTOMER_NOTIFY"),
            ]
            db.add_all(jobs)

            # Update / Upsert Customer Lead in database
            lead = db.query(CustomerLead).filter(CustomerLead.email == order.customer_email).first()
            if lead:
                lead.total_orders += 1
                lead.lifetime_spend += order.total_amount
                lead.last_order_date = datetime.utcnow()
                lead.full_name = order.customer_name
                lead.phone = order.customer_phone
                lead.delivery_address = order.delivery_address
            else:
                lead = CustomerLead(
                    email=order.customer_email,
                    full_name=order.customer_name,
                    phone=order.customer_phone,
                    delivery_address=order.delivery_address,
                    total_orders=1,
                    lifetime_spend=order.total_amount,
                )
                db.add(lead)

            # Clear customer's active cart in session
            session = db.query(AgentSession).filter(AgentSession.user_id == order.user_id).first()
            if session:
                session.active_cart_json = "[]"
                session.last_order_id = order.id

            db.commit()
            db.refresh(order)
            log.info("Order %s successfully CONFIRMED via email verification.", order.order_code)
            return True, "Thank you for your order! It is now confirmed and being prepared.", order.to_dict()
        except Exception as e:
            db.rollback()
            log.exception("Error confirming order: %s", e)
            return False, f"Internal error during confirmation: {e}", None
        finally:
            db.close()

    @staticmethod
    def get_order_for_verification(token: str) -> Optional[Dict[str, Any]]:
        """Fetches order for GET /orders/verify landing page WITHOUT changing state."""
        db = SessionLocal()
        try:
            order = db.query(Order).filter(Order.confirmation_token == token).first()
            if not order:
                return None
            return order.to_dict()
        finally:
            db.close()
