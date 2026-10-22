from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from restaurant_management_system.billing.models import Bill
from restaurant_management_system.config import get_settings
from restaurant_management_system.messaging.provider import get_provider
from restaurant_management_system.retention.models import RetentionSettings
from restaurant_management_system.retention.services import (
    classify,
    frequency_score,
    monetary_score,
    recency_score,
)
from tests.test_customers import place_order

API = "/api/retention"

DEFAULTS = RetentionSettings(at_risk_days=45, lost_days=90)


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


async def age_bill(engine: AsyncEngine, bill_id: int, days: int) -> None:
    async with async_sessionmaker(engine)() as session:
        await session.execute(
            update(Bill).where(Bill.id == bill_id).values(created_at=datetime.now(UTC) - timedelta(days=days))
        )
        await session.commit()


async def make_rule(client: AsyncClient, headers, **overrides) -> dict:
    body = {
        "name": "Win back",
        "segment": "at_risk",
        "template": "Hi {name}, we miss you at {restaurant}!",
        "mode": "approval",
        "cooldown_days": 30,
        **overrides,
    }
    response = await client.post(f"{API}/rules", headers=headers, json=body)
    assert response.status_code == 201
    return response.json()


# ------------------------------------------------------------ pure logic


@pytest.mark.parametrize(
    ("visits", "spent", "days", "expected"),
    [
        (1, "300", 3, "new"),
        (3, "900", 10, "regular"),
        (6, "7000", 10, "regular"),
        (6, "7000", 50, "at_risk"),  # a frequent guest who stopped coming is at risk
        (2, "400", 45, "at_risk"),
        (2, "400", 90, "lost"),
        (6, "2000", 5, "regular"),  # frequent but under the spend threshold
    ],
)
def test_classify(visits: int, spent: str, days: int, expected: str) -> None:
    assert classify(visits, Decimal(spent), days, DEFAULTS) == expected


def test_rfm_scores_run_from_one_to_five() -> None:
    assert (recency_score(1), recency_score(20), recency_score(200)) == (5, 4, 1)
    assert (frequency_score(1), frequency_score(3), frequency_score(12)) == (1, 3, 5)
    assert (monetary_score(Decimal("100")), monetary_score(Decimal("9000"))) == (1, 5)


# -------------------------------------------------------------- settings


async def test_thresholds_are_owner_configurable(client: AsyncClient, owner_headers) -> None:
    current = (await client.get(f"{API}/settings", headers=owner_headers)).json()
    assert current["at_risk_days"] == 45

    assert set(current) == {"at_risk_days", "lost_days"}
    changed = {**current, "at_risk_days": 20, "lost_days": 60}
    assert (await client.put(f"{API}/settings", headers=owner_headers, json=changed)).status_code == 200
    bad = {**current, "at_risk_days": 60, "lost_days": 30}
    assert (await client.put(f"{API}/settings", headers=owner_headers, json=bad)).status_code == 422


async def test_retention_is_owner_and_manager_only(
    client: AsyncClient, owner_headers, make_staff
) -> None:
    cashier = await make_staff("cashier")
    assert (await client.get(f"{API}/segments", headers=cashier)).status_code == 403
    assert (await client.get(f"{API}/segments")).status_code == 401
    manager = await make_staff("manager")
    assert (await client.get(f"{API}/segments", headers=manager)).status_code == 200


# -------------------------------------------------------------- segments


async def test_segments_list_customers_with_scores(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000002", name="Bala")
    await age_bill(engine, old["id"], 60)

    result = (await client.get(f"{API}/segments", headers=owner_headers)).json()

    counts = {row["segment"]: row["customers"] for row in result["summary"]}
    assert counts == {"regular": 0, "new": 1, "at_risk": 1, "lost": 0}
    asha = next(m for m in result["members"] if m["name"] == "Asha")
    assert asha["segment"] == "at_risk"
    assert asha["days_since_visit"] == 60
    assert asha["recency_score"] == 3

    only_new = (await client.get(f"{API}/segments?segment=new", headers=owner_headers)).json()
    assert [m["name"] for m in only_new["members"]] == ["Bala"]


async def test_customers_without_bills_are_not_segmented(
    client: AsyncClient, menu, owner_headers
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", bill=False)
    result = (await client.get(f"{API}/segments", headers=owner_headers)).json()
    assert result["members"] == []


# ----------------------------------------------------------------- rules


async def test_rule_crud(client: AsyncClient, owner_headers) -> None:
    rule = await make_rule(client, owner_headers)
    updated = await client.put(
        f"{API}/rules/{rule['id']}", headers=owner_headers, json={**rule, "mode": "automatic"}
    )
    assert updated.json()["mode"] == "automatic"

    assert (await client.delete(f"{API}/rules/{rule['id']}", headers=owner_headers)).status_code == 204
    rules = (await client.get(f"{API}/rules", headers=owner_headers)).json()
    assert rules[0]["is_active"] is False
    assert (await client.put(f"{API}/rules/99", headers=owner_headers, json=rule)).status_code == 404


async def test_rule_rejects_unknown_segment_and_mode(client: AsyncClient, owner_headers) -> None:
    base = {"name": "x", "template": "hi"}
    for bad in ({"segment": "whales", "mode": "approval"}, {"segment": "vip", "mode": "approval"}):
        response = await client.post(f"{API}/rules", headers=owner_headers, json={**base, **bad})
        assert response.status_code == 422


# -------------------------------------------------------- approval queue


async def test_approval_rule_queues_then_sends_on_approve(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    await age_bill(engine, old["id"], 60)
    await make_rule(client, owner_headers)

    run = (await client.post(f"{API}/run", headers=owner_headers)).json()
    assert run == {"rules_run": 1, "queued": 1, "sent": 0, "skipped_cooldown": 0}
    assert provider.sent == []  # nothing goes out before approval

    queue = (await client.get(f"{API}/messages?status=pending", headers=owner_headers)).json()
    assert len(queue) == 1
    assert queue[0]["customer_name"] == "Asha"
    assert queue[0]["body"].startswith("Hi Asha, we miss you at")
    assert "Reply STOP to opt out." in queue[0]["body"]

    approved = (await client.post(f"{API}/messages/{queue[0]['id']}/approve", headers=owner_headers)).json()
    assert approved["status"] == "sent"
    assert provider.sent[0][0] == "9000000001"

    again = await client.post(f"{API}/messages/{queue[0]['id']}/approve", headers=owner_headers)
    assert again.status_code == 409


async def test_rejected_message_is_not_sent_or_requeued(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")
    await age_bill(engine, old["id"], 60)
    await make_rule(client, owner_headers)
    await client.post(f"{API}/run", headers=owner_headers)
    queued = (await client.get(f"{API}/messages", headers=owner_headers)).json()[0]

    rejected = (await client.post(f"{API}/messages/{queued['id']}/reject", headers=owner_headers)).json()
    rerun = (await client.post(f"{API}/run", headers=owner_headers)).json()

    assert rejected["status"] == "rejected"
    assert provider.sent == []
    assert rerun["queued"] == 0
    assert rerun["skipped_cooldown"] == 1


async def test_automatic_rule_sends_immediately(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    await age_bill(engine, old["id"], 100)
    await make_rule(client, owner_headers, segment="lost", mode="automatic")

    run = (await client.post(f"{API}/run", headers=owner_headers)).json()

    assert run["sent"] == 1
    assert run["queued"] == 0
    assert len(provider.sent) == 1


async def test_cooldown_stops_repeat_messages(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")
    await age_bill(engine, old["id"], 100)
    await make_rule(client, owner_headers, segment="lost", mode="automatic")

    await client.post(f"{API}/run", headers=owner_headers)
    second = (await client.post(f"{API}/run", headers=owner_headers)).json()

    assert second["sent"] == 0
    assert second["skipped_cooldown"] == 1
    assert len(provider.sent) == 1


async def test_only_matching_segment_is_messaged(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")  # new
    await make_rule(client, owner_headers, segment="lost", mode="automatic")

    run = (await client.post(f"{API}/run", headers=owner_headers)).json()

    assert run["sent"] == 0
    assert provider.sent == []


async def test_inactive_rule_does_not_run(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")
    await age_bill(engine, old["id"], 100)
    await make_rule(client, owner_headers, segment="lost", mode="automatic", is_active=False)

    run = (await client.post(f"{API}/run", headers=owner_headers)).json()

    assert run["rules_run"] == 0
    assert provider.sent == []


# ---------------------------------------------------------------- opt-out


async def test_opted_out_customers_get_nothing(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")
    await age_bill(engine, old["id"], 100)
    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    await client.put(
        f"/api/customers/{customer['id']}/marketing-opt-out", headers=owner_headers, json={"opt_out": True}
    )
    await make_rule(client, owner_headers, segment="lost", mode="automatic")

    run = (await client.post(f"{API}/run", headers=owner_headers)).json()

    assert run["sent"] == 0
    assert provider.sent == []
    segments = (await client.get(f"{API}/segments", headers=owner_headers)).json()
    assert segments["members"][0]["marketing_opt_out"] is True


async def test_opt_out_while_queued_skips_the_message(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")
    await age_bill(engine, old["id"], 100)
    await make_rule(client, owner_headers, segment="lost")
    await client.post(f"{API}/run", headers=owner_headers)
    queued = (await client.get(f"{API}/messages", headers=owner_headers)).json()[0]
    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    await client.put(
        f"/api/customers/{customer['id']}/marketing-opt-out", headers=owner_headers, json={"opt_out": True}
    )

    result = (await client.post(f"{API}/messages/{queued['id']}/approve", headers=owner_headers)).json()

    assert result["status"] == "skipped"
    assert provider.sent == []


# ---------------------------------------------------------------- inbound


@pytest.fixture
def webhook_secret(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("WHATSAPP_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    return {"X-Webhook-Secret": "s3cret"}


async def test_inbound_requires_the_secret(client: AsyncClient, webhook_secret) -> None:
    body = {"phone": "9000000001", "text": "hi"}
    assert (await client.post("/api/messaging/inbound", json=body)).status_code == 401
    wrong = await client.post("/api/messaging/inbound", json=body, headers={"X-Webhook-Secret": "no"})
    assert wrong.status_code == 401


async def test_inbound_is_disabled_without_a_configured_secret(client: AsyncClient) -> None:
    response = await client.post("/api/messaging/inbound", json={"phone": "9000000001", "text": "hi"})
    assert response.status_code == 401


async def test_stop_and_start_replies_toggle_the_opt_out(
    client: AsyncClient, owner_headers, webhook_secret, provider: FakeProvider
) -> None:
    url = "/api/messaging/inbound"
    stop = await client.post(url, headers=webhook_secret, json={"phone": "+91 90000 00001", "text": "STOP"})
    assert stop.json() == {"action": "opted_out"}
    assert "no longer" in provider.sent[0][1]

    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    assert customer["marketing_opt_out"] is True

    start = await client.post(url, headers=webhook_secret, json={"phone": "9000000001", "text": "start"})
    assert start.json() == {"action": "opted_in"}
    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    assert customer["marketing_opt_out"] is False


# ----------------------------------------------------------------- report


async def test_report_counts_replies_and_return_visits(
    client: AsyncClient, menu, owner_headers, engine: AsyncEngine, provider: FakeProvider, webhook_secret
) -> None:
    old = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001", name="Asha")
    quiet = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000002", name="Bala")
    await age_bill(engine, old["id"], 100)
    await age_bill(engine, quiet["id"], 100)
    await make_rule(client, owner_headers, segment="lost", mode="automatic")
    await client.post(f"{API}/run", headers=owner_headers)

    # Asha replies, then comes back and is billed again.
    await client.post(
        "/api/messaging/inbound", headers=webhook_secret, json={"phone": "9000000001", "text": "Table for 2?"}
    )
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone="9000000001")

    report = (await client.get(f"{API}/report", headers=owner_headers)).json()

    assert len(report) == 1
    assert report[0]["sent"] == 2
    assert report[0]["replied"] == 1
    assert report[0]["visited_after"] == 1
    assert report[0]["pending"] == 0
