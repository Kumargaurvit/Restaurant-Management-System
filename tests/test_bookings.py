from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from restaurant_management_system.booking.models import Booking
from restaurant_management_system.booking.services import overlaps, parties_fit
from restaurant_management_system.messaging.models import Message
from restaurant_management_system.messaging.provider import get_provider

API = "/api/bookings"
TOMORROW = (datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(days=1)).date()


class FakeProvider:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone: str, body: str) -> bool:
        self.sent.append((phone, body))
        return True


@pytest.fixture
def provider(client: AsyncClient) -> FakeProvider:
    fake = FakeProvider()
    client._transport.app.dependency_overrides[get_provider] = lambda: fake
    return fake


def booking_body(**overrides) -> dict:
    body = {
        "guest_name": "Neha",
        "phone": "9876543210",
        "party_size": 2,
        "booking_date": TOMORROW.isoformat(),
        "start_time": "12:30:00",
    }
    return {**body, **overrides}


# ------------------------------------------------------------ pure logic


def test_parties_fit_assigns_smallest_table_that_fits() -> None:
    assert parties_fit([2, 4], [2, 4])
    assert parties_fit([4, 4], [2, 3])
    assert not parties_fit([4], [2, 2])  # seats are not pooled across parties
    assert not parties_fit([2, 2], [3])


def test_overlap_of_slots() -> None:
    assert overlaps(time(12, 0), 90, time(13, 0), 90)
    assert not overlaps(time(12, 0), 90, time(13, 30), 90)  # back to back is fine


# ------------------------------------------------------------- settings


async def test_settings_have_defaults_and_managers_can_change_them(
    client: AsyncClient, owner_headers
) -> None:
    current = (await client.get(f"{API}/settings", headers=owner_headers)).json()
    assert current["slot_minutes"] == 90

    changed = {**current, "slot_minutes": 60, "opens_at": "10:00:00"}
    response = await client.put(f"{API}/settings", headers=owner_headers, json=changed)
    assert response.json()["slot_minutes"] == 60

    bad = {**current, "opens_at": "23:00:00", "closes_at": "11:00:00"}
    assert (await client.put(f"{API}/settings", headers=owner_headers, json=bad)).status_code == 422


async def test_waiter_cannot_change_settings(client: AsyncClient, owner_headers, make_staff) -> None:
    waiter = await make_staff("waiter")
    current = (await client.get(f"{API}/settings", headers=waiter)).json()
    assert (await client.put(f"{API}/settings", headers=waiter, json=current)).status_code == 403


# --------------------------------------------------------- availability


async def test_availability_lists_slots_and_drops_full_ones(
    client: AsyncClient, menu, owner_headers
) -> None:
    url = f"{API}/availability?booking_date={TOMORROW}&party_size=4"
    slots = (await client.get(url, headers=owner_headers)).json()["slots"]
    assert slots[0]["start_time"] == "11:00:00"
    assert all(slot["available"] for slot in slots)

    # The only table seats 4, so one booking fills its slot.
    await client.post(API, headers=owner_headers, json=booking_body(party_size=4))
    slots = (await client.get(url, headers=owner_headers)).json()["slots"]
    by_start = {slot["start_time"]: slot["available"] for slot in slots}
    assert by_start["12:30:00"] is False
    assert by_start["11:00:00"] is True


async def test_party_larger_than_any_table_is_unavailable(
    client: AsyncClient, menu, owner_headers
) -> None:
    url = f"{API}/availability?booking_date={TOMORROW}&party_size=6"
    slots = (await client.get(url, headers=owner_headers)).json()["slots"]
    assert not any(slot["available"] for slot in slots)


# -------------------------------------------------------------- booking


async def test_create_booking_links_customer_and_starts_requested(
    client: AsyncClient, menu, owner_headers
) -> None:
    response = await client.post(API, headers=owner_headers, json=booking_body(phone="+91 98765 43210"))

    assert response.status_code == 201
    booking = response.json()
    assert booking["status"] == "requested"
    assert booking["phone"] == "9876543210"
    assert booking["end_time"] == "14:00:00"
    customers = (await client.get("/api/customers", headers=owner_headers)).json()
    assert [c["phone"] for c in customers] == ["9876543210"]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"start_time": "12:45:00"}, 422),  # not a slot start
        ({"start_time": "22:00:00"}, 422),  # slot would end after closing
        ({"booking_date": "2020-01-01"}, 422),  # in the past
        ({"party_size": 13}, 422),  # above the party limit
        ({"phone": "123"}, 422),
        ({"party_size": 6}, 409),  # fits no table
    ],
)
async def test_invalid_bookings_are_rejected(
    client: AsyncClient, menu, owner_headers, overrides, code
) -> None:
    response = await client.post(API, headers=owner_headers, json=booking_body(**overrides))
    assert response.status_code == code


async def test_booking_beyond_the_booking_window_is_rejected(
    client: AsyncClient, menu, owner_headers
) -> None:
    far = (TOMORROW + timedelta(days=60)).isoformat()
    response = await client.post(API, headers=owner_headers, json=booking_body(booking_date=far))
    assert response.status_code == 422


async def test_double_booking_the_only_table_is_rejected(
    client: AsyncClient, menu, owner_headers
) -> None:
    first = await client.post(API, headers=owner_headers, json=booking_body(party_size=4))
    second = await client.post(API, headers=owner_headers, json=booking_body(party_size=2))
    other_slot = await client.post(
        API, headers=owner_headers, json=booking_body(start_time="14:00:00")
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert other_slot.status_code == 201


async def test_cancelling_frees_the_slot(client: AsyncClient, menu, owner_headers, provider) -> None:
    first = (await client.post(API, headers=owner_headers, json=booking_body())).json()
    await client.post(f"{API}/{first['id']}/status", headers=owner_headers, json={"status": "cancelled"})

    again = await client.post(API, headers=owner_headers, json=booking_body(guest_name="Ravi"))
    assert again.status_code == 201


async def test_list_filters_by_date_and_status(client: AsyncClient, menu, owner_headers) -> None:
    await client.post(API, headers=owner_headers, json=booking_body())
    await client.post(
        API,
        headers=owner_headers,
        json=booking_body(booking_date=(TOMORROW + timedelta(days=1)).isoformat()),
    )

    on_day = (await client.get(f"{API}?booking_date={TOMORROW}", headers=owner_headers)).json()
    confirmed = (await client.get(f"{API}?status=confirmed", headers=owner_headers)).json()

    assert len(on_day) == 1
    assert confirmed == []


# --------------------------------------------------------------- status


async def test_confirming_sends_a_message_and_follows_the_lifecycle(
    client: AsyncClient, menu, owner_headers, provider: FakeProvider
) -> None:
    booking = (await client.post(API, headers=owner_headers, json=booking_body())).json()
    url = f"{API}/{booking['id']}/status"

    confirmed = await client.post(url, headers=owner_headers, json={"status": "confirmed"})
    assert confirmed.json()["status"] == "confirmed"
    assert len(provider.sent) == 1
    assert provider.sent[0][0] == "9876543210"
    assert "confirmed" in provider.sent[0][1]

    for step in ("seated", "completed"):
        response = await client.post(url, headers=owner_headers, json={"status": step})
        assert response.json()["status"] == step


async def test_invalid_status_change_is_rejected(
    client: AsyncClient, menu, owner_headers, provider
) -> None:
    booking = (await client.post(API, headers=owner_headers, json=booking_body())).json()
    url = f"{API}/{booking['id']}/status"

    assert (await client.post(url, headers=owner_headers, json={"status": "seated"})).status_code == 409
    await client.post(url, headers=owner_headers, json={"status": "cancelled"})
    assert (await client.post(url, headers=owner_headers, json={"status": "confirmed"})).status_code == 409


async def test_unknown_booking_is_404(client: AsyncClient, owner_headers) -> None:
    response = await client.post(f"{API}/999/status", headers=owner_headers, json={"status": "confirmed"})
    assert response.status_code == 404


# ------------------------------------------------------------ reminders


async def test_reminders_go_once_to_confirmed_bookings_starting_soon(
    client: AsyncClient, menu, owner_headers, provider: FakeProvider, engine: AsyncEngine
) -> None:
    soon = await client.post(API, headers=owner_headers, json=booking_body(party_size=1))
    soon_id = soon.json()["id"]
    await client.post(f"{API}/{soon_id}/status", headers=owner_headers, json={"status": "confirmed"})
    provider.sent.clear()

    # Move it to one hour from now (in the restaurant's timezone).
    starts = datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(hours=1)
    async with async_sessionmaker(engine)() as session:
        await session.execute(
            update(Booking)
            .where(Booking.id == soon_id)
            .values(booking_date=starts.date(), start_time=starts.time().replace(second=0, microsecond=0, tzinfo=None))
        )
        await session.commit()

    first = await client.post(f"{API}/send-reminders", headers=owner_headers)
    second = await client.post(f"{API}/send-reminders", headers=owner_headers)

    assert first.json() == {"sent": 1}
    assert second.json() == {"sent": 0}
    assert "Reminder" in provider.sent[0][1]
    async with async_sessionmaker(engine)() as session:
        kinds = list(await session.scalars(select(Message.kind)))
    assert kinds == ["booking", "reminder"]


async def test_no_reminder_for_a_booking_days_away(
    client: AsyncClient, menu, owner_headers, provider: FakeProvider
) -> None:
    booking = (await client.post(API, headers=owner_headers, json=booking_body())).json()
    await client.post(f"{API}/{booking['id']}/status", headers=owner_headers, json={"status": "confirmed"})
    provider.sent.clear()

    result = await client.post(f"{API}/send-reminders", headers=owner_headers)

    assert result.json() == {"sent": 0}
    assert provider.sent == []


async def test_bookings_require_login(client: AsyncClient) -> None:
    assert (await client.get(API)).status_code == 401
