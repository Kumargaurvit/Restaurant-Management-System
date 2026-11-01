import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.config import Settings, get_settings
from restaurant_management_system.customers.services import (
    get_or_create_customer,
    is_opt_in_message,
    is_opt_out_message,
    normalize_phone,
    set_marketing_opt_out,
)
from restaurant_management_system.db.session import get_session
from restaurant_management_system.messaging.provider import (
    MessageProvider,
    get_provider,
    record_incoming,
    send_message,
)

router = APIRouter(prefix="/api/messaging", tags=["messaging"])


class InboundIn(BaseModel):
    phone: str
    text: str


@router.post("/inbound")
async def inbound_message(
    body: InboundIn,
    x_webhook_secret: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: MessageProvider = Depends(get_provider),
) -> dict[str, str]:
    """Where the WhatsApp provider delivers guest replies.

    Logs every reply (the retention report counts replies to campaigns) and handles
    STOP / START so a guest can opt out of marketing or back in.
    """
    expected = settings.whatsapp_webhook_secret
    if not expected or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")

    phone = normalize_phone(body.phone)
    await record_incoming(session, phone, body.text)

    action = "logged"
    if is_opt_out_message(body.text):
        customer = await get_or_create_customer(session, phone, None)
        set_marketing_opt_out(customer, True, "whatsapp")
        await send_message(
            session,
            provider,
            phone,
            "You will no longer get marketing messages from us. Reply START to opt back in.",
            "chat",
        )
        action = "opted_out"
    elif is_opt_in_message(body.text):
        customer = await get_or_create_customer(session, phone, None)
        set_marketing_opt_out(customer, False, "whatsapp")
        await send_message(
            session, provider, phone, "You are subscribed to our offers again.", "chat"
        )
        action = "opted_in"
    await session.commit()
    return {"action": action}

