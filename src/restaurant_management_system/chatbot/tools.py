"""Tools the chatbot may call.

Every tool runs on the server and is scoped to the guest on the other end of the chat: the phone
number comes from the webhook, never from anything the model supplies, so a guest cannot read
another guest's bills no matter what they type.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from restaurant_management_system.billing.models import Bill, Order, OrderStatus, RestaurantTable
from restaurant_management_system.billing.receipt import render_receipt
from restaurant_management_system.chatbot.models import Conversation
from restaurant_management_system.chatbot.offers import aware, current_offers
from restaurant_management_system.config import Settings
from restaurant_management_system.restaurant.services import get_profile

logger = logging.getLogger(__name__)

MAX_PARTY_SIZE = 50


@dataclass
class ToolContext:
    session: AsyncSession
    phone: str
    conversation: Conversation
    settings: Settings
    now: datetime

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.settings.timezone)

    def local(self, moment: datetime) -> str:
        return aware(moment).astimezone(self.zone).strftime("%d %b %Y, %I:%M %p")


TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_active_offers",
            "description": (
                "Get the discounts and offers the restaurant is running right now, plus any that "
                "start within the next 24 hours. Use this for any question about discounts, "
                "offers, deals or promotions. Never quote a discount without calling this."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_table_availability",
            "description": (
                "Check whether the restaurant has a table free right now for a party of a given "
                "size. This reflects current occupancy only; it cannot reserve a table."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "party_size": {
                        "type": "integer",
                        "description": "Number of people in the party",
                        "minimum": 1,
                        "maximum": MAX_PARTY_SIZE,
                    }
                },
                "required": ["party_size"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_recent_bills",
            "description": "List this guest's most recent bills (invoice number, date, total, status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3}
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bill_receipt",
            "description": (
                "Get the printable receipt text for one of this guest's own bills, by invoice "
                "number. Include the text exactly as returned, inside a ``` code block."
            ),
            "parameters": {
                "type": "object",
                "properties": {"invoice_number": {"type": "string"}},
                "required": ["invoice_number"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_handoff",
            "description": (
                "Ask a person from the restaurant to take over this chat. Use it when the guest "
                "wants something you cannot do (food orders, table reservations, complaints, "
                "refunds), is upset, or asks something you cannot answer from tool results."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string", "description": "One short sentence"}},
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]


def _offer_dict(offer, ctx: ToolContext, *, active: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": offer.title,
        "description": offer.description,
        "discount_percent": float(offer.discount_percent) if offer.discount_percent is not None else None,
    }
    if offer.valid_from is not None:
        data["starts"] = ctx.local(offer.valid_from)
    if offer.valid_until is not None:
        data["ends"] = ctx.local(offer.valid_until)
        if active:
            remaining = aware(offer.valid_until) - ctx.now
            data["minutes_remaining"] = max(0, int(remaining.total_seconds() // 60))
    return data


async def get_active_offers(ctx: ToolContext, args: dict) -> dict:
    active, upcoming = await current_offers(ctx.session, ctx.now)
    return {
        "now": ctx.local(ctx.now),
        "active_offers": [_offer_dict(o, ctx, active=True) for o in active],
        "upcoming_offers": [_offer_dict(o, ctx, active=False) for o in upcoming],
    }


async def check_table_availability(ctx: ToolContext, args: dict) -> dict:
    party_size = args.get("party_size")
    if not isinstance(party_size, int) or isinstance(party_size, bool) or not 1 <= party_size <= MAX_PARTY_SIZE:
        return {"error": f"party_size must be a whole number from 1 to {MAX_PARTY_SIZE}"}

    tables = list(await ctx.session.scalars(select(RestaurantTable).where(RestaurantTable.is_active.is_(True))))
    busy = set(
        await ctx.session.scalars(
            select(Order.table_id).where(
                Order.status == OrderStatus.OPEN.value, Order.table_id.is_not(None)
            )
        )
    )
    free = [t for t in tables if t.id not in busy]
    fitting = [t for t in free if t.capacity >= party_size]
    largest = max((t.capacity for t in tables), default=0)
    return {
        "party_size": party_size,
        "can_seat_right_now": bool(fitting),
        "free_tables_that_fit": len(fitting),
        "largest_table_seats": largest,
        "note": "Based on tables free at this moment. Reservations are not available yet.",
    }


def _guest_bills_query(phone: str):
    return (
        select(Bill)
        .join(Order, Order.id == Bill.order_id)
        .where(Order.customer_phone == phone)
        .options(
            selectinload(Bill.payments),
            selectinload(Bill.order).selectinload(Order.items),
            selectinload(Bill.order).selectinload(Order.table),
        )
    )


async def get_my_recent_bills(ctx: ToolContext, args: dict) -> dict:
    limit = args.get("limit", 3)
    limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else 3
    limit = min(max(limit, 1), 5)

    bills = list(await ctx.session.scalars(_guest_bills_query(ctx.phone).order_by(Bill.id.desc()).limit(limit)))
    return {
        "bills": [
            {
                "invoice_number": bill.invoice_number,
                "date": ctx.local(bill.created_at),
                "total": str(bill.total),
                "status": bill.status,
                "amount_due": str(bill.amount_due),
                "items": [f"{i.quantity} x {i.name}" for i in bill.order.items],
            }
            for bill in bills
        ],
        "note": None if bills else "No bills found for this phone number.",
    }


async def get_bill_receipt(ctx: ToolContext, args: dict) -> dict:
    invoice = str(args.get("invoice_number", "")).strip()
    bill = await ctx.session.scalar(_guest_bills_query(ctx.phone).where(Bill.invoice_number == invoice))
    if bill is None:
        return {"error": "No bill with that invoice number was found for this guest."}
    profile = await get_profile(ctx.session)
    return {"receipt_text": render_receipt(bill, bill.order, ctx.zone, profile)}


async def request_human_handoff(ctx: ToolContext, args: dict) -> dict:
    reason = str(args.get("reason", "")).strip()[:300] or "Guest asked for a person"
    ctx.conversation.needs_human = True
    ctx.conversation.handoff_reason = reason
    return {"ok": True, "message": "A team member has been notified and will reply here."}


TOOLS: dict[str, Callable[[ToolContext, dict], Awaitable[dict]]] = {
    "get_active_offers": get_active_offers,
    "check_table_availability": check_table_availability,
    "get_my_recent_bills": get_my_recent_bills,
    "get_bill_receipt": get_bill_receipt,
    "request_human_handoff": request_human_handoff,
}


async def run_tool(name: str, args: dict, ctx: ToolContext) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool {name!r}"}
    try:
        return await tool(ctx, args if isinstance(args, dict) else {})
    except Exception:  # a tool bug must not break the guest's chat
        logger.exception("Chatbot tool %s failed", name)
        return {"error": "That information is temporarily unavailable."}


def utcnow() -> datetime:
    return datetime.now(UTC)
