"""
SQLAlchemy 2.0 ORM models for AI Restaurant Agent.
Single Source of Truth for Menu, Orders, Order Items, Customer Leads,
Fulfillment Outbox Jobs, and Persistent Agent Sessions.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Numeric, DateTime, ForeignKey, 
    Text, Boolean, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.database import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, default="Mains")
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "item_code": self.item_code,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "price": float(self.price),
            "is_available": self.is_available,
            "image_url": self.image_url,
        }


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="telegram")
    language: Mapped[str] = mapped_column(String(8), default="en")

    # Customer Details Snapshot
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(254), index=True, nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    special_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Financial Snapshots (Decimal Precision)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("60.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # State Machine & Sub-Statuses
    # Primary: DRAFT | PENDING_EMAIL_CONFIRMATION | CONFIRMED | ACCEPTED_BY_KITCHEN | PREPARING | READY | OUT_FOR_DELIVERY | DELIVERED | EXPIRED | CANCELLED | REQUIRES_MANUAL_REVIEW
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    payment_status: Mapped[str] = mapped_column(String(32), default="PENDING_COD")
    payment_method: Mapped[str] = mapped_column(String(32), default="CASH_ON_DELIVERY")
    email_verification_status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED")
    print_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    sheets_sync_status: Mapped[str] = mapped_column(String(32), default="PENDING")

    # Token Verification
    confirmation_token: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items: Mapped[List["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    jobs: Mapped[List["FulfillmentJob"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_code": self.order_code,
            "user_id": self.user_id,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "customer_phone": self.customer_phone,
            "delivery_address": self.delivery_address,
            "special_notes": self.special_notes,
            "subtotal": float(self.subtotal),
            "delivery_fee": float(self.delivery_fee),
            "discount_amount": float(self.discount_amount),
            "total_amount": float(self.total_amount),
            "status": self.status,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "email_verification_status": self.email_verification_status,
            "print_status": self.print_status,
            "sheets_sync_status": self.sheets_sync_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "items": [item.to_dict() for item in self.items],
        }


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    menu_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("menu_items.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit_price": float(self.unit_price),
            "line_total": float(self.line_total),
        }


class CustomerLead(Base):
    __tablename__ = "customer_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_orders: Mapped[int] = mapped_column(Integer, default=1)
    lifetime_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    first_order_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_order_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)
    unsubscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class FulfillmentJob(Base):
    __tablename__ = "fulfillment_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)  # KITCHEN_PRINT | GSHEETS_SYNC | CUSTOMER_NOTIFY
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)  # PENDING | PROCESSING | SUCCESS | FAILED
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order: Mapped["Order"] = relationship(back_populates="jobs")


class AgentSession(Base):
    """Stores per-user persistent cart and customer slot state across chat turns."""
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en")
    active_cart_json: Mapped[str] = mapped_column(Text, default="[]")
    customer_info_json: Mapped[str] = mapped_column(Text, default="{}")
    last_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
