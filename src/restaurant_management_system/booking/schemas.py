from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from restaurant_management_system.booking.models import BookingStatus


class BookingSettingsIn(BaseModel):
    opens_at: time
    closes_at: time
    slot_minutes: int = Field(ge=15, le=480)
    max_party_size: int = Field(ge=1, le=100)
    max_days_ahead: int = Field(ge=1, le=365)
    reminder_hours_before: int = Field(ge=1, le=48)

    @model_validator(mode="after")
    def _opens_before_closes(self) -> "BookingSettingsIn":
        if self.closes_at <= self.opens_at:
            raise ValueError("Closing time must be after opening time")
        return self


class BookingSettingsOut(BookingSettingsIn):
    model_config = ConfigDict(from_attributes=True)


class BookingIn(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)
    phone: str
    party_size: int = Field(ge=1)
    booking_date: date
    start_time: time
    notes: str | None = Field(default=None, max_length=300)


class StatusIn(BaseModel):
    status: BookingStatus


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guest_name: str
    phone: str
    party_size: int
    booking_date: date
    start_time: time
    end_time: time
    slot_minutes: int
    status: str
    source: str
    notes: str | None
    created_at: datetime


class SlotOut(BaseModel):
    start_time: time
    available: bool


class AvailabilityOut(BaseModel):
    booking_date: date
    party_size: int
    slots: list[SlotOut]
