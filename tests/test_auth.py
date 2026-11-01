from httpx import AsyncClient

from tests.helpers import bearer

SETUP = {
    "name": "Owner",
    "email": "Owner@Test.com",
    "password": "password123",
    "restaurant_name": "Spice Garden",
}


async def test_status_reports_no_users_before_setup(client: AsyncClient) -> None:
    response = await client.get("/api/auth/status")

    assert response.json() == {"has_users": False}


async def test_bootstrap_creates_owner_and_returns_token(client: AsyncClient) -> None:
    response = await client.post("/api/auth/bootstrap", json=SETUP)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == "owner"
    assert body["user"]["email"] == "owner@test.com"
    assert (await client.get("/api/auth/status")).json() == {"has_users": True}


async def test_bootstrap_only_works_once(client: AsyncClient) -> None:
    await client.post("/api/auth/bootstrap", json=SETUP)

    response = await client.post("/api/auth/bootstrap", json=SETUP)

    assert response.status_code == 409


async def test_bootstrap_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post("/api/auth/bootstrap", json={**SETUP, "password": "short"})

    assert response.status_code == 422


async def test_login_succeeds_with_correct_password(client: AsyncClient) -> None:
    await client.post("/api/auth/bootstrap", json=SETUP)

    response = await client.post(
        "/api/auth/login", json={"email": "owner@test.com", "password": "password123"}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_login_fails_with_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/auth/bootstrap", json=SETUP)

    response = await client.post(
        "/api/auth/login", json={"email": "owner@test.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


async def test_login_fails_for_unknown_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": "nobody@test.com", "password": "password123"}
    )

    assert response.status_code == 401


async def test_me_requires_a_token(client: AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_rejects_a_garbage_token(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me", headers=bearer("not-a-real-token"))

    assert response.status_code == 401


async def test_me_returns_current_user(client: AsyncClient, owner_headers) -> None:
    response = await client.get("/api/auth/me", headers=owner_headers)

    assert response.json()["email"] == "owner@test.com"


async def test_owner_can_create_staff(client: AsyncClient, owner_headers) -> None:
    response = await client.post(
        "/api/auth/users",
        headers=owner_headers,
        json={"name": "Cash", "email": "cash@test.com", "password": "password123", "role": "cashier"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "cashier"


async def test_staff_email_must_be_unique(client: AsyncClient, owner_headers) -> None:
    body = {"name": "Cash", "email": "cash@test.com", "password": "password123", "role": "cashier"}
    await client.post("/api/auth/users", headers=owner_headers, json=body)

    response = await client.post("/api/auth/users", headers=owner_headers, json=body)

    assert response.status_code == 409


async def test_non_owner_cannot_create_staff(client: AsyncClient, make_staff) -> None:
    manager = await make_staff("manager")

    response = await client.post(
        "/api/auth/users",
        headers=manager,
        json={"name": "X", "email": "x@test.com", "password": "password123", "role": "waiter"},
    )

    assert response.status_code == 403


async def test_bootstrap_requires_a_restaurant_name(client: AsyncClient) -> None:
    for bad in ({"restaurant_name": ""}, {"restaurant_name": "   "}):
        response = await client.post("/api/auth/bootstrap", json={**SETUP, **bad})
        assert response.status_code == 422
    missing = {key: value for key, value in SETUP.items() if key != "restaurant_name"}
    assert (await client.post("/api/auth/bootstrap", json=missing)).status_code == 422


async def test_restaurant_name_comes_back_with_the_user(client: AsyncClient) -> None:
    setup = await client.post("/api/auth/bootstrap", json=SETUP)
    assert setup.json()["user"]["restaurant_name"] == "Spice Garden"

    login = await client.post(
        "/api/auth/login", json={"email": "owner@test.com", "password": "password123"}
    )
    assert login.json()["user"]["restaurant_name"] == "Spice Garden"
    me = await client.get("/api/auth/me", headers=bearer(login.json()["access_token"]))
    assert me.json()["restaurant_name"] == "Spice Garden"


async def test_only_the_owner_can_rename_the_restaurant(client: AsyncClient, owner_headers, make_staff) -> None:
    manager = await make_staff("manager")

    assert (await client.get("/api/restaurant", headers=manager)).json() == {"name": "Spice Garden"}
    assert (await client.put("/api/restaurant", headers=manager, json={"name": "X"})).status_code == 403
    renamed = await client.put("/api/restaurant", headers=owner_headers, json={"name": " Dilli Darbar "})
    assert renamed.json() == {"name": "Dilli Darbar"}
    me = await client.get("/api/auth/me", headers=owner_headers)
    assert me.json()["restaurant_name"] == "Dilli Darbar"
    assert (await client.put("/api/restaurant", headers=owner_headers, json={"name": "  "})).status_code == 422
