from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.billing.models import RestaurantTable
from restaurant_management_system.booking.models import (
    ACTIVE_STATUSES,
    Booking,
    BookingSettings,
    BookingStatus,
)
from restaurant_management_system.customers.services import (
    get_or_create_customer,
    normalize_phone,
)
from restaurant_management_system.messaging.provider import MessageProvider, send_message

# What each status may move to. Completed, no-show and cancelled are final.
TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.REQUESTED.value: {"confirmed", "cancelled"},
    BookingStatus.CONFIRMED.value: {"seated", "no_show", "cancelled"},
    BookingStatus.SEATED.value: {"completed"},
    BookingStatus.COMPLETED.value: set(),
    BookingStatus.NO_SHOW.value: set(),
    BookingStatus.CANCELLED.value: set(),
}


def _minutes(moment: time) -> int:
    return moment.hour * 60 + moment.minute


def overlaps(start_a: time, minutes_a: int, start_b: time, minutes_b: int) -> bool:
    a, b = _minutes(start_a), _minutes(start_b)
    return a < b + minutes_b and b < a + minutes_a


def parties_fit(capacities: list[int], parties: list[int]) -> bool:
    """Can every party get its own table? Biggest party first, smallest table that fits."""
    free = sorted(capacities)
    for party in sorted(parties, reverse=True):
        for index, capacity in enumerate(free):
            if capacity >= party:
                del free[index]
                break
        else:
            return False
    return True


async def get_settings_row(session: AsyncSession) -> BookingSettings:
    row = await session.scalar(select(BookingSettings))
    if row is None:
        row = BookingSettings(
            opens_at=time(11, 0),
            closes_at=time(23, 0),
            slot_minutes=90,
            max_party_size=12,
            max_days_ahead=30,
            reminder_hours_before=3,
        )
        session.add(row)
        await session.flush()
    return row


def slot_starts(settings: BookingSettings) -> list[time]:
    """Start times from opening, one slot apart, while the whole slot ends by closing."""
    starts = []
    minute = _minutes(settings.opens_at)
    while minute + settings.slot_minutes <= _minutes(settings.closes_at):
        starts.append(time(minute // 60, minute % 60))
        minute += settings.slot_minutes
    return starts


async def is_available(
    session: AsyncSession, settings: BookingSettings, day: date, start: time, party_size: int
) -> bool:
    capacities = list(
        await session.scalars(
            select(RestaurantTable.capacity).where(RestaurantTable.is_active.is_(True))
        )
    )
    bookings = await session.scalars(
        select(Booking).where(Booking.booking_date == day, Booking.status.in_(ACTIVE_STATUSES))
    )
    parties = [
        booking.party_size
        for booking in bookings
        if overlaps(booking.start_time, booking.slot_minutes, start, settings.slot_minutes)
    ]
    return parties_fit(capacities, [*parties, party_size])


def local_now(zone_name: str) -> datetime:
    return datetime.now(UTC).astimezone(ZoneInfo(zone_name))


def _has_passed(day: date, start: time, now: datetime) -> bool:
    return day == now.date() and start <= now.time().replace(tzinfo=None)


async def availability(
    session: AsyncSession, settings: BookingSettings, day: date, party_size: int, zone_name: str
) -> list[tuple[time, bool]]:
    now = local_now(zone_name)
    result = []
    for start in slot_starts(settings):
        free = not _has_passed(day, start, now) and await is_available(
            session, settings, day, start, party_size
        )
        result.append((start, free))
    return result


async def create_booking(
    session: AsyncSession,
    *,
    guest_name: str,
    phone: str,
    party_size: int,
    day: date,
    start: time,
    notes: str | None,
    source: str,
    zone_name: str,
) -> Booking:
    settings = await get_settings_row(session)
    normalized = normalize_phone(phone)
    now = local_now(zone_name)
    start = start.replace(second=0, microsecond=0)

    if party_size > settings.max_party_size:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Bookings are for up to {settings.max_party_size} guests. Larger groups need a call.",
        )
    if day < now.date() or day > now.date() + timedelta(days=settings.max_days_ahead):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Bookings open from today up to {settings.max_days_ahead} days ahead.",
        )
    if start not in slot_starts(settings):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That time is not a bookable slot start."
        )
    if _has_passed(day, start, now):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That time has already passed.")
    if not await is_available(session, settings, day, start, party_size):
        raise HTTPException(status.HTTP_409_CONFLICT, "No table is free for that slot.")

    customer = await get_or_create_customer(session, normalized, guest_name)
    booking = Booking(
        customer_id=customer.id,
        guest_name=guest_name.strip(),
        phone=normalized,
        party_size=party_size,
        booking_date=day,
        start_time=start,
        slot_minutes=settings.slot_minutes,
        notes=notes,
        source=source,
    )
    session.add(booking)
    await session.flush()
    return booking


def _when(booking: Booking) -> str:
    return f"{booking.booking_date.strftime('%d %b %Y')} at {booking.start_time.strftime('%H:%M')}"


def confirmation_text(booking: Booking, restaurant: str) -> str:
    return (
        f"Hi {booking.guest_name}, your table for {booking.party_size} at {restaurant} is "
        f"confirmed for {_when(booking)}."
    )


def reminder_text(booking: Booking, restaurant: str) -> str:
    return (
        f"Reminder: your table for {booking.party_size} at {restaurant} is booked for "
        f"{_when(booking)}. See you soon!"
    )


def cancellation_text(booking: Booking, restaurant: str) -> str:
    return (
        f"Hi {booking.guest_name}, your booking at {restaurant} for {_when(booking)} "
        f"has been cancelled."
    )


async def change_status(
    session: AsyncSession,
    provider: MessageProvider,
    booking: Booking,
    new_status: str,
    restaurant: str,
) -> Booking:
    if new_status not in TRANSITIONS[booking.status]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A {booking.status.replace('_', ' ')} booking cannot become "
            f"{new_status.replace('_', ' ')}.",
        )
    booking.status = new_status
    # Booking messages are service messages, so the marketing opt-out does not apply to them.
    if new_status == "confirmed":
        await send_message(
            session, provider, booking.phone, confirmation_text(booking, restaurant), "booking"
        )
    elif new_status == "cancelled":
        await send_message(
            session, provider, booking.phone, cancellation_text(booking, restaurant), "booking"
        )
    return booking


async def send_due_reminders(
    session: AsyncSession, provider: MessageProvider, zone_name: str, restaurant: str
) -> int:
    """Remind guests of confirmed bookings starting within the reminder window."""
    settings = await get_settings_row(session)
    zone = ZoneInfo(zone_name)
    now = datetime.now(UTC).astimezone(zone)
    horizon = now + timedelta(hours=settings.reminder_hours_before)

    bookings = await session.scalars(
        select(Booking).where(
            Booking.status == BookingStatus.CONFIRMED.value,
            Booking.reminder_sent_at.is_(None),
            Booking.booking_date >= now.date(),
            Booking.booking_date <= horizon.date(),
        )
    )
    count = 0
    for booking in bookings:
        starts = datetime.combine(booking.booking_date, booking.start_time, tzinfo=zone)
        if now < starts <= horizon:
            await send_message(
                session, provider, booking.phone, reminder_text(booking, restaurant), "reminder"
            )
            booking.reminder_sent_at = datetime.now(UTC)
            count += 1
    return count
