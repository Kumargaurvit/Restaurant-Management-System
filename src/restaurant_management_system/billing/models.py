from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from restaurant_management_system.db.base import Base


class OrderType(StrEnum):
    DINE_IN = "dine_in"
    TAKEAWAY = "takeaway"
    DELIVERY = "delivery"


class OrderStatus(StrEnum):
    OPEN = "open"
    BILLED = "billed"
    CANCELLED = "cancelled"


class BillStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"


class PaymentMode(StrEnum):
    CASH = "cash"
    UPI = "upi"
    CARD = "card"


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    items: Mapped[list["MenuItem"]] = relationship(back_populates="category")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("menu_categories.id"))
    name: Mapped[str] = mapped_column(String(160))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("5.00"))
    is_available: Mapped[bool] = mapped_column(default=True)

    category: Mapped[MenuCategory] = relationship(back_populates="items")


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    capacity: Mapped[int] = mapped_column(default=2)
    is_active: Mapped[bool] = mapped_column(default=True)


class KitchenTicket(Base):
    __tablename__ = "kitchen_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="kitchen_ticket")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.OPEN.value, index=True)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("restaurant_tables.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(120))
    customer_phone: Mapped[str | None] = mapped_column(String(20))
    delivery_address: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    table: Mapped[RestaurantTable | None] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", order_by="OrderItem.id", cascade="all, delete-orphan"
    )
    bill: Mapped["Bill | None"] = relationship(back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"))
    # Name, price and GST are copied so later menu edits never change an existing order.
    name: Mapped[str] = mapped_column(String(160))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    quantity: Mapped[int]
    notes: Mapped[str | None] = mapped_column(String(300))
    kitchen_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("kitchen_tickets.id"))

    order: Mapped[Order] = relationship(back_populates="items")
    kitchen_ticket: Mapped[KitchenTicket | None] = relationship(back_populates="items")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cgst: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sgst: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    round_off: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default=BillStatus.UNPAID.value, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="bill")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="bill", order_by="Payment.id", cascade="all, delete-orphan"
    )

    @property
    def amount_paid(self) -> Decimal:
        return sum((payment.amount for payment in self.payments), Decimal("0.00"))

    @property
    def amount_due(self) -> Decimal:
        return self.total - self.amount_paid


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"), index=True)
    mode: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bill: Mapped[Bill] = relationship(back_populates="payments")


class InvoiceCounter(Base):
    """One row holding the last used invoice number; locked while a bill is generated."""

    __tablename__ = "invoice_counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_number: Mapped[int] = mapped_column(default=0)
