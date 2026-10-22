import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.customers.models import Customer


def normalize_phone(raw: str) -> str:
    """Return the 10-digit Indian mobile number, accepting +91, 91 and 0 prefixes."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid 10-digit mobile number"
        )
    return digits


async def get_or_create_customer(
    session: AsyncSession, phone: str, name: str | None
) -> Customer:
    """Find the customer by phone, creating them if new. A name is stored only if none is set."""
    normalized = normalize_phone(phone)
    name = name.strip() if name else None

    customer = await session.scalar(select(Customer).where(Customer.phone == normalized))
    if customer is None:
        customer = Customer(phone=normalized, name=name or None)
        session.add(customer)
        await session.flush()
    elif name and not customer.name:
        customer.name = name
    return customer
