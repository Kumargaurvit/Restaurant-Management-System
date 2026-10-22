from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from restaurant_management_system.billing.models import OrderType, PaymentMode


class ORMModel(BaseModel):
    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class CategoryOut(ORMModel):
    id: int
    name: str
    sort_order: int


class MenuItemCreate(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    gst_rate: Decimal = Field(default=Decimal("5.00"), ge=0, le=28)


class MenuItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    gst_rate: Decimal | None = Field(default=None, ge=0, le=28)
    is_available: bool | None = None


class MenuItemOut(ORMModel):
    id: int
    category_id: int
    name: str
    price: Decimal
    gst_rate: Decimal
    is_available: bool


class TableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    capacity: int = Field(default=2, ge=1, le=50)


class TableOut(ORMModel):
    id: int
    name: str
    capacity: int
    is_active: bool


class OrderCreate(BaseModel):
    order_type: OrderType
    table_id: int | None = None
    customer_name: str | None = Field(default=None, max_length=120)
    customer_phone: str | None = Field(default=None, max_length=20)
    delivery_address: str | None = Field(default=None, max_length=500)


class OrderCustomerSet(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=120)


class OrderItemAdd(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=300)


class OrderItemUpdate(BaseModel):
    quantity: int = Field(ge=0, le=100)


class OrderItemOut(ORMModel):
    id: int
    menu_item_id: int
    name: str
    unit_price: Decimal
    gst_rate: Decimal
    quantity: int
    notes: str | None
    kitchen_ticket_id: int | None


class OrderOut(ORMModel):
    id: int
    order_type: str
    status: str
    table_id: int | None
    customer_id: int | None
    customer_name: str | None
    customer_phone: str | None
    delivery_address: str | None
    created_at: datetime
    items: list[OrderItemOut]


class KitchenTicketOut(ORMModel):
    id: int
    order_id: int
    created_at: datetime
    items: list[OrderItemOut]


class BillCreate(BaseModel):
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class PaymentCreate(BaseModel):
    mode: PaymentMode
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reference: str | None = Field(default=None, max_length=120)


class PaymentOut(ORMModel):
    id: int
    mode: str
    amount: Decimal
    reference: str | None
    created_at: datetime


class BillOut(ORMModel):
    id: int
    invoice_number: str
    order_id: int
    subtotal: Decimal
    discount: Decimal
    cgst: Decimal
    sgst: Decimal
    round_off: Decimal
    total: Decimal
    status: str
    created_at: datetime
    payments: list[PaymentOut]
    amount_paid: Decimal
    amount_due: Decimal


class DailySalesOut(BaseModel):
    day: date
    bill_count: int
    total_sales: Decimal
    cash: Decimal
    upi: Decimal
    card: Decimal
