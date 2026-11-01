from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from restaurant_management_system.chatbot.models import Offer
from restaurant_management_system.chatbot.offers import offer_status

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def iso(delta_hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=delta_hours)).isoformat()


async def create(client: AsyncClient, headers, **fields) -> dict:
    body = {"title": "Lunch deal", "description": "On all mains", "discount_percent": "15", **fields}
    response = await client.post("/api/offers", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------- status


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, "active"),
        ({"valid_from": NOW - timedelta(hours=1), "valid_until": NOW + timedelta(hours=1)}, "active"),
        ({"valid_from": NOW + timedelta(minutes=1)}, "upcoming"),
        ({"valid_until": NOW - timedelta(seconds=1)}, "expired"),
        ({"valid_until": NOW}, "expired"),
        ({"valid_from": NOW}, "active"),
        ({"is_active": False}, "paused"),
        ({"is_active": False, "valid_until": NOW - timedelta(days=1)}, "paused"),
    ],
)
def test_offer_status(kwargs, expected) -> None:
    offer = Offer(title="x", description="", is_active=kwargs.pop("is_active", True), **kwargs)

    assert offer_status(offer, NOW) == expected


def test_naive_datetimes_from_the_database_are_treated_as_utc() -> None:
    offer = Offer(title="x", description="", is_active=True, valid_until=datetime(2026, 10, 22, 11, 0))

    assert offer_status(offer, NOW) == "expired"


# ------------------------------------------------------------------ API


async def test_manager_can_create_and_list_offers(client: AsyncClient, owner_headers) -> None:
    created = await create(client, owner_headers)

    listed = (await client.get("/api/offers", headers=owner_headers)).json()

    assert [o["id"] for o in listed] == [created["id"]]
    assert created["status"] == "active"
    assert created["discount_percent"] == "15.00"


async def test_offer_without_a_discount_percent_is_allowed(client: AsyncClient, owner_headers) -> None:
    offer = await create(client, owner_headers, title="Free dessert", discount_percent=None)

    assert offer["discount_percent"] is None


@pytest.mark.parametrize("percent", ["-1", "100.5", "abc"])
async def test_invalid_discount_percent_is_rejected(client: AsyncClient, owner_headers, percent) -> None:
    response = await client.post(
        "/api/offers", headers=owner_headers, json={"title": "x", "discount_percent": percent}
    )

    assert response.status_code == 422


async def test_end_must_be_after_start(client: AsyncClient, owner_headers) -> None:
    response = await client.post(
        "/api/offers",
        headers=owner_headers,
        json={"title": "x", "valid_from": iso(2), "valid_until": iso(1)},
    )

    assert response.status_code == 422


async def test_title_is_required(client: AsyncClient, owner_headers) -> None:
    assert (await client.post("/api/offers", headers=owner_headers, json={"title": ""})).status_code == 422


async def test_status_reflects_the_time_window(client: AsyncClient, owner_headers) -> None:
    await create(client, owner_headers, title="Now", valid_until=iso(2))
    await create(client, owner_headers, title="Later", valid_from=iso(2))
    await create(client, owner_headers, title="Paused", is_active=False)

    offers = {o["title"]: o["status"] for o in (await client.get("/api/offers", headers=owner_headers)).json()}

    assert offers == {"Now": "active", "Later": "upcoming", "Paused": "paused"}


async def test_offer_can_be_updated(client: AsyncClient, owner_headers) -> None:
    offer = await create(client, owner_headers)

    response = await client.put(
        f"/api/offers/{offer['id']}",
        headers=owner_headers,
        json={"title": "Dinner deal", "discount_percent": "10", "is_active": False},
    )

    body = response.json()
    assert (body["title"], body["discount_percent"], body["status"]) == ("Dinner deal", "10.00", "paused")


async def test_offer_can_be_deleted(client: AsyncClient, owner_headers) -> None:
    offer = await create(client, owner_headers)

    assert (await client.delete(f"/api/offers/{offer['id']}", headers=owner_headers)).status_code == 204
    assert (await client.get("/api/offers", headers=owner_headers)).json() == []


async def test_missing_offer_returns_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.put("/api/offers/9", headers=owner_headers, json={"title": "x"})).status_code == 404
    assert (await client.delete("/api/offers/9", headers=owner_headers)).status_code == 404


async def test_waiter_cannot_manage_offers(client: AsyncClient, make_staff) -> None:
    waiter = await make_staff("waiter")

    assert (await client.get("/api/offers", headers=waiter)).status_code == 403
    assert (await client.post("/api/offers", headers=waiter, json={"title": "x"})).status_code == 403


async def test_staff_can_see_only_offers_running_now(
    client: AsyncClient, owner_headers, make_staff
) -> None:
    await create(client, owner_headers, title="Now", valid_until=iso(2))
    await create(client, owner_headers, title="Later", valid_from=iso(2))
    await create(client, owner_headers, title="Expired", valid_until=iso(-1))
    await create(client, owner_headers, title="Paused", is_active=False)
    cashier = await make_staff("cashier")

    response = await client.get("/api/offers/active", headers=cashier)

    assert [o["title"] for o in response.json()] == ["Now"]


async def test_offers_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/offers/active")).status_code == 401
