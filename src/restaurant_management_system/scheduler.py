import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from restaurant_management_system.booking.services import send_due_reminders
from restaurant_management_system.config import get_settings
from restaurant_management_system.db.session import get_sessionmaker
from restaurant_management_system.messaging.provider import build_provider
from restaurant_management_system.restaurant.services import FALLBACK_NAME, get_restaurant_name
from restaurant_management_system.retention.services import run_rules

logger = logging.getLogger(__name__)


async def _booking_reminders() -> None:
    settings = get_settings()
    try:
        async with get_sessionmaker()() as session:
            await send_due_reminders(
                session,
                build_provider(settings),
                settings.timezone,
                await get_restaurant_name(session) or FALLBACK_NAME,
            )
            await session.commit()
    except Exception:  # noqa: BLE001 - a failed run must not stop the scheduler
        logger.exception("Booking reminder job failed")


async def _retention_campaigns() -> None:
    """Sends automatic rules; approval rules wait for the owner to run them or approve."""
    settings = get_settings()
    try:
        async with get_sessionmaker()() as session:
            await run_rules(
                session,
                build_provider(settings),
                await get_restaurant_name(session) or FALLBACK_NAME,
                automatic_only=True,
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Retention campaign job failed")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=get_settings().timezone)
    scheduler.add_job(_booking_reminders, "interval", minutes=10, id="booking_reminders")
    scheduler.add_job(_retention_campaigns, "cron", hour=11, minute=0, id="retention_campaigns")
    return scheduler
