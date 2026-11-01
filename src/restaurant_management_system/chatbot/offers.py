from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.chatbot.models import Offer


def aware(moment: datetime | None) -> datetime | None:
    """Timestamps are stored in UTC; some drivers return them without tzinfo."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def offer_status(offer: Offer, now: datetime) -> str:
    if not offer.is_active:
        return "paused"
    start, end = aware(offer.valid_from), aware(offer.valid_until)
    if start is not None and start > now:
        return "upcoming"
    if end is not None and end <= now:
        return "expired"
    return "active"


async def current_offers(
    session: AsyncSession, now: datetime, horizon: timedelta = timedelta(hours=24)
) -> tuple[list[Offer], list[Offer]]:
    """Offers valid right now, and offers that start within the horizon (soonest first)."""
    offers = list(await session.scalars(select(Offer).where(Offer.is_active.is_(True))))
    active = [o for o in offers if offer_status(o, now) == "active"]
    upcoming = [
        o
        for o in offers
        if offer_status(o, now) == "upcoming" and aware(o.valid_from) <= now + horizon
    ]
    upcoming.sort(key=lambda o: aware(o.valid_from))
    return active, upcoming
