from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from restaurant_management_system.billing.models import Bill
from restaurant_management_system.customers.services import normalize_phone
from tests.helpers import place_order

API = "/api/billing"


# ------------------------------------------------------- phone numbers


@pytest.mark.parametrize(
    "raw",
    ["9876543210", "+91 98765 43210", "919876543210", "09876543210", "98765-43210", " 98765 43210 "],
)
def test_phone_numbers_are_normalized_to_ten_digits(raw: str) -> None:
    assert normalize_phone(raw) == "9876543210"


@pytest.mark.parametrize("raw", ["12345", "1234567890", "98765432101234", "abcdefghij", ""])
def test_invalid_phone_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(HTTPException) as error:
        normalize_phone(raw)
    assert error.value.status_code == 422


# ------------------------------------------------- linking to an order


async def test_order_with_phone_creates_and_links_a_customer(
    client: AsyncClient, menu, owner_headers
) -> None:
    response = await client.post(
        f"{API}/orders",
        headers=owner_headers,
        json={"order_type": "takeaway", "customer_phone": "+91 98765 43210", "customer_name": "Neha"},
    )

    order = response.json()
    assert order["customer_id"] is not None
    assert order["customer_phone"] == "9876543210"
    assert order["customer_name"] == "Neha"


async def test_same_number_in_different_formats_is_one_customer(
    client: AsyncClient, menu, owner_headers
) -> None:
    first = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210")
    second = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="+91-98765-43210")

    customers = (await client.get("/api/customers", headers=owner_headers)).json()
    assert len(customers) == 1
    assert first["order_id"] != second["order_id"]


async def test_order_with_invalid_phone_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(
        f"{API}/orders",
        headers=owner_headers,
        json={"order_type": "takeaway", "customer_phone": "12345"},
    )

    assert response.status_code == 422


async def test_order_without_phone_has_no_customer(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(f"{API}/orders", headers=owner_headers, json={"order_type": "takeaway"})

    assert response.json()["customer_id"] is None


async def test_existing_customer_name_is_not_overwritten(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210", name="Neha")
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210", name="Someone Else")

    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    assert customer["name"] == "Neha"


async def test_missing_name_is_filled_in_later(client: AsyncClient, menu, owner_headers) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210")
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210", name="Neha")

    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    assert customer["name"] == "Neha"


async def test_customer_can_be_attached_to_an_open_dine_in_order(
    client: AsyncClient, menu, owner_headers
) -> None:
    order = (
        await client.post(
            f"{API}/orders",
            headers=owner_headers,
            json={"order_type": "dine_in", "table_id": menu["table_id"]},
        )
    ).json()

    response = await client.put(
        f"{API}/orders/{order['id']}/customer",
        headers=owner_headers,
        json={"phone": "9876543210", "name": "Neha"},
    )

    assert response.status_code == 200
    assert response.json()["customer_phone"] == "9876543210"
    assert response.json()["customer_id"] is not None


async def test_customer_cannot_be_changed_after_billing(
    client: AsyncClient, menu, owner_headers
) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1})

    response = await client.put(
        f"{API}/orders/{bill['order_id']}/customer",
        headers=owner_headers,
        json={"phone": "9876543210"},
    )

    assert response.status_code == 409


async def test_waiter_can_attach_a_customer(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")
    order = await place_order(client, waiter, menu, {}, bill=False)

    response = await client.put(
        f"{API}/orders/{order['id']}/customer", headers=waiter, json={"phone": "9876543210"}
    )

    assert response.status_code == 200


# ------------------------------------------------------------- lookup


async def test_lookup_of_unknown_number_is_404(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.get("/api/customers/lookup?phone=9876543210", headers=owner_headers)

    assert response.status_code == 404


async def test_lookup_reports_visits_and_returning_status(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210", name="Neha")
    first = (await client.get("/api/customers/lookup?phone=9876543210", headers=owner_headers)).json()
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210")

    second = (await client.get("/api/customers/lookup?phone=%2B919876543210", headers=owner_headers)).json()

    assert (first["name"], first["visits"], first["is_returning"]) == ("Neha", 1, False)
    assert (second["visits"], second["is_returning"]) == (2, True)


async def test_lookup_hides_spend_and_is_open_to_waiters(
    client: AsyncClient, menu, owner_headers, make_staff
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210")
    waiter = await make_staff("waiter")

    response = await client.get("/api/customers/lookup?phone=9876543210", headers=waiter)

    assert response.status_code == 200
    assert "total_spent" not in response.json()


async def test_lookup_rejects_an_invalid_number(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.get("/api/customers/lookup?phone=123", headers=owner_headers)

    assert response.status_code == 422


# ---------------------------------------------------- visits counting


async def test_only_billed_orders_count_as_visits(client: AsyncClient, menu, owner_headers) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210")  # billed
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210", bill=False)  # open
    cancelled = await place_order(
        client, owner_headers, menu, {"paneer": 1}, phone="9876543210", bill=False
    )
    await client.post(f"{API}/orders/{cancelled['id']}/cancel", headers=owner_headers)

    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]

    assert customer["visits"] == 1
    assert customer["is_returning"] is False


async def test_customer_with_no_bills_has_zero_visits(client: AsyncClient, menu, owner_headers) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210", bill=False)

    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]

    assert customer["visits"] == 0
    assert Decimal(customer["total_spent"]) == Decimal("0")
    assert customer["last_visit"] is None


# ---------------------------------------------------------- customer list


async def test_customer_list_is_manager_only(client: AsyncClient, menu, make_staff) -> None:
    cashier = await make_staff("cashier")

    assert (await client.get("/api/customers", headers=cashier)).status_code == 403


async def test_customer_list_is_sorted_by_visits_and_searchable(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    for _ in range(3):
        await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000002", name="Bala")

    everyone = (await client.get("/api/customers", headers=owner_headers)).json()
    by_name = (await client.get("/api/customers?search=asha", headers=owner_headers)).json()
    by_phone = (await client.get("/api/customers?search=0002", headers=owner_headers)).json()

    assert [c["name"] for c in everyone] == ["Bala", "Asha"]
    assert [c["name"] for c in by_name] == ["Asha"]
    assert [c["name"] for c in by_phone] == ["Bala"]


# ---------------------------------------------------------- customer detail


async def test_customer_detail_has_order_history_and_favourite_dishes(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 2, "cola": 1}, phone="9876543210", name="Neha")
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9876543210")
    customer_id = (await client.get("/api/customers", headers=owner_headers)).json()[0]["id"]

    detail = (await client.get(f"/api/customers/{customer_id}", headers=owner_headers)).json()

    assert detail["visits"] == 2
    assert detail["is_returning"] is True
    assert len(detail["orders"]) == 2
    assert detail["orders"][0]["items"] == [{"name": "Paneer Tikka", "quantity": 1}]  # newest first
    assert detail["favourite_dishes"][0]["name"] == "Paneer Tikka"
    assert detail["favourite_dishes"][0]["quantity"] == 3
    # 400 + 5% GST = 420 and 50 + 18% GST = 59 (479), then 200 + 5% GST = 210
    assert Decimal(detail["total_spent"]) == Decimal("479.00") + Decimal("210.00")


async def test_missing_customer_detail_is_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.get("/api/customers/999", headers=owner_headers)).status_code == 404


async def test_customer_detail_is_manager_only(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")

    assert (await client.get("/api/customers/1", headers=waiter)).status_code == 403


# ------------------------------------------------------------ top dishes


async def test_top_dishes_ranks_by_quantity_across_orders(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 2, "cola": 1})
    await place_order(client, owner_headers, menu, {"paneer": 1, "cola": 4})
    await place_order(client, owner_headers, menu, {"cola": 1})

    dishes = (await client.get("/api/reports/top-dishes", headers=owner_headers)).json()

    assert [(d["name"], d["quantity"], d["orders"]) for d in dishes] == [
        ("Cola", 6, 3),
        ("Paneer Tikka", 3, 2),
    ]
    assert Decimal(dishes[0]["revenue"]) == Decimal("300.00")
    assert Decimal(dishes[1]["revenue"]) == Decimal("600.00")


async def test_top_dishes_ignores_open_and_cancelled_orders(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1})
    await place_order(client, owner_headers, menu, {"cola": 9}, bill=False)
    cancelled = await place_order(client, owner_headers, menu, {"cola": 9}, bill=False)
    await client.post(f"{API}/orders/{cancelled['id']}/cancel", headers=owner_headers)

    dishes = (await client.get("/api/reports/top-dishes", headers=owner_headers)).json()

    assert [d["name"] for d in dishes] == ["Paneer Tikka"]


async def test_top_dishes_respects_limit(client: AsyncClient, menu, owner_headers) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 2, "cola": 1})

    dishes = (await client.get("/api/reports/top-dishes?limit=1", headers=owner_headers)).json()

    assert [d["name"] for d in dishes] == ["Paneer Tikka"]


async def test_top_dishes_keeps_the_name_it_was_sold_under(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1})
    await client.patch(
        f"{API}/menu/items/{menu['paneer_id']}", headers=owner_headers, json={"price": "250"}
    )
    await place_order(client, owner_headers, menu, {"paneer": 1})

    dishes = (await client.get("/api/reports/top-dishes", headers=owner_headers)).json()

    assert len(dishes) == 1
    assert dishes[0]["quantity"] == 2
    assert Decimal(dishes[0]["revenue"]) == Decimal("450.00")  # 200 then 250


async def test_top_dishes_can_be_limited_to_recent_days(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine
) -> None:
    old = await place_order(client, owner_headers, menu, {"cola": 5})
    await place_order(client, owner_headers, menu, {"paneer": 1})
    async with async_sessionmaker(engine)() as session:
        await session.execute(
            update(Bill).where(Bill.id == old["id"]).values(created_at=datetime.now(UTC) - timedelta(days=60))
        )
        await session.commit()

    recent = (await client.get("/api/reports/top-dishes?days=30", headers=owner_headers)).json()
    everything = (await client.get("/api/reports/top-dishes", headers=owner_headers)).json()

    assert [d["name"] for d in recent] == ["Paneer Tikka"]
    assert [d["name"] for d in everything] == ["Cola", "Paneer Tikka"]


async def test_top_dishes_with_no_sales_is_empty(client: AsyncClient, owner_headers) -> None:
    assert (await client.get("/api/reports/top-dishes", headers=owner_headers)).json() == []


async def test_reports_are_manager_only(client: AsyncClient, make_staff) -> None:
    cashier = await make_staff("cashier")

    assert (await client.get("/api/reports/top-dishes", headers=cashier)).status_code == 403
    assert (await client.get("/api/reports/top-customers", headers=cashier)).status_code == 403


# --------------------------------------------------------- top customers


async def test_top_customers_ranked_by_visits_then_spend(
    client: AsyncClient, menu, owner_headers
) -> None:
    # Asha: 1 big visit. Bala: 3 small visits. Chitra: 3 visits, spends more than Bala.
    await place_order(client, owner_headers, menu, {"paneer": 9}, phone="9000000001", name="Asha")
    for _ in range(3):
        await place_order(client, owner_headers, menu, {"cola": 1}, phone="9000000002", name="Bala")
    for _ in range(3):
        await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000003", name="Chitra")

    customers = (await client.get("/api/reports/top-customers", headers=owner_headers)).json()

    assert [(c["name"], c["visits"]) for c in customers] == [("Chitra", 3), ("Bala", 3), ("Asha", 1)]
    assert [c["is_returning"] for c in customers] == [True, True, False]


async def test_top_customers_excludes_guests_who_never_completed_a_visit(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", bill=False)
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000002")

    customers = (await client.get("/api/reports/top-customers", headers=owner_headers)).json()

    assert [c["phone"] for c in customers] == ["9000000002"]


async def test_top_customers_ignores_orders_without_a_phone(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1})

    assert (await client.get("/api/reports/top-customers", headers=owner_headers)).json() == []


async def test_top_customers_reports_spend_and_visit_dates(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")

    customer = (await client.get("/api/reports/top-customers", headers=owner_headers)).json()[0]

    assert Decimal(customer["total_spent"]) == Decimal("420.00")
    assert customer["first_visit"] is not None and customer["last_visit"] is not None


async def test_top_customers_can_be_limited_to_recent_days(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000002", name="Bala")
    async with async_sessionmaker(engine)() as session:
        await session.execute(
            update(Bill).where(Bill.id == old["id"]).values(created_at=datetime.now(UTC) - timedelta(days=90))
        )
        await session.commit()

    recent = (await client.get("/api/reports/top-customers?days=30", headers=owner_headers)).json()

    assert [c["name"] for c in recent] == ["Bala"]
