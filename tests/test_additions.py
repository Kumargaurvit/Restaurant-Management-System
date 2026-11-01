import base64
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from restaurant_management_system.chatbot.service import RATE_LIMIT_REPLY
from restaurant_management_system.config import get_settings
from restaurant_management_system.logging_config import JsonFormatter, configure_logging
from restaurant_management_system.messaging.models import Message
from restaurant_management_system.messaging.provider import get_provider
from tests.fakes import RecordingProvider, ScriptedLLM, say
from tests.fakes import call as tool_call
from tests.helpers import place_order

API = "/api/billing"
PROFILE_URL = "/api/restaurant/profile"
GUEST = "9810000001"


def data_url(kind: str, payload: bytes) -> str:
    magic = {
        "png": b"\x89PNG\r\n\x1a\n",
        "jpeg": b"\xff\xd8\xff\xe0",
        "webp": b"RIFF\x00\x00\x00\x00WEBP",
    }[kind]
    return f"data:image/{kind};base64," + base64.b64encode(magic + payload).decode()


@pytest.fixture
def provider(app) -> RecordingProvider:
    recorder = RecordingProvider()
    app.dependency_overrides[get_provider] = lambda: recorder
    return recorder


# ------------------------------------------------------------------- logo


@pytest.mark.parametrize("kind", ["png", "jpeg", "webp"])
async def test_a_small_raster_logo_can_be_saved_and_read_back(client: AsyncClient, owner_headers, kind) -> None:
    logo = data_url(kind, b"x" * 50)

    saved = await client.put(PROFILE_URL, headers=owner_headers, json={"logo": logo})
    read = await client.get(PROFILE_URL, headers=owner_headers)

    assert saved.status_code == 200
    assert read.json()["logo"] == logo


async def test_the_logo_can_be_removed(client: AsyncClient, owner_headers) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json={"logo": data_url("png", b"x" * 20)})

    await client.put(PROFILE_URL, headers=owner_headers, json={"logo": ""})

    assert (await client.get(PROFILE_URL, headers=owner_headers)).json()["logo"] == ""


@pytest.mark.parametrize(
    ("logo", "fragment"),
    [
        ("data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)/>").decode(), "PNG, JPEG or WebP"),
        ("https://example.com/logo.png", "PNG, JPEG or WebP"),
        ("data:image/png;base64,@@@@", "PNG, JPEG or WebP"),
        ("data:image/png;base64," + base64.b64encode(b"just text, not a png").decode(), "does not match"),
        ("data:image/jpeg;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nxxxx").decode(), "does not match"),
        ("data:image/webp;base64," + base64.b64encode(b"RIFF\x00\x00\x00\x00JUNKxxxx").decode(), "does not match"),
    ],
)
async def test_non_images_and_disguised_files_are_rejected(client: AsyncClient, owner_headers, logo, fragment) -> None:
    response = await client.put(PROFILE_URL, headers=owner_headers, json={"logo": logo})

    assert response.status_code == 422
    assert fragment in response.text


async def test_an_oversized_logo_is_rejected(client: AsyncClient, owner_headers) -> None:
    response = await client.put(PROFILE_URL, headers=owner_headers, json={"logo": data_url("png", b"x" * 110_000)})

    assert response.status_code == 422
    assert "too large" in response.text or "String should have at most" in response.text


async def test_staff_can_read_the_logo_but_not_change_it(client: AsyncClient, owner_headers, make_staff) -> None:
    logo = data_url("png", b"x" * 20)
    await client.put(PROFILE_URL, headers=owner_headers, json={"logo": logo})
    waiter = await make_staff("waiter")

    assert (await client.get(PROFILE_URL, headers=waiter)).json()["logo"] == logo
    assert (await client.put(PROFILE_URL, headers=waiter, json={"logo": ""})).status_code == 403


async def test_saving_details_without_a_logo_field_clears_nothing_else(client: AsyncClient, owner_headers) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json={"address": "12 CP", "logo": data_url("png", b"x" * 20)})

    read = (await client.get(PROFILE_URL, headers=owner_headers)).json()

    assert read["address"] == "12 CP"
    assert read["logo"].startswith("data:image/png")


# ------------------------------------------------------- send a bill on WhatsApp


async def test_a_bill_is_sent_to_the_guest_on_the_order(client: AsyncClient, menu, owner_headers, provider) -> None:
    await client.put(PROFILE_URL, headers=owner_headers, json={"address": "12 CP, Delhi", "gstin": "07AAAAA0000A1Z5"})
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone="+91 98100 00001", name="Asha")

    response = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={})

    assert response.status_code == 200
    assert response.json() == {"phone": GUEST, "status": "sent"}
    phone, text = provider.sent[0]
    assert phone == GUEST
    assert "Spice Garden" in text
    assert text.count("```") == 2
    for expected in (bill["invoice_number"], "Paneer Tikka", "GSTIN: 07AAAAA0000A1Z5", "12 CP, Delhi", "210.00"):
        assert expected in text


async def test_the_message_is_logged_as_a_bill(client: AsyncClient, menu, owner_headers, provider, engine) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)

    await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={})

    async with async_sessionmaker(engine)() as session:
        rows = (await session.scalars(select(Message))).all()
    assert [(m.direction, m.kind, m.status, m.phone) for m in rows] == [("out", "bill", "sent", GUEST)]


async def test_a_bill_can_be_sent_to_a_different_number(client: AsyncClient, menu, owner_headers, provider) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)

    response = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={"phone": "98100 00002"})

    assert response.json()["phone"] == "9810000002"
    assert provider.sent[0][0] == "9810000002"


async def test_a_bill_with_no_number_needs_one_to_be_given(client: AsyncClient, menu, owner_headers, provider) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1})

    refused = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={})
    allowed = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={"phone": GUEST})

    assert refused.status_code == 409
    assert allowed.status_code == 200


async def test_an_invalid_number_is_rejected(client: AsyncClient, menu, owner_headers, provider) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)

    response = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={"phone": "123"})

    assert response.status_code == 422
    assert provider.sent == []


async def test_a_provider_failure_is_reported_and_logged(app, client: AsyncClient, menu, owner_headers, engine) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    app.dependency_overrides[get_provider] = lambda: RecordingProvider(fail=True)

    response = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={})

    assert response.status_code == 502
    async with async_sessionmaker(engine)() as session:
        rows = (await session.scalars(select(Message))).all()
    assert [(m.kind, m.status) for m in rows] == [("bill", "failed")]


async def test_sending_a_bill_ignores_the_marketing_opt_out(client: AsyncClient, menu, owner_headers, provider) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    customer = (await client.get("/api/customers", headers=owner_headers)).json()[0]
    await client.put(f"/api/customers/{customer['id']}/marketing-opt-out", headers=owner_headers, json={"opt_out": True})

    response = await client.post(f"{API}/bills/{bill['id']}/send", headers=owner_headers, json={})

    assert response.status_code == 200
    assert len(provider.sent) == 1


async def test_cashier_can_send_but_waiter_cannot(client: AsyncClient, menu, owner_headers, make_staff, provider) -> None:
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    cashier = await make_staff("cashier")
    waiter = await make_staff("waiter")

    assert (await client.post(f"{API}/bills/{bill['id']}/send", headers=cashier, json={})).status_code == 200
    assert (await client.post(f"{API}/bills/{bill['id']}/send", headers=waiter, json={})).status_code == 403


async def test_sending_a_missing_bill_is_404(client: AsyncClient, owner_headers, provider) -> None:
    assert (await client.post(f"{API}/bills/99/send", headers=owner_headers, json={})).status_code == 404


# --------------------------------------------------- bot: restaurant information


@pytest.fixture
def use_llm(app):
    from restaurant_management_system.chatbot.llm import get_optional_llm

    def _use(llm):
        app.dependency_overrides[get_optional_llm] = lambda: llm
        return llm

    return _use


async def ask(client: AsyncClient, headers, text="hi", phone=GUEST):
    return await client.post("/api/chat/simulate", headers=headers, json={"phone": phone, "text": text})


async def test_the_bot_can_give_the_address_phone_and_hours(client: AsyncClient, owner_headers, use_llm, monkeypatch) -> None:
    from restaurant_management_system.chatbot import service

    await client.put(PROFILE_URL, headers=owner_headers, json={"address": "12 CP, Delhi", "phone": "011 4000 1234"})
    monkeypatch.setattr(service, "utcnow", lambda: datetime(2026, 11, 2, 8, 30, tzinfo=UTC))  # 2 pm in Delhi
    llm = use_llm(ScriptedLLM(tool_call("get_restaurant_info"), say("We're open until 11 pm")))

    await ask(client, owner_headers, "are you open?")

    info = llm.last_tool_result
    assert info == {
        "name": "Spice Garden",
        "address": "12 CP, Delhi",
        "phone": "011 4000 1234",
        "opens_at": "11:00",
        "closes_at": "23:00",
        "open_now": True,
        "local_time_now": "14:00",
    }


async def test_the_bot_knows_when_the_restaurant_is_closed(client: AsyncClient, owner_headers, use_llm, monkeypatch) -> None:
    from restaurant_management_system.chatbot import service

    monkeypatch.setattr(service, "utcnow", lambda: datetime(2026, 11, 2, 18, 0, tzinfo=UTC))  # 11:30 pm
    llm = use_llm(ScriptedLLM(tool_call("get_restaurant_info"), say("We are closed")))

    await ask(client, owner_headers, "open now?")

    assert llm.last_tool_result["open_now"] is False


async def test_unsaved_details_are_reported_as_missing_not_blank(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("get_restaurant_info"), say("ok")))

    await ask(client, owner_headers, "where are you?")

    assert llm.last_tool_result["address"] is None
    assert llm.last_tool_result["phone"] is None


# ------------------------------------------------------------------- rate limit


@pytest.fixture
def limit_of_three(monkeypatch):
    monkeypatch.setenv("CHAT_MAX_MESSAGES_PER_HOUR", "3")
    get_settings.cache_clear()


async def test_a_guest_over_the_hourly_limit_gets_a_notice_and_no_model_call(
    client: AsyncClient, owner_headers, use_llm, limit_of_three
) -> None:
    llm = use_llm(ScriptedLLM(say("1"), say("2"), say("3")))

    replies = [(await ask(client, owner_headers, f"message {n}")).json()["reply"] for n in range(5)]

    assert replies[:3] == ["1", "2", "3"]
    assert replies[3:] == [RATE_LIMIT_REPLY, RATE_LIMIT_REPLY]
    assert len(llm.requests) == 3  # the model was never asked about the extra messages


async def test_rate_limited_messages_are_not_stored(client: AsyncClient, owner_headers, use_llm, limit_of_three) -> None:
    use_llm(ScriptedLLM(say("1"), say("2"), say("3")))
    for n in range(6):
        await ask(client, owner_headers, f"message {n}")

    conversation = (await client.get("/api/chat/conversations", headers=owner_headers)).json()[0]

    assert conversation["message_count"] == 6  # 3 guest messages and 3 replies, nothing from the flood


async def test_the_limit_is_per_guest(client: AsyncClient, owner_headers, use_llm, limit_of_three) -> None:
    use_llm(ScriptedLLM(*[say(str(n)) for n in range(4)]))
    for n in range(3):
        await ask(client, owner_headers, f"m{n}", phone=GUEST)

    other = await ask(client, owner_headers, "hello", phone="9810000002")

    assert other.json()["reply"] == "3"


async def test_a_limit_of_zero_means_no_limit(client: AsyncClient, owner_headers, use_llm, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MAX_MESSAGES_PER_HOUR", "0")
    get_settings.cache_clear()
    use_llm(ScriptedLLM(*[say("ok") for _ in range(40)]))

    replies = {(await ask(client, owner_headers, f"m{n}")).json()["reply"] for n in range(40)}

    assert replies == {"ok"}


async def test_the_default_limit_allows_normal_use(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(*[say("ok") for _ in range(10)]))

    replies = {(await ask(client, owner_headers, f"m{n}")).json()["reply"] for n in range(10)}

    assert replies == {"ok"}


# ------------------------------------------------------------------- logging


def make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_log_lines_are_valid_json_with_the_structured_fields() -> None:
    line = JsonFormatter().format(make_record(request_id="abc", method="GET", path="/health", status=200, duration_ms=3.2))

    data = json.loads(line)
    assert data["message"] == "hello world"
    assert (data["level"], data["logger"]) == ("INFO", "app.test")
    assert (data["request_id"], data["method"], data["path"], data["status"], data["duration_ms"]) == ("abc", "GET", "/health", 200, 3.2)
    assert data["time"].endswith("+00:00")


def test_json_logs_carry_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())

    assert "ValueError: boom" in json.loads(JsonFormatter().format(record))["exception"]


def test_extra_fields_that_are_not_ours_are_not_logged() -> None:
    data = json.loads(JsonFormatter().format(make_record(password="secret", phone="9810000001")))

    assert "password" not in data and "phone" not in data


def test_configuring_logging_twice_keeps_a_single_handler() -> None:
    configure_logging("INFO", "json")
    configure_logging("DEBUG", "text")

    ours = [h for h in logging.getLogger().handlers if getattr(h, "_rms_handler", False)]
    assert len(ours) == 1
    assert logging.getLogger().level == logging.DEBUG
    configure_logging("INFO", "text")


def test_an_unknown_log_level_falls_back_to_info() -> None:
    configure_logging("LOUD", "text")

    assert logging.getLogger().level == logging.INFO


async def test_each_request_is_logged_without_its_query_string(client: AsyncClient, owner_headers, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.requests"):
        await client.get("/api/customers/lookup?phone=9810000001", headers=owner_headers)

    record = next(r for r in caplog.records if r.name == "app.requests")
    assert (record.method, record.path, record.status) == ("GET", "/api/customers/lookup", 404)
    assert record.duration_ms >= 0
    assert "9810000001" not in record.getMessage()
    assert not hasattr(record, "query")


async def test_every_response_has_a_request_id(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")

    assert len(first.headers["x-request-id"]) == 12
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_the_request_id_matches_the_logged_one(client: AsyncClient, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.requests"):
        response = await client.get("/health")

    record = next(r for r in caplog.records if r.name == "app.requests")
    assert record.request_id == response.headers["x-request-id"]


# ------------------------------------------- the report's day follows the restaurant's clock


async def test_daily_report_uses_the_restaurant_day_not_the_utc_day(
    client: AsyncClient, menu, owner_headers, engine
) -> None:
    """19:00 UTC on 10 June is 00:30 on 11 June in Delhi, so the bill belongs to 11 June."""
    from sqlalchemy import update

    from restaurant_management_system.billing.models import Bill, Payment

    bill = await place_order(client, owner_headers, menu, {"paneer": 1})
    await client.post(f"{API}/bills/{bill['id']}/payments", headers=owner_headers, json={"mode": "cash", "amount": "210"})
    moment = datetime(2026, 6, 10, 19, 0, tzinfo=UTC)
    async with async_sessionmaker(engine)() as session:
        await session.execute(update(Bill).where(Bill.id == bill["id"]).values(created_at=moment))
        await session.execute(update(Payment).where(Payment.bill_id == bill["id"]).values(created_at=moment))
        await session.commit()

    eleventh = (await client.get(f"{API}/reports/daily?day=2026-06-11", headers=owner_headers)).json()
    tenth = (await client.get(f"{API}/reports/daily?day=2026-06-10", headers=owner_headers)).json()

    assert (eleventh["bill_count"], eleventh["total_sales"], eleventh["cash"]) == (1, "210.00", "210.00")
    assert tenth["bill_count"] == 0
    assert Decimal(tenth["total_sales"]) == 0


async def test_a_bill_just_before_restaurant_midnight_stays_on_that_day(
    client: AsyncClient, menu, owner_headers, engine
) -> None:
    """18:29 UTC is 23:59 in Delhi: still the earlier day."""
    from sqlalchemy import update

    from restaurant_management_system.billing.models import Bill

    bill = await place_order(client, owner_headers, menu, {"paneer": 1})
    async with async_sessionmaker(engine)() as session:
        await session.execute(
            update(Bill).where(Bill.id == bill["id"]).values(created_at=datetime(2026, 6, 10, 18, 29, tzinfo=UTC))
        )
        await session.commit()

    tenth = (await client.get(f"{API}/reports/daily?day=2026-06-10", headers=owner_headers)).json()
    eleventh = (await client.get(f"{API}/reports/daily?day=2026-06-11", headers=owner_headers)).json()

    assert (tenth["bill_count"], eleventh["bill_count"]) == (1, 0)


def test_http_client_libraries_are_kept_quiet() -> None:
    configure_logging("INFO", "text")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
