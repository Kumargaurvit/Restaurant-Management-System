import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from restaurant_management_system.chatbot import tools as tools_module
from restaurant_management_system.chatbot.llm import (
    LLMUnavailableError,
    OpenAIClient,
    get_llm_client,
    get_optional_llm,
)
from restaurant_management_system.chatbot.service import FALLBACK_REPLY
from restaurant_management_system.config import get_settings
from restaurant_management_system.messaging.factory import get_provider
from tests.fakes import RecordingProvider, ScriptedLLM, calls, say, unavailable
from tests.fakes import call as tool_call
from tests.helpers import place_order

GUEST = "9810000001"
OTHER = "9810000002"


def iso(delta_hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=delta_hours)).isoformat()


@pytest.fixture
def provider(app) -> RecordingProvider:
    recorder = RecordingProvider()
    app.dependency_overrides[get_provider] = lambda: recorder
    return recorder


@pytest.fixture
def use_llm(app):
    def _use(llm):
        app.dependency_overrides[get_optional_llm] = lambda: llm
        return llm

    return _use


@pytest.fixture
def webhook_secret(monkeypatch) -> str:
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    return "s3cret"


async def ask(client: AsyncClient, headers, text="hello", phone=GUEST):
    return await client.post("/api/chat/simulate", headers=headers, json={"phone": phone, "text": text})


async def add_offer(client: AsyncClient, headers, **fields) -> None:
    body = {"title": "Lunch deal", "description": "On mains", "discount_percent": "15", **fields}
    assert (await client.post("/api/offers", headers=headers, json=body)).status_code == 201


# ----------------------------------------------------------- basic flow


async def test_reply_is_returned_and_the_exchange_is_stored(
    client: AsyncClient, owner_headers, use_llm
) -> None:
    use_llm(ScriptedLLM(say("Hi! How can I help?")))

    response = await ask(client, owner_headers, "hello")

    assert response.json() == {"reply": "Hi! How can I help?", "needs_human": False}
    conversations = (await client.get("/api/chat/conversations", headers=owner_headers)).json()
    detail = (await client.get(f"/api/chat/conversations/{conversations[0]['id']}", headers=owner_headers)).json()
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "hello"),
        ("assistant", "Hi! How can I help?"),
    ]


async def test_model_receives_system_prompt_with_restaurant_name_and_tools(
    client: AsyncClient, owner_headers, use_llm
) -> None:
    await client.put("/api/restaurant", headers=owner_headers, json={"name": "Spice Route"})
    llm = use_llm(ScriptedLLM(say("ok")))

    await ask(client, owner_headers, "hi")

    first = llm.requests[0]
    system = first["messages"][0]
    assert system["role"] == "system"
    assert "Spice Route" in system["content"]
    assert "cannot take food orders" in system["content"]
    assert {t["function"]["name"] for t in first["tools"]} == {
        "get_active_offers",
        "check_table_availability",
        "get_my_recent_bills",
        "get_bill_receipt",
        "request_human_handoff",
    }
    assert first["messages"][-1] == {"role": "user", "content": "hi"}


async def test_earlier_messages_are_sent_as_history(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(say("first answer"), say("second answer")))

    await ask(client, owner_headers, "first question")
    await ask(client, owner_headers, "second question")

    sent = llm.requests[1]["messages"]
    assert [(m["role"], m["content"]) for m in sent[1:]] == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "second question"),
    ]


async def test_history_is_limited(client: AsyncClient, owner_headers, use_llm, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_HISTORY_MESSAGES", "2")
    get_settings.cache_clear()
    llm = use_llm(ScriptedLLM(*[say(f"a{i}") for i in range(4)]))

    for i in range(4):
        await ask(client, owner_headers, f"q{i}")

    sent = llm.requests[3]["messages"][1:]
    assert [m["content"] for m in sent] == ["q2", "a2", "q3"]


async def test_each_phone_number_has_its_own_conversation(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(say("a"), say("b")))

    await ask(client, owner_headers, "from guest one", phone=GUEST)
    await ask(client, owner_headers, "from guest two", phone=OTHER)

    assert [m["content"] for m in llm.requests[1]["messages"][1:]] == ["from guest two"]
    assert len((await client.get("/api/chat/conversations", headers=owner_headers)).json()) == 2


async def test_phone_formats_map_to_the_same_conversation(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(say("a"), say("b")))

    await ask(client, owner_headers, "one", phone="+91 98100 00001")
    await ask(client, owner_headers, "two", phone="9810000001")

    conversations = (await client.get("/api/chat/conversations", headers=owner_headers)).json()
    assert len(conversations) == 1
    assert conversations[0]["phone"] == GUEST
    assert conversations[0]["message_count"] == 4


async def test_invalid_phone_is_rejected(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(say("never used")))

    assert (await ask(client, owner_headers, "hi", phone="12345")).status_code == 422


async def test_very_long_messages_are_truncated(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(say("ok")))

    await ask(client, owner_headers, "x" * 3000)

    assert len(llm.requests[0]["messages"][-1]["content"]) == 1000


async def test_known_customer_is_linked_to_the_conversation(
    client: AsyncClient, menu, owner_headers, use_llm
) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST, name="Asha")
    use_llm(ScriptedLLM(say("hi")))

    await ask(client, owner_headers, "hello")

    conversation = (await client.get("/api/chat/conversations", headers=owner_headers)).json()[0]
    assert conversation["customer_name"] == "Asha"


# ----------------------------------------------------------------- offers


async def test_offers_tool_returns_current_and_upcoming_offers(
    client: AsyncClient, owner_headers, use_llm
) -> None:
    await add_offer(client, owner_headers, title="Happy hour", discount_percent="15", valid_until=iso(2))
    await add_offer(client, owner_headers, title="Evening", discount_percent="10", valid_from=iso(2))
    await add_offer(client, owner_headers, title="Old", valid_until=iso(-3))
    await add_offer(client, owner_headers, title="Paused", is_active=False)
    await add_offer(client, owner_headers, title="Next week", valid_from=iso(24 * 7))
    llm = use_llm(ScriptedLLM(tool_call("get_active_offers"), say("15% off for the next 2 hours, then 10%")))

    response = await ask(client, owner_headers, "any discount?")

    result = llm.last_tool_result
    assert [o["title"] for o in result["active_offers"]] == ["Happy hour"]
    assert result["active_offers"][0]["discount_percent"] == 15.0
    assert 118 <= result["active_offers"][0]["minutes_remaining"] <= 120
    assert [o["title"] for o in result["upcoming_offers"]] == ["Evening"]
    assert response.json()["reply"] == "15% off for the next 2 hours, then 10%"


async def test_offers_tool_with_no_offers(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("get_active_offers"), say("No offers right now")))

    await ask(client, owner_headers, "any discount?")

    assert llm.last_tool_result["active_offers"] == []
    assert llm.last_tool_result["upcoming_offers"] == []


async def test_offer_times_are_given_in_restaurant_time(client: AsyncClient, owner_headers, use_llm) -> None:
    await add_offer(client, owner_headers, valid_until="2099-01-01T12:00:00+00:00")
    llm = use_llm(ScriptedLLM(tool_call("get_active_offers"), say("ok")))

    await ask(client, owner_headers, "offers?")

    assert llm.last_tool_result["active_offers"][0]["ends"] == "01 Jan 2099, 05:30 PM"  # IST = UTC+5:30


# ------------------------------------------------------ table availability


async def test_table_free_for_party(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("check_table_availability", party_size=2), say("Yes")))

    await ask(client, owner_headers, "space for 2?")

    result = llm.last_tool_result
    assert result["can_seat_right_now"] is True
    assert result["free_tables_that_fit"] == 1
    assert "Reservations are not available" in result["note"]


async def test_occupied_table_is_not_counted(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    await client.post(
        "/api/billing/orders", headers=owner_headers, json={"order_type": "dine_in", "table_id": menu["table_id"]}
    )
    llm = use_llm(ScriptedLLM(tool_call("check_table_availability", party_size=2), say("Sorry, full")))

    await ask(client, owner_headers, "space for 2?")

    assert llm.last_tool_result["can_seat_right_now"] is False
    assert llm.last_tool_result["free_tables_that_fit"] == 0


async def test_table_becomes_free_again_after_billing(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    order = (await client.post(
        "/api/billing/orders", headers=owner_headers, json={"order_type": "dine_in", "table_id": menu["table_id"]}
    )).json()
    await client.post(f"/api/billing/orders/{order['id']}/items", headers=owner_headers, json={"menu_item_id": menu["paneer_id"]})
    await client.post(f"/api/billing/orders/{order['id']}/bill", headers=owner_headers, json={})
    llm = use_llm(ScriptedLLM(tool_call("check_table_availability", party_size=2), say("Yes")))

    await ask(client, owner_headers, "space?")

    assert llm.last_tool_result["can_seat_right_now"] is True


async def test_party_larger_than_any_table(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("check_table_availability", party_size=10), say("No")))

    await ask(client, owner_headers, "space for 10?")

    assert llm.last_tool_result["can_seat_right_now"] is False
    assert llm.last_tool_result["largest_table_seats"] == 4


async def test_inactive_tables_are_ignored(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    await client.patch(f"/api/billing/tables/{menu['table_id']}", headers=owner_headers, json={"is_active": False})
    llm = use_llm(ScriptedLLM(tool_call("check_table_availability", party_size=2), say("No")))

    await ask(client, owner_headers, "space?")

    assert llm.last_tool_result["can_seat_right_now"] is False


@pytest.mark.parametrize("bad", [0, -1, 51, "two", None, True, 2.5])
async def test_invalid_party_size_gets_an_error_result(client: AsyncClient, owner_headers, use_llm, bad) -> None:
    llm = use_llm(ScriptedLLM(tool_call("check_table_availability", party_size=bad), say("Sorry")))

    await ask(client, owner_headers, "space?")

    assert "error" in llm.last_tool_result


# ------------------------------------------------------------------ bills


async def test_guest_sees_only_their_own_bills(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    await place_order(client, owner_headers, menu, {"cola": 2}, phone=OTHER)
    llm = use_llm(ScriptedLLM(tool_call("get_my_recent_bills"), say("Here you go")))

    await ask(client, owner_headers, "my bills?", phone=GUEST)

    bills = llm.last_tool_result["bills"]
    assert len(bills) == 1
    assert bills[0]["items"] == ["1 x Paneer Tikka"]
    assert bills[0]["total"] == "210.00"
    assert bills[0]["status"] == "unpaid"


async def test_recent_bills_are_newest_first_and_limited(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    for _ in range(4):
        await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    llm = use_llm(ScriptedLLM(tool_call("get_my_recent_bills", limit=2), say("ok")))

    await ask(client, owner_headers, "bills?")

    invoices = [b["invoice_number"] for b in llm.last_tool_result["bills"]]
    assert len(invoices) == 2
    assert [i.rsplit("-", 1)[1] for i in invoices] == ["000004", "000003"]


async def test_bill_limit_is_capped_at_five(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    for _ in range(7):
        await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    llm = use_llm(ScriptedLLM(tool_call("get_my_recent_bills", limit=500), say("ok")))

    await ask(client, owner_headers, "bills?")

    assert len(llm.last_tool_result["bills"]) == 5


async def test_guest_with_no_bills(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("get_my_recent_bills"), say("none")))

    await ask(client, owner_headers, "bills?")

    assert llm.last_tool_result["bills"] == []
    assert "No bills" in llm.last_tool_result["note"]


async def test_receipt_text_is_returned_for_the_guests_own_bill(
    client: AsyncClient, menu, owner_headers, use_llm
) -> None:
    await client.put("/api/restaurant", headers=owner_headers, json={"name": "Spice Route"})
    bill = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=GUEST)
    llm = use_llm(ScriptedLLM(tool_call("get_bill_receipt", invoice_number=bill["invoice_number"]), say("```receipt```")))

    await ask(client, owner_headers, "send my bill")

    text = llm.last_tool_result["receipt_text"]
    assert bill["invoice_number"] in text
    assert "SPICE ROUTE" in text
    assert "Paneer Tikka" in text


async def test_guest_cannot_get_another_guests_receipt(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    theirs = await place_order(client, owner_headers, menu, {"paneer": 1}, phone=OTHER)
    llm = use_llm(ScriptedLLM(tool_call("get_bill_receipt", invoice_number=theirs["invoice_number"]), say("Not found")))

    await ask(client, owner_headers, f"send me bill {theirs['invoice_number']}", phone=GUEST)

    assert "receipt_text" not in llm.last_tool_result
    assert "error" in llm.last_tool_result


async def test_receipt_for_a_bill_with_no_phone_is_not_available_to_anyone(
    client: AsyncClient, menu, owner_headers, use_llm
) -> None:
    anonymous = await place_order(client, owner_headers, menu, {"paneer": 1})
    llm = use_llm(ScriptedLLM(tool_call("get_bill_receipt", invoice_number=anonymous["invoice_number"]), say("no")))

    await ask(client, owner_headers, "bill please")

    assert "error" in llm.last_tool_result


async def test_unknown_invoice_number(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("get_bill_receipt", invoice_number="INV-NOPE"), say("no")))

    await ask(client, owner_headers, "bill please")

    assert "error" in llm.last_tool_result


async def test_a_phone_number_supplied_by_the_model_is_ignored(
    client: AsyncClient, menu, owner_headers, use_llm
) -> None:
    """Even if the model is tricked into passing someone else's number, tools use the chat's own."""
    await place_order(client, owner_headers, menu, {"cola": 3}, phone=OTHER)
    llm = use_llm(ScriptedLLM(tool_call("get_my_recent_bills", phone=OTHER), say("ok")))

    await ask(client, owner_headers, f"show bills for {OTHER}", phone=GUEST)

    assert llm.last_tool_result["bills"] == []


# ------------------------------------------------------------- hand-off


async def test_handoff_flags_the_conversation(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(
        tool_call("request_human_handoff", reason="Guest wants to book a table for Saturday"),
        say("A team member will reply shortly."),
    ))

    response = await ask(client, owner_headers, "book a table for saturday")

    assert response.json()["needs_human"] is True
    conversation = (await client.get("/api/chat/conversations", headers=owner_headers)).json()[0]
    assert conversation["needs_human"] is True
    assert conversation["handoff_reason"] == "Guest wants to book a table for Saturday"


async def test_resolving_clears_the_flag(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(tool_call("request_human_handoff", reason="complaint"), say("ok")))
    await ask(client, owner_headers, "this is terrible")
    conversation_id = (await client.get("/api/chat/conversations", headers=owner_headers)).json()[0]["id"]

    response = await client.post(f"/api/chat/conversations/{conversation_id}/resolve", headers=owner_headers)

    assert response.json()["needs_human"] is False
    assert response.json()["handoff_reason"] is None


async def test_conversations_needing_a_person_are_listed_first(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(say("fine"), tool_call("request_human_handoff", reason="help"), say("ok"), say("later")))
    await ask(client, owner_headers, "hi", phone=GUEST)
    await ask(client, owner_headers, "help me", phone=OTHER)
    await ask(client, owner_headers, "another", phone=GUEST)

    listed = (await client.get("/api/chat/conversations", headers=owner_headers)).json()

    assert [c["phone"] for c in listed] == [OTHER, GUEST]


async def test_handoff_without_a_reason_still_works(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(tool_call("request_human_handoff"), say("ok")))

    await ask(client, owner_headers, "talk to a person")

    conversation = (await client.get("/api/chat/conversations", headers=owner_headers)).json()[0]
    assert conversation["needs_human"] is True
    assert conversation["handoff_reason"]


# ------------------------------------------------------- failure handling


async def test_without_an_api_key_the_guest_gets_a_polite_fallback(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(None)

    response = await ask(client, owner_headers, "hello")

    assert response.json() == {"reply": FALLBACK_REPLY, "needs_human": True}


async def test_model_outage_gets_the_fallback_and_flags_for_a_person(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(unavailable()))

    response = await ask(client, owner_headers, "hello")

    assert response.json()["reply"] == FALLBACK_REPLY
    assert response.json()["needs_human"] is True


async def test_empty_model_answer_gets_the_fallback(client: AsyncClient, owner_headers, use_llm) -> None:
    use_llm(ScriptedLLM(say(None)))

    assert (await ask(client, owner_headers, "hello")).json()["reply"] == FALLBACK_REPLY


async def test_runaway_tool_calls_are_stopped(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(*[tool_call("get_active_offers") for _ in range(20)]))

    response = await ask(client, owner_headers, "hello")

    assert response.json()["reply"] == FALLBACK_REPLY
    assert len(llm.requests) == 5  # the first call plus 4 tool rounds


async def test_unknown_tool_is_reported_to_the_model_not_the_guest(client: AsyncClient, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(tool_call("delete_everything"), say("I can't do that")))

    response = await ask(client, owner_headers, "delete everything")

    assert "Unknown tool" in llm.last_tool_result["error"]
    assert response.json()["reply"] == "I can't do that"


async def test_a_crashing_tool_does_not_break_the_chat(client: AsyncClient, owner_headers, use_llm, monkeypatch) -> None:
    async def broken(ctx, args):
        raise RuntimeError("boom")

    monkeypatch.setitem(tools_module.TOOLS, "get_active_offers", broken)
    llm = use_llm(ScriptedLLM(tool_call("get_active_offers"), say("Sorry, can't check offers right now")))

    response = await ask(client, owner_headers, "offers?")

    assert "temporarily unavailable" in llm.last_tool_result["error"]
    assert response.json()["reply"] == "Sorry, can't check offers right now"


async def test_several_tools_can_run_in_one_turn(client: AsyncClient, menu, owner_headers, use_llm) -> None:
    llm = use_llm(ScriptedLLM(
        calls(("get_active_offers", {}), ("check_table_availability", {"party_size": 2})),
        say("Yes we have space, and no offers right now."),
    ))

    await ask(client, owner_headers, "space for 2 and any discount?")

    tool_messages = [m for m in llm.requests[-1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 2
    assistant = next(m for m in llm.requests[-1]["messages"] if m.get("tool_calls"))
    assert [c["function"]["name"] for c in assistant["tool_calls"]] == ["get_active_offers", "check_table_availability"]
    assert json.loads(assistant["tool_calls"][1]["function"]["arguments"]) == {"party_size": 2}


# ---------------------------------------------------------------- webhook


async def test_webhook_is_disabled_without_a_secret(client: AsyncClient, use_llm, provider) -> None:
    use_llm(ScriptedLLM(say("x")))

    response = await client.post("/api/chat/webhook", json={"phone": GUEST, "text": "hi"})

    assert response.status_code == 503


async def test_webhook_rejects_a_missing_or_wrong_secret(client: AsyncClient, use_llm, provider, webhook_secret) -> None:
    use_llm(ScriptedLLM(say("x")))

    missing = await client.post("/api/chat/webhook", json={"phone": GUEST, "text": "hi"})
    wrong = await client.post(
        "/api/chat/webhook", json={"phone": GUEST, "text": "hi"}, headers={"X-Webhook-Secret": "nope"}
    )

    assert (missing.status_code, wrong.status_code) == (401, 401)
    assert provider.sent == []


async def test_webhook_replies_and_sends_via_the_provider(client: AsyncClient, use_llm, provider, webhook_secret) -> None:
    use_llm(ScriptedLLM(say("Hello from the restaurant")))

    response = await client.post(
        "/api/chat/webhook",
        json={"phone": "+91 98100 00001", "text": "hi"},
        headers={"X-Webhook-Secret": webhook_secret},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Hello from the restaurant"
    assert provider.sent == [(GUEST, "Hello from the restaurant")]


async def test_webhook_still_succeeds_when_sending_fails(app, client: AsyncClient, use_llm, webhook_secret, owner_headers) -> None:
    app.dependency_overrides[get_provider] = lambda: RecordingProvider(fail=True)
    use_llm(ScriptedLLM(say("Hello")))

    response = await client.post(
        "/api/chat/webhook", json={"phone": GUEST, "text": "hi"}, headers={"X-Webhook-Secret": webhook_secret}
    )

    assert response.status_code == 200
    detail_list = (await client.get("/api/chat/conversations", headers=owner_headers)).json()
    assert detail_list[0]["message_count"] == 2


async def test_webhook_validates_the_payload(client: AsyncClient, use_llm, provider, webhook_secret) -> None:
    headers = {"X-Webhook-Secret": webhook_secret}

    assert (await client.post("/api/chat/webhook", json={"phone": GUEST}, headers=headers)).status_code == 422
    assert (await client.post("/api/chat/webhook", json={"phone": "123", "text": "hi"}, headers=headers)).status_code == 422
    assert (await client.post("/api/chat/webhook", json={"phone": GUEST, "text": ""}, headers=headers)).status_code == 422


async def test_simulator_never_sends_to_the_provider(client: AsyncClient, owner_headers, use_llm, provider) -> None:
    use_llm(ScriptedLLM(say("test reply")))

    await ask(client, owner_headers, "hi")

    assert provider.sent == []


# ------------------------------------------------------- permissions


async def test_chat_management_is_manager_only(client: AsyncClient, make_staff, use_llm) -> None:
    use_llm(ScriptedLLM(say("x")))
    waiter = await make_staff("waiter")

    assert (await client.post("/api/chat/simulate", headers=waiter, json={"phone": GUEST, "text": "hi"})).status_code == 403
    assert (await client.get("/api/chat/conversations", headers=waiter)).status_code == 403
    assert (await client.get("/api/chat/conversations/1", headers=waiter)).status_code == 403
    assert (await client.post("/api/chat/conversations/1/resolve", headers=waiter)).status_code == 403


async def test_chat_endpoints_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/chat/conversations")).status_code == 401
    assert (await client.post("/api/chat/simulate", json={"phone": GUEST, "text": "hi"})).status_code == 401


async def test_missing_conversation_returns_404(client: AsyncClient, owner_headers) -> None:
    assert (await client.get("/api/chat/conversations/99", headers=owner_headers)).status_code == 404
    assert (await client.post("/api/chat/conversations/99/resolve", headers=owner_headers)).status_code == 404


# ------------------------------------------------ the real OpenAI wrapper


def _fake_openai_response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _fake_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


async def test_openai_client_parses_text_and_tool_calls() -> None:
    client = OpenAIClient("sk-test", "gpt-4.1-mini")
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return _fake_openai_response(
            content=None,
            tool_calls=[_fake_call("c1", "check_table_availability", '{"party_size": 2}')],
        )

    client._client.chat.completions.create = create

    reply = await client.complete([{"role": "user", "content": "hi"}], [{"type": "function"}])

    assert seen["model"] == "gpt-4.1-mini"
    assert seen["messages"] == [{"role": "user", "content": "hi"}]
    assert (reply.tool_calls[0].id, reply.tool_calls[0].name, reply.tool_calls[0].arguments) == (
        "c1",
        "check_table_availability",
        {"party_size": 2},
    )


async def test_openai_client_tolerates_malformed_tool_arguments() -> None:
    client = OpenAIClient("sk-test", "gpt-4.1-mini")

    async def create(**kwargs):
        return _fake_openai_response(tool_calls=[_fake_call("c1", "get_active_offers", "{not json")])

    client._client.chat.completions.create = create

    reply = await client.complete([], [])

    assert reply.tool_calls[0].arguments == {}


async def test_openai_client_returns_plain_text() -> None:
    client = OpenAIClient("sk-test", "gpt-4.1-mini")

    async def create(**kwargs):
        return _fake_openai_response(content="Hello!")

    client._client.chat.completions.create = create

    reply = await client.complete([], [])

    assert (reply.content, reply.tool_calls) == ("Hello!", [])


async def test_openai_failures_become_llm_unavailable() -> None:
    client = OpenAIClient("sk-test", "gpt-4.1-mini")

    async def create(**kwargs):
        raise ConnectionError("network down")

    client._client.chat.completions.create = create

    with pytest.raises(LLMUnavailableError):
        await client.complete([], [])


def test_no_api_key_means_no_llm(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    get_llm_client.cache_clear()

    assert get_optional_llm() is None
    with pytest.raises(LLMUnavailableError):
        get_llm_client()


def test_api_key_creates_the_client(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    get_llm_client.cache_clear()

    assert isinstance(get_optional_llm(), OpenAIClient)
    get_llm_client.cache_clear()
