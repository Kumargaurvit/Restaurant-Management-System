from httpx import AsyncClient

API = "/api/billing"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def place_order(
    client: AsyncClient, headers, menu, items: dict[str, int], phone=None, name=None, bill=True
) -> dict:
    """Create a takeaway order for a customer, add items by key (paneer/cola), optionally bill."""
    body = {"order_type": "takeaway"}
    if phone:
        body["customer_phone"] = phone
    if name:
        body["customer_name"] = name
    order = (await client.post(f"{API}/orders", headers=headers, json=body)).json()
    for key, quantity in items.items():
        await client.post(
            f"{API}/orders/{order['id']}/items",
            headers=headers,
            json={"menu_item_id": menu[f"{key}_id"], "quantity": quantity},
        )
    if not bill:
        return order
    response = await client.post(f"{API}/orders/{order['id']}/bill", headers=headers, json={})
    return response.json()
