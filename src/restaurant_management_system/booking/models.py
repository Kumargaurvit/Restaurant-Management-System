from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class BookingStatus(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    SEATED = "seated"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


# Bookings in these statuses hold a table; the others free it.
ACTIVE_STATUSES = (
    BookingStatus.REQUESTED.value,
    BookingStatus.CONFIRMED.value,
    BookingStatus.SEATED.value,
)


class BookingSettings(Base):
    """One row: when the restaurant takes bookings. Created with defaults on first use."""

    __tablename__ = "booking_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    opens_at: Mapped[time] = mapped_column(Time)
    closes_at: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int]
    max_party_size: Mapped[int]
    max_days_ahead: Mapped[int]
    reminder_hours_before: Mapped[int]


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    guest_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(10))
    party_size: Mapped[int]
    booking_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    # Copied from the settings when booked, so changing the slot length later does not
    # change bookings that already exist.
    slot_minutes: Mapped[int]
    status: Mapped[str] = mapped_column(
        String(20), default=BookingStatus.REQUESTED.value, index=True
    )
    source: Mapped[str] = mapped_column(String(20), default="staff")
    notes: Mapped[str | None] = mapped_column(String(300))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def end_time(self) -> time:
        total = min(self.start_time.hour * 60 + self.start_time.minute + self.slot_minutes, 24 * 60 - 1)
        return time(total // 60, total % 60)
