import re
from datetime import UTC, datetime

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


# Replies that mean "stop marketing me" (WhatsApp chatbot and retention replies).
OPT_OUT_KEYWORDS = {"stop", "unsubscribe", "optout", "opt out", "cancel marketing"}
OPT_IN_KEYWORDS = {"start", "subscribe", "optin", "opt in"}


def is_opt_out_message(text: str) -> bool:
    return re.sub(r"[^\w ]", "", text).strip().lower() in OPT_OUT_KEYWORDS


def is_opt_in_message(text: str) -> bool:
    return re.sub(r"[^\w ]", "", text).strip().lower() in OPT_IN_KEYWORDS


def set_marketing_opt_out(customer: Customer, opt_out: bool, source: str) -> None:
    """Record or clear a marketing opt-out. `source` is e.g. "staff" or "whatsapp"."""
    if customer.marketing_opt_out == opt_out:
        return
    customer.marketing_opt_out = opt_out
    customer.opted_out_at = datetime.now(UTC) if opt_out else None
    customer.opt_out_source = source if opt_out else None


async def can_receive_marketing(session: AsyncSession, phone: str) -> bool:
    """Retention campaigns must check this before sending any marketing message."""
    customer = await session.scalar(select(Customer).where(Customer.phone == normalize_phone(phone)))
    return customer is not None and not customer.marketing_opt_out
