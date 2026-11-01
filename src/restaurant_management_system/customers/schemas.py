from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CustomerOut(BaseModel):
    id: int
    phone: str
    name: str | None
    visits: int
    total_spent: Decimal
    first_visit: datetime | None
    last_visit: datetime | None
    is_returning: bool
    marketing_opt_out: bool
    opted_out_at: datetime | None


class MarketingOptOutIn(BaseModel):
    opt_out: bool


class CustomerLookupOut(BaseModel):
    """What staff may see while taking an order: no spend or history."""

    id: int
    phone: str
    name: str | None
    visits: int
    is_returning: bool


class TopDishOut(BaseModel):
    menu_item_id: int
    name: str
    quantity: int
    orders: int
    revenue: Decimal


class OrderedItemOut(BaseModel):
    name: str
    quantity: int


class CustomerOrderOut(BaseModel):
    order_id: int
    invoice_number: str
    billed_at: datetime
    order_type: str
    bill_status: str
    total: Decimal
    items: list[OrderedItemOut]


class CustomerDetailOut(CustomerOut):
    favourite_dishes: list[TopDishOut]
    orders: list[CustomerOrderOut]
