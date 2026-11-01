from decimal import Decimal

import pytest
from httpx import AsyncClient

API = "/api/billing"


async def new_order(client: AsyncClient, headers, order_type="takeaway") -> dict:
    return (await client.post(f"{API}/orders", headers=headers, json={"order_type": order_type})).json()


async def add(client: AsyncClient, headers, order_id, menu_item_id, quantity=1, **extra):
    return await client.post(
        f"{API}/orders/{order_id}/items",
        headers=headers,
        json={"menu_item_id": menu_item_id, "quantity": quantity, **extra},
    )


async def add_variant(client: AsyncClient, headers, item_id, name, price):
    return await client.post(
        f"{API}/menu/items/{item_id}/variants", headers=headers, json={"name": name, "price": price}
    )


async def item(client: AsyncClient, headers, item_id) -> dict:
    items = (await client.get(f"{API}/menu/items", headers=headers)).json()
    return next(i for i in items if i["id"] == item_id)


@pytest.fixture
async def sized(client: AsyncClient, menu, owner_headers) -> dict:
    """Paneer Tikka with Half (120) and Full (200) sizes."""
    half = (await add_variant(client, owner_headers, menu["paneer_id"], "Half", "120")).json()
    full = (await add_variant(client, owner_headers, menu["paneer_id"], "Full", "200")).json()
    return {**menu, "half_id": half["id"], "full_id": full["id"]}


# ------------------------------------------------------------- variants: menu


async def test_variants_are_listed_on_the_menu_item(client: AsyncClient, sized, owner_headers) -> None:
    paneer = await item(client, owner_headers, sized["paneer_id"])

    assert [(v["name"], v["price"]) for v in paneer["variants"]] == [("Half", "120.00"), ("Full", "200.00")]


async def test_plain_items_have_no_variants(client: AsyncClient, menu, owner_headers) -> None:
    assert (await item(client, owner_headers, menu["cola_id"]))["variants"] == []


async def test_variant_name_must_be_unique_per_item_ignoring_case(client: AsyncClient, sized, owner_headers) -> None:
    response = await add_variant(client, owner_headers, sized["paneer_id"], "half", "100")

    assert response.status_code == 409


async def test_two_items_can_use_the_same_size_name(client: AsyncClient, sized, owner_headers) -> None:
    response = await add_variant(client, owner_headers, sized["cola_id"], "Half", "30")

    assert response.status_code == 201


@pytest.mark.parametrize("body", [{"name": "", "price": "10"}, {"name": "   ", "price": "10"}, {"name": "Half", "price": "-1"}])
async def test_invalid_variants_are_rejected(client: AsyncClient, menu, owner_headers, body) -> None:
    response = await client.post(f"{API}/menu/items/{menu['paneer_id']}/variants", headers=owner_headers, json=body)

    assert response.status_code == 422


async def test_variant_for_a_missing_item_is_404(client: AsyncClient, owner_headers) -> None:
    assert (await add_variant(client, owner_headers, 99, "Half", "10")).status_code == 404


async def test_variant_can_be_renamed_and_repriced(client: AsyncClient, sized, owner_headers) -> None:
    response = await client.patch(
        f"{API}/menu/variants/{sized['half_id']}", headers=owner_headers, json={"name": "Small", "price": "130"}
    )

    assert (response.json()["name"], response.json()["price"]) == ("Small", "130.00")


async def test_variant_rename_cannot_clash(client: AsyncClient, sized, owner_headers) -> None:
    response = await client.patch(f"{API}/menu/variants/{sized['half_id']}", headers=owner_headers, json={"name": "FULL"})

    assert response.status_code == 409


async def test_variant_can_be_deleted(client: AsyncClient, sized, owner_headers) -> None:
    assert (await client.delete(f"{API}/menu/variants/{sized['half_id']}", headers=owner_headers)).status_code == 204

    assert [v["name"] for v in (await item(client, owner_headers, sized["paneer_id"]))["variants"]] == ["Full"]


async def test_missing_variant_returns_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.patch(f"{API}/menu/variants/99", headers=owner_headers, json={"name": "x"})).status_code == 404
    assert (await client.delete(f"{API}/menu/variants/99", headers=owner_headers)).status_code == 404


async def test_waiter_cannot_manage_variants(client: AsyncClient, sized, make_staff) -> None:
    waiter = await make_staff("waiter")

    assert (await add_variant(client, waiter, sized["cola_id"], "Large", "60")).status_code == 403
    assert (await client.patch(f"{API}/menu/variants/{sized['half_id']}", headers=waiter, json={"price": "1"})).status_code == 403
    assert (await client.delete(f"{API}/menu/variants/{sized['half_id']}", headers=waiter)).status_code == 403


# ------------------------------------------------------------ variants: orders


async def test_an_item_with_sizes_must_be_ordered_by_size(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], sized["paneer_id"])

    assert response.status_code == 422
    assert "Choose a size" in response.json()["detail"]


async def test_a_size_from_another_item_is_rejected(client: AsyncClient, sized, owner_headers) -> None:
    other = (await add_variant(client, owner_headers, sized["cola_id"], "Large", "60")).json()
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], sized["paneer_id"], variant_id=other["id"])

    assert response.status_code == 404


async def test_a_size_on_an_item_without_sizes_is_rejected(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], sized["cola_id"], variant_id=sized["half_id"])

    assert response.status_code == 422


async def test_the_line_uses_the_size_name_and_price(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], sized["paneer_id"], 2, variant_id=sized["half_id"])

    line = response.json()["items"][0]
    assert (line["name"], line["unit_price"], line["quantity"], line["variant_id"]) == ("Paneer Tikka (Half)", "120.00", 2, sized["half_id"])
    assert line["gst_rate"] == "5.00"  # tax still comes from the item


async def test_different_sizes_are_separate_lines_and_the_same_size_merges(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["half_id"])
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["full_id"])

    response = await add(client, owner_headers, order["id"], sized["paneer_id"], 2, variant_id=sized["half_id"])

    assert [(l["name"], l["quantity"]) for l in response.json()["items"]] == [("Paneer Tikka (Half)", 3), ("Paneer Tikka (Full)", 1)]


async def test_the_bill_uses_the_size_prices(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["half_id"])  # 120
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["full_id"])  # 200

    bill = (await client.post(f"{API}/orders/{order['id']}/bill", headers=owner_headers, json={})).json()

    assert Decimal(bill["subtotal"]) == Decimal("320.00")
    assert Decimal(bill["total"]) == Decimal("336.00")  # + 5% GST


async def test_later_size_edits_do_not_change_an_existing_order(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["half_id"])
    await client.patch(f"{API}/menu/variants/{sized['half_id']}", headers=owner_headers, json={"name": "Mini", "price": "999"})

    line = (await client.get(f"{API}/orders/{order['id']}", headers=owner_headers)).json()["items"][0]

    assert (line["name"], line["unit_price"]) == ("Paneer Tikka (Half)", "120.00")


async def test_deleting_a_size_keeps_the_orders_that_used_it(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["half_id"])
    await client.delete(f"{API}/menu/variants/{sized['half_id']}", headers=owner_headers)

    response = await client.get(f"{API}/orders/{order['id']}", headers=owner_headers)

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Paneer Tikka (Half)"


async def test_receipt_and_kitchen_ticket_show_the_size(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["full_id"])
    ticket = (await client.post(f"{API}/orders/{order['id']}/kot", headers=owner_headers)).json()
    bill = (await client.post(f"{API}/orders/{order['id']}/bill", headers=owner_headers, json={})).json()

    kot = (await client.get(f"{API}/kot/{ticket['id']}/print", headers=owner_headers)).text
    receipt = (await client.get(f"{API}/bills/{bill['id']}/receipt", headers=owner_headers)).text

    assert "Paneer Tikka (Full)" in kot
    assert "Paneer Tikka (Full)" in receipt


async def test_top_dishes_group_all_sizes_under_the_dish(client: AsyncClient, sized, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 1, variant_id=sized["half_id"])
    await add(client, owner_headers, order["id"], sized["paneer_id"], 2, variant_id=sized["full_id"])
    await client.post(f"{API}/orders/{order['id']}/bill", headers=owner_headers, json={})

    dishes = (await client.get("/api/reports/top-dishes", headers=owner_headers)).json()

    assert [(d["menu_item_id"], d["quantity"]) for d in dishes] == [(sized["paneer_id"], 3)]


async def test_creating_a_menu_item_returns_an_empty_variant_list(client: AsyncClient, menu, owner_headers) -> None:
    created = (await client.post(
        f"{API}/menu/items", headers=owner_headers,
        json={"category_id": menu["category_id"], "name": "Naan", "price": "40"},
    )).json()

    assert created["variants"] == []
    assert created["stock_quantity"] is None


# ------------------------------------------------------------------- stock


async def with_stock(client: AsyncClient, headers, item_id, quantity) -> None:
    response = await client.patch(f"{API}/menu/items/{item_id}", headers=headers, json={"stock_quantity": quantity})
    assert response.status_code == 200


async def stock_of(client: AsyncClient, headers, item_id):
    return (await item(client, headers, item_id))["stock_quantity"]


async def test_items_are_untracked_by_default(client: AsyncClient, menu, owner_headers) -> None:
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], menu["paneer_id"], 50)

    assert await stock_of(client, owner_headers, menu["paneer_id"]) is None


async def test_stock_can_be_set_when_creating_an_item(client: AsyncClient, menu, owner_headers) -> None:
    created = (await client.post(
        f"{API}/menu/items", headers=owner_headers,
        json={"category_id": menu["category_id"], "name": "Gulab Jamun", "price": "60", "stock_quantity": 12},
    )).json()

    assert created["stock_quantity"] == 12


async def test_adding_to_an_order_takes_stock(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 10)
    order = await new_order(client, owner_headers)

    await add(client, owner_headers, order["id"], menu["paneer_id"], 3)
    await add(client, owner_headers, order["id"], menu["paneer_id"], 2)

    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 5


async def test_ordering_more_than_is_left_is_refused_and_takes_nothing(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 4)
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], menu["paneer_id"], 5)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only 4 left of Paneer Tikka"
    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 4
    assert (await client.get(f"{API}/orders/{order['id']}", headers=owner_headers)).json()["items"] == []


async def test_a_sold_out_item_cannot_be_ordered(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 0)
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], menu["paneer_id"])

    assert response.status_code == 409
    assert response.json()["detail"] == "Paneer Tikka is sold out"


async def test_the_last_portion_can_be_taken(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 2)
    order = await new_order(client, owner_headers)

    response = await add(client, owner_headers, order["id"], menu["paneer_id"], 2)

    assert response.status_code == 200
    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 0


async def test_changing_a_quantity_adjusts_stock_both_ways(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 10)
    order = await new_order(client, owner_headers)
    line = (await add(client, owner_headers, order["id"], menu["paneer_id"], 2)).json()["items"][0]

    await client.patch(f"{API}/orders/{order['id']}/items/{line['id']}", headers=owner_headers, json={"quantity": 6})
    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 4
    await client.patch(f"{API}/orders/{order['id']}/items/{line['id']}", headers=owner_headers, json={"quantity": 1})

    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 9


async def test_raising_a_quantity_beyond_stock_is_refused(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 3)
    order = await new_order(client, owner_headers)
    line = (await add(client, owner_headers, order["id"], menu["paneer_id"], 2)).json()["items"][0]

    response = await client.patch(
        f"{API}/orders/{order['id']}/items/{line['id']}", headers=owner_headers, json={"quantity": 9}
    )

    assert response.status_code == 409
    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 1
    assert (await client.get(f"{API}/orders/{order['id']}", headers=owner_headers)).json()["items"][0]["quantity"] == 2


async def test_removing_a_line_returns_its_stock(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 10)
    order = await new_order(client, owner_headers)
    line = (await add(client, owner_headers, order["id"], menu["paneer_id"], 4)).json()["items"][0]

    await client.patch(f"{API}/orders/{order['id']}/items/{line['id']}", headers=owner_headers, json={"quantity": 0})

    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 10


async def test_cancelling_an_order_returns_all_its_stock(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 10)
    await with_stock(client, owner_headers, menu["cola_id"], 5)
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], menu["paneer_id"], 4)
    await add(client, owner_headers, order["id"], menu["cola_id"], 2)

    await client.post(f"{API}/orders/{order['id']}/cancel", headers=owner_headers)

    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 10
    assert await stock_of(client, owner_headers, menu["cola_id"]) == 5


async def test_billing_keeps_the_stock_deducted(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 10)
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], menu["paneer_id"], 3)

    await client.post(f"{API}/orders/{order['id']}/bill", headers=owner_headers, json={})

    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 7


async def test_stock_is_shared_across_sizes(client: AsyncClient, sized, owner_headers) -> None:
    await with_stock(client, owner_headers, sized["paneer_id"], 3)
    order = await new_order(client, owner_headers)
    await add(client, owner_headers, order["id"], sized["paneer_id"], 2, variant_id=sized["half_id"])

    response = await add(client, owner_headers, order["id"], sized["paneer_id"], 2, variant_id=sized["full_id"])

    assert response.status_code == 409
    assert await stock_of(client, owner_headers, sized["paneer_id"]) == 1


async def test_stock_can_be_restocked_and_untracked(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 2)
    await with_stock(client, owner_headers, menu["paneer_id"], 40)
    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 40

    await with_stock(client, owner_headers, menu["paneer_id"], None)

    assert await stock_of(client, owner_headers, menu["paneer_id"]) is None


async def test_updating_other_fields_leaves_stock_alone(client: AsyncClient, menu, owner_headers) -> None:
    await with_stock(client, owner_headers, menu["paneer_id"], 7)

    await client.patch(f"{API}/menu/items/{menu['paneer_id']}", headers=owner_headers, json={"price": "250"})

    assert await stock_of(client, owner_headers, menu["paneer_id"]) == 7


async def test_negative_stock_is_rejected(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.patch(f"{API}/menu/items/{menu['paneer_id']}", headers=owner_headers, json={"stock_quantity": -1})

    assert response.status_code == 422


async def test_waiter_cannot_change_stock(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")

    response = await client.patch(f"{API}/menu/items/{menu['paneer_id']}", headers=waiter, json={"stock_quantity": 99})

    assert response.status_code == 403
