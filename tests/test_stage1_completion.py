import pytest
from httpx import AsyncClient

API = "/api/billing"
PROFILE_URL = "/api/restaurant/profile"
# The restaurant name is set at registration (see conftest, "Spice Garden") and has its own
# endpoint. These are the extra details printed on receipts.
PROFILE = {
    "address": "12 Connaught Place, New Delhi 110001",
    "phone": "011 4000 1234",
    "gstin": "07AAAAA0000A1Z5",
    "fssai": "12345678901234",
    "receipt_footer": "Thank you for dining with us!",
}


async def bill_one_order(client: AsyncClient, headers, menu) -> dict:
    order = (await client.post(f"{API}/orders", headers=headers, json={"order_type": "takeaway"})).json()
    await client.post(
        f"{API}/orders/{order['id']}/items",
        headers=headers,
        json={"menu_item_id": menu["paneer_id"], "quantity": 1},
    )
    return (await client.post(f"{API}/orders/{order['id']}/bill", headers=headers, json={})).json()


# ------------------------------------------------------ restaurant profile


async def test_details_are_blank_until_saved_but_the_name_is_there(client: AsyncClient, owner_headers) -> None:
    response = await client.get(PROFILE_URL, headers=owner_headers)

    assert response.status_code == 200
    assert response.json() == {
        "name": "Spice Garden",
        "address": "",
        "phone": "",
        "gstin": "",
        "fssai": "",
        "receipt_footer": "",
    }


async def test_owner_can_save_and_read_the_details(client: AsyncClient, owner_headers) -> None:
    saved = await client.put(PROFILE_URL, headers=owner_headers, json=PROFILE)
    read = await client.get(PROFILE_URL, headers=owner_headers)

    assert saved.status_code == 200
    assert read.json() == {"name": "Spice Garden", **PROFILE}


async def test_saving_details_does_not_change_the_restaurant_name(client: AsyncClient, owner_headers) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json=PROFILE)

    assert (await client.get("/api/restaurant", headers=owner_headers)).json() == {"name": "Spice Garden"}


async def test_renaming_does_not_wipe_the_saved_details(client: AsyncClient, owner_headers) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json=PROFILE)

    await client.put("/api/restaurant", headers=owner_headers, json={"name": "Dilli Darbar"})

    read = (await client.get(PROFILE_URL, headers=owner_headers)).json()
    assert read["name"] == "Dilli Darbar"
    assert read["gstin"] == PROFILE["gstin"]


async def test_saving_again_updates_the_same_details(client: AsyncClient, owner_headers) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json=PROFILE)
    await client.put(PROFILE_URL, headers=owner_headers, json={**PROFILE, "address": "New address"})

    assert (await client.get(PROFILE_URL, headers=owner_headers)).json()["address"] == "New address"


@pytest.mark.parametrize("gstin", ["123", "07aaaaa0000a1z5x", "AAAAAAAAAAAAAAA"])
async def test_invalid_gstin_is_rejected(client: AsyncClient, owner_headers, gstin) -> None:
    response = await client.put(PROFILE_URL, headers=owner_headers, json={**PROFILE, "gstin": gstin})

    assert response.status_code == 422


async def test_lowercase_gstin_is_normalised(client: AsyncClient, owner_headers) -> None:
    response = await client.put(
        PROFILE_URL, headers=owner_headers, json={**PROFILE, "gstin": "07aaaaa0000a1z5"}
    )

    assert response.json()["gstin"] == "07AAAAA0000A1Z5"


async def test_invalid_fssai_is_rejected(client: AsyncClient, owner_headers) -> None:
    response = await client.put(PROFILE_URL, headers=owner_headers, json={**PROFILE, "fssai": "12345"})

    assert response.status_code == 422


async def test_optional_details_can_be_cleared(client: AsyncClient, owner_headers) -> None:
    response = await client.put(PROFILE_URL, headers=owner_headers, json={**PROFILE, "gstin": "", "fssai": ""})

    assert response.status_code == 200
    assert response.json()["gstin"] == ""


async def test_manager_can_edit_details_but_waiter_cannot(client: AsyncClient, make_staff) -> None:
    manager = await make_staff("manager")
    waiter = await make_staff("waiter")

    assert (await client.put(PROFILE_URL, headers=manager, json=PROFILE)).status_code == 200
    assert (await client.get(PROFILE_URL, headers=waiter)).status_code == 200
    assert (await client.put(PROFILE_URL, headers=waiter, json=PROFILE)).status_code == 403


async def test_details_require_login(client: AsyncClient) -> None:
    assert (await client.get(PROFILE_URL)).status_code == 401
    assert (await client.put(PROFILE_URL, json=PROFILE)).status_code == 401


async def test_receipt_shows_the_name_and_all_saved_details(client: AsyncClient, menu, owner_headers) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json=PROFILE)
    bill = await bill_one_order(client, owner_headers, menu)

    text = (await client.get(f"{API}/bills/{bill['id']}/receipt", headers=owner_headers)).text

    assert "SPICE GARDEN" in text
    assert "Connaught Place" in text
    assert "GSTIN: 07AAAAA0000A1Z5" in text
    assert "FSSAI: 12345678901234" in text
    assert "Ph: 011 4000 1234" in text
    assert "Thank you for dining with us!" in text
    assert text.index("SPICE GARDEN") < text.index("TAX INVOICE")
    assert all(len(line) <= 42 for line in text.splitlines())


async def test_name_only_receipt_is_compact(client: AsyncClient, menu, owner_headers) -> None:
    bill = await bill_one_order(client, owner_headers, menu)

    lines = (await client.get(f"{API}/bills/{bill['id']}/receipt", headers=owner_headers)).text.splitlines()

    assert lines[0].strip() == "SPICE GARDEN"
    assert lines[1].strip() == "TAX INVOICE"
    assert "Thank you! Visit again." in "\n".join(lines)
    assert not any("GSTIN" in line for line in lines)


# ---------------------------------------------------- editing the catalogue


async def test_category_can_be_renamed_and_reordered(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.patch(
        f"{API}/menu/categories/{menu['category_id']}",
        headers=owner_headers,
        json={"name": "Main Course", "sort_order": 3},
    )

    assert response.json()["name"] == "Main Course"
    assert response.json()["sort_order"] == 3


async def test_category_rename_cannot_clash_with_another(client: AsyncClient, menu, owner_headers) -> None:
    other = (await client.post(f"{API}/menu/categories", headers=owner_headers, json={"name": "Drinks"})).json()

    response = await client.patch(
        f"{API}/menu/categories/{other['id']}", headers=owner_headers, json={"name": "Mains"}
    )

    assert response.status_code == 409


async def test_category_with_items_cannot_be_deleted(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.delete(f"{API}/menu/categories/{menu['category_id']}", headers=owner_headers)

    assert response.status_code == 409


async def test_empty_category_can_be_deleted(client: AsyncClient, owner_headers) -> None:
    category = (await client.post(f"{API}/menu/categories", headers=owner_headers, json={"name": "Empty"})).json()

    response = await client.delete(f"{API}/menu/categories/{category['id']}", headers=owner_headers)

    assert response.status_code == 204
    categories = (await client.get(f"{API}/menu/categories", headers=owner_headers)).json()
    assert categories == []


async def test_menu_item_can_be_edited_and_moved(client: AsyncClient, menu, owner_headers) -> None:
    drinks = (await client.post(f"{API}/menu/categories", headers=owner_headers, json={"name": "Drinks"})).json()

    response = await client.patch(
        f"{API}/menu/items/{menu['cola_id']}",
        headers=owner_headers,
        json={"name": "Cola 300ml", "price": "60", "gst_rate": "12", "category_id": drinks["id"]},
    )

    body = response.json()
    assert (body["name"], body["price"], body["category_id"]) == ("Cola 300ml", "60.00", drinks["id"])


async def test_menu_item_cannot_move_to_a_missing_category(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.patch(
        f"{API}/menu/items/{menu['cola_id']}", headers=owner_headers, json={"category_id": 999}
    )

    assert response.status_code == 404


async def test_never_ordered_item_can_be_deleted(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.delete(f"{API}/menu/items/{menu['cola_id']}", headers=owner_headers)

    assert response.status_code == 204
    items = (await client.get(f"{API}/menu/items", headers=owner_headers)).json()
    assert [item["name"] for item in items] == ["Paneer Tikka"]


async def test_ordered_item_cannot_be_deleted(client: AsyncClient, menu, owner_headers) -> None:
    await bill_one_order(client, owner_headers, menu)

    response = await client.delete(f"{API}/menu/items/{menu['paneer_id']}", headers=owner_headers)

    assert response.status_code == 409
    assert "unavailable" in response.json()["detail"]


async def test_waiter_cannot_edit_or_delete_the_menu(client: AsyncClient, menu, make_staff) -> None:
    waiter = await make_staff("waiter")

    assert (await client.patch(f"{API}/menu/categories/{menu['category_id']}", headers=waiter, json={"name": "X"})).status_code == 403
    assert (await client.delete(f"{API}/menu/items/{menu['cola_id']}", headers=waiter)).status_code == 403
    assert (await client.delete(f"{API}/tables/{menu['table_id']}", headers=waiter)).status_code == 403


async def test_missing_records_return_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.patch(f"{API}/menu/categories/99", headers=owner_headers, json={"name": "X"})).status_code == 404
    assert (await client.delete(f"{API}/menu/categories/99", headers=owner_headers)).status_code == 404
    assert (await client.delete(f"{API}/menu/items/99", headers=owner_headers)).status_code == 404
    assert (await client.patch(f"{API}/tables/99", headers=owner_headers, json={"capacity": 2})).status_code == 404
    assert (await client.delete(f"{API}/tables/99", headers=owner_headers)).status_code == 404


async def test_table_can_be_renamed_and_resized(client: AsyncClient, menu, owner_headers) -> None:
    response = await client.patch(
        f"{API}/tables/{menu['table_id']}", headers=owner_headers, json={"name": "Window 1", "capacity": 6}
    )

    assert (response.json()["name"], response.json()["capacity"]) == ("Window 1", 6)


async def test_table_rename_cannot_clash(client: AsyncClient, menu, owner_headers) -> None:
    other = (await client.post(f"{API}/tables", headers=owner_headers, json={"name": "T2"})).json()

    response = await client.patch(f"{API}/tables/{other['id']}", headers=owner_headers, json={"name": "T1"})

    assert response.status_code == 409


async def test_table_with_open_order_cannot_be_deactivated(client: AsyncClient, menu, owner_headers) -> None:
    await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "dine_in", "table_id": menu["table_id"]}
    )

    response = await client.patch(f"{API}/tables/{menu['table_id']}", headers=owner_headers, json={"is_active": False})

    assert response.status_code == 409


async def test_deactivated_table_cannot_take_new_orders(client: AsyncClient, menu, owner_headers) -> None:
    await client.patch(f"{API}/tables/{menu['table_id']}", headers=owner_headers, json={"is_active": False})

    response = await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "dine_in", "table_id": menu["table_id"]}
    )

    assert response.status_code == 404


async def test_unused_table_can_be_deleted_but_used_one_cannot(client: AsyncClient, menu, owner_headers) -> None:
    spare = (await client.post(f"{API}/tables", headers=owner_headers, json={"name": "Spare"})).json()
    await client.post(
        f"{API}/orders", headers=owner_headers, json={"order_type": "dine_in", "table_id": menu["table_id"]}
    )

    assert (await client.delete(f"{API}/tables/{spare['id']}", headers=owner_headers)).status_code == 204
    assert (await client.delete(f"{API}/tables/{menu['table_id']}", headers=owner_headers)).status_code == 409


# ------------------------------------------------------ staff management


async def test_owner_can_list_staff(client: AsyncClient, owner_headers, make_staff) -> None:
    await make_staff("cashier")

    staff = (await client.get("/api/auth/users", headers=owner_headers)).json()

    assert [(u["email"], u["role"], u["is_active"]) for u in staff] == [
        ("owner@test.com", "owner", True),
        ("cashier@test.com", "cashier", True),
    ]
    assert "password_hash" not in staff[0]


async def test_only_owner_can_manage_staff(client: AsyncClient, make_staff) -> None:
    manager = await make_staff("manager")

    assert (await client.get("/api/auth/users", headers=manager)).status_code == 403
    assert (await client.patch("/api/auth/users/1", headers=manager, json={"name": "X"})).status_code == 403
    assert (await client.post("/api/auth/users/1/password", headers=manager, json={"password": "newpassword1"})).status_code == 403


async def test_staff_role_can_be_changed(client: AsyncClient, owner_headers, make_staff) -> None:
    await make_staff("waiter")

    response = await client.patch("/api/auth/users/2", headers=owner_headers, json={"role": "cashier"})

    assert response.json()["role"] == "cashier"


async def test_deactivated_staff_cannot_log_in_or_use_old_token(client: AsyncClient, owner_headers, make_staff) -> None:
    waiter = await make_staff("waiter")

    await client.patch("/api/auth/users/2", headers=owner_headers, json={"is_active": False})

    login = await client.post("/api/auth/login", json={"email": "waiter@test.com", "password": "password123"})
    assert login.status_code == 401
    assert (await client.get("/api/auth/me", headers=waiter)).status_code == 401


async def test_staff_can_be_reactivated(client: AsyncClient, owner_headers, make_staff) -> None:
    await make_staff("waiter")
    await client.patch("/api/auth/users/2", headers=owner_headers, json={"is_active": False})

    await client.patch("/api/auth/users/2", headers=owner_headers, json={"is_active": True})

    login = await client.post("/api/auth/login", json={"email": "waiter@test.com", "password": "password123"})
    assert login.status_code == 200


async def test_owner_cannot_deactivate_or_demote_themselves(client: AsyncClient, owner_headers) -> None:
    deactivate = await client.patch("/api/auth/users/1", headers=owner_headers, json={"is_active": False})
    demote = await client.patch("/api/auth/users/1", headers=owner_headers, json={"role": "manager"})

    assert deactivate.status_code == 409
    assert demote.status_code == 409


async def test_last_active_owner_cannot_be_removed_by_another_owner(client: AsyncClient, owner_headers, make_staff) -> None:
    await make_staff("manager")
    await client.patch("/api/auth/users/2", headers=owner_headers, json={"role": "owner"})
    second_owner = await client.post("/api/auth/login", json={"email": "manager@test.com", "password": "password123"})
    headers = {"Authorization": f"Bearer {second_owner.json()['access_token']}"}

    # With two owners, one may deactivate the other...
    assert (await client.patch("/api/auth/users/1", headers=headers, json={"is_active": False})).status_code == 200
    # ...but then no one can remove the only remaining owner.
    assert (await client.patch("/api/auth/users/2", headers=headers, json={"role": "waiter"})).status_code == 409


async def test_password_can_be_reset(client: AsyncClient, owner_headers, make_staff) -> None:
    await make_staff("cashier")

    reset = await client.post("/api/auth/users/2/password", headers=owner_headers, json={"password": "brand-new-pass"})

    assert reset.status_code == 204
    old = await client.post("/api/auth/login", json={"email": "cashier@test.com", "password": "password123"})
    new = await client.post("/api/auth/login", json={"email": "cashier@test.com", "password": "brand-new-pass"})
    assert (old.status_code, new.status_code) == (401, 200)


async def test_short_reset_password_is_rejected(client: AsyncClient, owner_headers, make_staff) -> None:
    await make_staff("cashier")

    response = await client.post("/api/auth/users/2/password", headers=owner_headers, json={"password": "short"})

    assert response.status_code == 422


async def test_unknown_staff_member_returns_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.patch("/api/auth/users/99", headers=owner_headers, json={"name": "X"})).status_code == 404
    assert (await client.post("/api/auth/users/99/password", headers=owner_headers, json={"password": "longenough1"})).status_code == 404
