from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.booking import schemas, services
from restaurant_management_system.booking.models import Booking
from restaurant_management_system.config import Settings, get_settings
from restaurant_management_system.db.session import get_session
from restaurant_management_system.messaging.provider import MessageProvider, get_provider
from restaurant_management_system.restaurant.services import FALLBACK_NAME, get_restaurant_name

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

STAFF = (Role.OWNER, Role.MANAGER, Role.CASHIER, Role.WAITER)
MANAGERS = (Role.OWNER, Role.MANAGER)


@router.get(
    "/settings",
    response_model=schemas.BookingSettingsOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def read_settings(session: AsyncSession = Depends(get_session)):
    row = await services.get_settings_row(session)
    await session.commit()
    return row


@router.put(
    "/settings",
    response_model=schemas.BookingSettingsOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def update_settings(
    body: schemas.BookingSettingsIn, session: AsyncSession = Depends(get_session)
):
    row = await services.get_settings_row(session)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    await session.commit()
    return row


@router.get(
    "/availability",
    response_model=schemas.AvailabilityOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def check_availability(
    booking_date: date,
    party_size: int = Query(ge=1),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> schemas.AvailabilityOut:
    row = await services.get_settings_row(session)
    slots = await services.availability(session, row, booking_date, party_size, settings.timezone)
    await session.commit()
    return schemas.AvailabilityOut(
        booking_date=booking_date,
        party_size=party_size,
        slots=[schemas.SlotOut(start_time=start, available=free) for start, free in slots],
    )


@router.get(
    "",
    response_model=list[schemas.BookingOut],
    dependencies=[Depends(require_roles(*STAFF))],
)
async def list_bookings(
    booking_date: date | None = None,
    booking_status: str | None = Query(default=None, alias="status"),
    upcoming: bool = False,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[Booking]:
    query = select(Booking).order_by(Booking.booking_date, Booking.start_time, Booking.id)
    if booking_date:
        query = query.where(Booking.booking_date == booking_date)
    if upcoming:
        query = query.where(Booking.booking_date >= services.local_now(settings.timezone).date())
    if booking_status:
        query = query.where(Booking.status == booking_status)
    return list(await session.scalars(query))


@router.post(
    "",
    response_model=schemas.BookingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def create_booking(
    body: schemas.BookingIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Booking:
    booking = await services.create_booking(
        session,
        guest_name=body.guest_name,
        phone=body.phone,
        party_size=body.party_size,
        day=body.booking_date,
        start=body.start_time,
        notes=body.notes,
        source="staff",
        zone_name=settings.timezone,
    )
    await session.commit()
    return booking


@router.post(
    "/{booking_id}/status",
    response_model=schemas.BookingOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def update_status(
    booking_id: int,
    body: schemas.StatusIn,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: MessageProvider = Depends(get_provider),
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    await services.change_status(
        session,
        provider,
        booking,
        body.status.value,
        await get_restaurant_name(session) or FALLBACK_NAME,
    )
    await session.commit()
    return booking


@router.post(
    "/send-reminders",
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def send_reminders(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    provider: MessageProvider = Depends(get_provider),
) -> dict[str, int]:
    """Normally run by the scheduler; this lets the owner trigger it by hand."""
    sent = await services.send_due_reminders(
        session,
        provider,
        settings.timezone,
        await get_restaurant_name(session) or FALLBACK_NAME,
    )
    await session.commit()
    return {"sent": sent}
