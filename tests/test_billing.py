import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import AsyncClient

API = "/api/billing"


async def new_order(client: AsyncClient, headers, menu, **overrides) -> dict:
    body = {"order_type": "dine_in", "table_id": menu["table_id"], **overrides}
    response = await client.post(f"{API}/orders", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def add_item(client: AsyncClient, headers, order_id, menu_item_id, quantity=1, **extra):
    return await client.post(
        f"{API}/orders/{order_id}/items",
        headers=headers,
        json={"menu_item_id": menu_item_id, "quantity": quantity, **extra},
    )


# ----------------------------------------------------------------- menu


async def test_menu_requires_login(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/menu/items")).status_code == 401


async def test_manager_can_create_items_and_waiter_can_read_them(
    client: AsyncClient, menu, make_staff
) -> None:
    waiter = await make_staff("waiter")

    response = await client.get(f"{API}/menu/items", headers=waiter)

    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {"Paneer Tikka", "Cola"}


async def test_waiter_cannot_create_menu_items(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")

    response = await client.post(
        f"{API}/menu/items",
        headers=waiter,
        json={"category_id": menu["category_id"], "name": "Naan", "price": "40"},
    )

    assert response.status_code == 403


async def test_duplicate_category_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(
        f"{API}/menu/categories", headers=owner_headers, json={"name": "Mains"}
    )

    assert response.status_code == 409


async def test_menu_item_needs_existing_category(client: AsyncClient, owner_headers) -> None:
    response = await client.post(
        f"{API}/menu/items",
        headers=owner_headers,
        json={"category_id": 999, "name": "Ghost", "price": "10"},
    )

    assert response.status_code == 404


async def test_negative_price_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(
        f"{API}/menu/items",
        headers=owner_headers,
        json={"category_id": menu["category_id"], "name": "Bad", "price": "-5"},
    )

    assert response.status_code == 422


async def test_item_can_be_marked_unavailable_and_filtered(
    client: AsyncClient, menu, owner_headers
) -> None:
    await client.patch(
        f"{API}/menu/items/{menu['cola_id']}", headers=owner_headers, json={"is_available": False}
    )

    response = await client.get(f"{API}/menu/items?available_only=true", headers=owner_headers)

    assert [item["name"] for item in response.json()] == ["Paneer Tikka"]


# --------------------------------------------------------------- orders


async def test_dine_in_order_requires_a_table(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "dine_in"}
    )

    assert response.status_code == 422


async def test_delivery_order_requires_an_address(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "delivery"}
    )

    assert response.status_code == 422


async def test_takeaway_order_needs_no_table(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "takeaway"}
    )

    assert response.status_code == 201
    assert response.json()["table_id"] is None


async def test_table_cannot_have_two_open_orders(client: AsyncClient, menu, owner_headers) -> None:
    await new_order(client, owner_headers, menu)

    response = await client.post(
        f"{API}/orders",
        headers=owner_headers,
        json={"order_type": "dine_in", "table_id": menu["table_id"]},
    )

    assert response.status_code == 409


async def test_adding_item_snapshots_name_price_and_gst(
    client: AsyncClient, menu, owner_headers
) -> None:
    order = await new_order(client, owner_headers, menu)

    response = await add_item(client, owner_headers, order["id"], menu["paneer_id"], 2)

    line = response.json()["items"][0]
    assert (line["name"], Decimal(line["unit_price"]), line["quantity"]) == (
        "Paneer Tikka",
        Decimal("200.00"),
        2,
    )


async def test_later_menu_price_change_does_not_alter_existing_order(
    client: AsyncClient, menu, owner_headers
) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"])
    await client.patch(
        f"{API}/menu/items/{menu['paneer_id']}", headers=owner_headers, json={"price": "999"}
    )

    response = await client.get(f"{API}/orders/{order['id']}", headers=owner_headers)

    assert Decimal(response.json()["items"][0]["unit_price"]) == Decimal("200.00")


async def test_adding_the_same_unsent_item_merges_quantity(
    client: AsyncClient, menu, owner_headers
) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"], 1)

    response = await add_item(client, owner_headers, order["id"], menu["paneer_id"], 2)

    items = response.json()["items"]
    assert len(items) == 1 and items[0]["quantity"] == 3


async def test_unavailable_item_cannot_be_ordered(client: AsyncClient, menu, owner_headers) -> None:
    await client.patch(
        f"{API}/menu/items/{menu['cola_id']}", headers=owner_headers, json={"is_available": False}
    )
    order = await new_order(client, owner_headers, menu)

    response = await add_item(client, owner_headers, order["id"], menu["cola_id"])

    assert response.status_code == 409


async def test_quantity_can_be_changed_and_zero_removes_the_line(
    client: AsyncClient, menu, owner_headers
) -> None:
    order = await new_order(client, owner_headers, menu)
    added = await add_item(client, owner_headers, order["id"], menu["paneer_id"], 2)
    item_id = added.json()["items"][0]["id"]

    changed = await client.patch(
        f"{API}/orders/{order['id']}/items/{item_id}", headers=owner_headers, json={"quantity": 5}
    )
    removed = await client.patch(
        f"{API}/orders/{order['id']}/items/{item_id}", headers=owner_headers, json={"quantity": 0}
    )

    assert changed.json()["items"][0]["quantity"] == 5
    assert removed.json()["items"] == []


async def test_list_orders_filters_by_status(client: AsyncClient, menu, owner_headers) -> None:
    open_order = await new_order(client, owner_headers, menu)
    cancelled = await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "takeaway"}
    )
    await client.post(f"{API}/orders/{cancelled.json()['id']}/cancel", headers=owner_headers)

    response = await client.get(f"{API}/orders?status=open", headers=owner_headers)

    assert [order["id"] for order in response.json()] == [open_order["id"]]


async def test_waiter_cannot_cancel_an_order(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")
    order = await new_order(client, waiter, menu)

    response = await client.post(f"{API}/orders/{order['id']}/cancel", headers=waiter)

    assert response.status_code == 403


# ------------------------------------------------------------------ KOT


async def test_kot_sends_only_new_items(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"], 2)
    first = await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)
    await add_item(client, owner_headers, order["id"], menu["cola_id"], 1)

    second = await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)

    assert first.status_code == 201
    assert [item["name"] for item in first.json()["items"]] == ["Paneer Tikka"]
    assert [item["name"] for item in second.json()["items"]] == ["Cola"]


async def test_kot_with_nothing_new_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"])
    await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)

    response = await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)

    assert response.status_code == 409


async def test_item_added_after_kot_becomes_a_separate_line(
    client: AsyncClient, menu, owner_headers
) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"])
    await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)

    response = await add_item(client, owner_headers, order["id"], menu["paneer_id"])

    assert len(response.json()["items"]) == 2


async def test_kot_print_is_plain_text_with_items(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"], 2, notes="extra spicy")
    ticket = await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)

    response = await client.get(f"{API}/kot/{ticket.json()['id']}/print", headers=owner_headers)

    assert response.headers["content-type"].startswith("text/plain")
    assert "2 x Paneer Tikka" in response.text
    assert "extra spicy" in response.text
    assert "T1" in response.text


# ---------------------------------------------------------------- bills


async def make_bill(client, headers, menu, discount="0") -> dict:
    order = await new_order(client, headers, menu)
    await add_item(client, headers, order["id"], menu["paneer_id"], 2)  # 400 @ 5%
    await add_item(client, headers, order["id"], menu["cola_id"], 2)  # 100 @ 18%
    response = await client.post(
        f"{API}/orders/{order['id']}/bill", headers=headers, json={"discount": discount}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_bill_totals_include_gst_split(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu)

    # tax = 20 + 18 = 38 -> cgst 19, sgst 19; total 538
    assert Decimal(bill["subtotal"]) == Decimal("500.00")
    assert Decimal(bill["cgst"]) == Decimal("19.00")
    assert Decimal(bill["sgst"]) == Decimal("19.00")
    assert Decimal(bill["total"]) == Decimal("538.00")
    assert bill["status"] == "unpaid"
    assert Decimal(bill["amount_due"]) == Decimal("538.00")


async def test_bill_applies_discount(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu, discount="50")

    # taxable 450, tax 38 * 450/500 = 34.20, total 484.20 -> 484
    assert Decimal(bill["discount"]) == Decimal("50.00")
    assert Decimal(bill["total"]) == Decimal("484.00")
    assert Decimal(bill["round_off"]) == Decimal("-0.20")


async def test_discount_above_subtotal_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers, menu)
    await add_item(client, owner_headers, order["id"], menu["paneer_id"])

    response = await client.post(
        f"{API}/orders/{order['id']}/bill", headers=owner_headers, json={"discount": "9999"}
    )

    assert response.status_code == 422


async def test_empty_order_cannot_be_billed(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers, menu)

    response = await client.post(
        f"{API}/orders/{order['id']}/bill", headers=owner_headers, json={}
    )

    assert response.status_code == 409


async def test_billing_closes_the_order_and_blocks_more_items(
    client: AsyncClient, menu, owner_headers
) -> None:
    bill = await make_bill(client, owner_headers, menu)

    order = await client.get(f"{API}/orders/{bill['order_id']}", headers=owner_headers)
    more = await add_item(client, owner_headers, bill["order_id"], menu["cola_id"])
    again = await client.post(
        f"{API}/orders/{bill['order_id']}/bill", headers=owner_headers, json={}
    )

    assert order.json()["status"] == "billed"
    assert more.status_code == 409
    assert again.status_code == 409


async def test_billing_frees_the_table(client: AsyncClient, menu, owner_headers) -> None:
    await make_bill(client, owner_headers, menu)

    response = await client.post(
        f"{API}/orders",
        headers=owner_headers,
        json={"order_type": "dine_in", "table_id": menu["table_id"]},
    )

    assert response.status_code == 201


async def test_invoice_numbers_increase(client: AsyncClient, menu, owner_headers) -> None:
    first = await make_bill(client, owner_headers, menu)
    second = await make_bill(client, owner_headers, menu)

    assert first["invoice_number"] != second["invoice_number"]
    assert first["invoice_number"].endswith("000001")
    assert second["invoice_number"].endswith("000002")


async def test_waiter_cannot_generate_a_bill(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")
    order = await new_order(client, waiter, menu)
    await add_item(client, waiter, order["id"], menu["paneer_id"])

    response = await client.post(f"{API}/orders/{order['id']}/bill", headers=waiter, json={})

    assert response.status_code == 403


async def test_bill_can_be_fetched_by_order(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu)

    response = await client.get(f"{API}/orders/{bill['order_id']}/bill", headers=owner_headers)

    assert response.json()["id"] == bill["id"]


async def test_order_without_bill_returns_404(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers, menu)

    response = await client.get(f"{API}/orders/{order['id']}/bill", headers=owner_headers)

    assert response.status_code == 404


# ------------------------------------------------------------- payments


async def pay(client, headers, bill_id, mode, amount, **extra):
    return await client.post(
        f"{API}/bills/{bill_id}/payments",
        headers=headers,
        json={"mode": mode, "amount": amount, **extra},
    )


async def test_full_payment_marks_bill_paid(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu)

    response = await pay(client, owner_headers, bill["id"], "cash", "538.00")

    assert response.json()["status"] == "paid"
    assert Decimal(response.json()["amount_due"]) == Decimal("0.00")


async def test_split_payment_across_modes(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu)

    partial = await pay(client, owner_headers, bill["id"], "cash", "200.00")
    final = await pay(client, owner_headers, bill["id"], "upi", "338.00", reference="UPI123")

    assert partial.json()["status"] == "unpaid"
    assert Decimal(partial.json()["amount_due"]) == Decimal("338.00")
    assert final.json()["status"] == "paid"
    assert [p["mode"] for p in final.json()["payments"]] == ["cash", "upi"]


async def test_overpayment_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu)

    response = await pay(client, owner_headers, bill["id"], "cash", "538.01")

    assert response.status_code == 422


async def test_paying_a_paid_bill_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    bill = await make_bill(client, owner_headers, menu)
    await pay(client, owner_headers, bill["id"], "cash", "538.00")

    response = await pay(client, owner_headers, bill["id"], "cash", "1.00")

    assert response.status_code == 409


async def test_invalid_payment_mode_and_amount_are_rejected(
    client: AsyncClient, menu, owner_headers
) -> None:
    bill = await make_bill(client, owner_headers, menu)

    bad_mode = await pay(client, owner_headers, bill["id"], "bitcoin", "10")
    zero = await pay(client, owner_headers, bill["id"], "cash", "0")

    assert bad_mode.status_code == 422
    assert zero.status_code == 422


async def test_waiter_cannot_take_payment(client: AsyncClient, menu, owner_headers, make_staff) -> None:
    bill = await make_bill(client, owner_headers, menu)
    waiter = await make_staff("waiter")

    response = await pay(client, waiter, bill["id"], "cash", "10")

    assert response.status_code == 403


async def test_cashier_can_bill_and_take_payment(client: AsyncClient, menu, make_staff) -> None:
    cashier = await make_staff("cashier")
    bill = await make_bill(client, cashier, menu)

    response = await pay(client, cashier, bill["id"], "card", "538")

    assert response.json()["status"] == "paid"


async def test_unpaid_bills_can_be_listed(client: AsyncClient, menu, owner_headers) -> None:
    unpaid = await make_bill(client, owner_headers, menu)
    paid = await make_bill(client, owner_headers, menu)
    await pay(client, owner_headers, paid["id"], "cash", "538")

    response = await client.get(f"{API}/bills?status=unpaid", headers=owner_headers)

    assert [bill["id"] for bill in response.json()] == [unpaid["id"]]
    assert Decimal(response.json()[0]["amount_due"]) == Decimal("538.00")


# -------------------------------------------------------------- receipt


async def test_receipt_shows_items_tax_total_and_payment(
    client: AsyncClient, menu, owner_headers
) -> None:
    bill = await make_bill(client, owner_headers, menu)
    await pay(client, owner_headers, bill["id"], "cash", "538.00")

    response = await client.get(f"{API}/bills/{bill['id']}/receipt", headers=owner_headers)

    text = response.text
    assert response.headers["content-type"].startswith("text/plain")
    assert bill["invoice_number"] in text
    assert "Paneer Tikka" in text and "Cola" in text
    assert "CGST" in text and "19.00" in text
    assert "538.00" in text
    assert "CASH" in text and "PAID" in text
    assert all(len(line) <= 42 for line in text.splitlines())


async def test_receipt_time_is_in_the_restaurant_timezone(
    client: AsyncClient, menu, owner_headers
) -> None:
    bill = await make_bill(client, owner_headers, menu)

    response = await client.get(f"{API}/bills/{bill['id']}/receipt", headers=owner_headers)

    printed = re.search(r"\d{2}-\d{2}-\d{4} \d{2}:\d{2}", response.text).group()
    printed_at = datetime.strptime(printed, "%d-%m-%Y %H:%M")
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    assert abs((now_ist - printed_at).total_seconds()) < 180


async def test_missing_bill_returns_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.get(f"{API}/bills/999", headers=owner_headers)).status_code == 404
    assert (await client.get(f"{API}/bills/999/receipt", headers=owner_headers)).status_code == 404


# -------------------------------------------------------------- reports


async def test_daily_report_totals_sales_by_mode(client: AsyncClient, menu, owner_headers) -> None:
    first = await make_bill(client, owner_headers, menu)
    second = await make_bill(client, owner_headers, menu)
    await pay(client, owner_headers, first["id"], "cash", "538")
    await pay(client, owner_headers, second["id"], "upi", "300")

    response = await client.get(f"{API}/reports/daily", headers=owner_headers)

    body = response.json()
    assert body["bill_count"] == 2
    assert Decimal(body["total_sales"]) == Decimal("1076.00")
    assert Decimal(body["cash"]) == Decimal("538.00")
    assert Decimal(body["upi"]) == Decimal("300.00")
    assert Decimal(body["card"]) == Decimal("0")


async def test_daily_report_for_an_empty_day_is_zero(client: AsyncClient, owner_headers) -> None:
    response = await client.get(f"{API}/reports/daily?day=2020-01-01", headers=owner_headers)

    assert response.json()["bill_count"] == 0
    assert Decimal(response.json()["total_sales"]) == Decimal("0")


async def test_cashier_cannot_view_reports(client: AsyncClient, make_staff) -> None:
    cashier = await make_staff("cashier")

    response = await client.get(f"{API}/reports/daily", headers=cashier)

    assert response.status_code == 403
