import logging
from typing import Protocol

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.config import Settings, get_settings
from restaurant_management_system.messaging.models import Message

logger = logging.getLogger(__name__)


class MessageProvider(Protocol):
    """A WhatsApp provider. Implement `send` and return True when the message was accepted."""

    async def send(self, phone: str, body: str) -> bool: ...


class LogProvider:
    """Default provider: writes the message to the log instead of sending it."""

    async def send(self, phone: str, body: str) -> bool:
        logger.info("WhatsApp to %s: %s", phone, body)
        return True


def build_provider(settings: Settings) -> MessageProvider:
    if settings.whatsapp_provider == "log":
        return LogProvider()
    raise ValueError(f"Unknown WHATSAPP_PROVIDER: {settings.whatsapp_provider!r}")


def get_provider(settings: Settings = Depends(get_settings)) -> MessageProvider:
    return build_provider(settings)


async def send_message(
    session: AsyncSession,
    provider: MessageProvider,
    phone: str,
    body: str,
    kind: str,
) -> Message:
    """Send through the provider and log the outcome. Never raises on a provider failure."""
    try:
        sent = await provider.send(phone, body)
    except Exception:  # noqa: BLE001 - a provider outage must not break the caller
        logger.exception("Sending WhatsApp message to %s failed", phone)
        sent = False
    message = Message(
        phone=phone, direction="out", kind=kind, body=body, status="sent" if sent else "failed"
    )
    session.add(message)
    await session.flush()
    return message


async def record_incoming(session: AsyncSession, phone: str, body: str) -> Message:
    message = Message(phone=phone, direction="in", kind="chat", body=body)
    session.add(message)
    await session.flush()
    return message
