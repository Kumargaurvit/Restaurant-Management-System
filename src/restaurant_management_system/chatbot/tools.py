"""Tools the chatbot may call.

Every tool runs on the server and is scoped to the guest on the other end of the chat: the phone
number comes from the webhook, never from anything the model supplies, so a guest cannot read
another guest's bills or bookings no matter what they type.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from restaurant_management_system.billing.models import Bill, Order, OrderStatus, RestaurantTable
from restaurant_management_system.billing.receipt import render_receipt
from restaurant_management_system.booking.models import ACTIVE_STATUSES, Booking
from restaurant_management_system.booking.services import (
    availability,
    create_booking,
    get_settings_row,
    is_available,
)
from restaurant_management_system.chatbot.models import Conversation
from restaurant_management_system.chatbot.offers import aware, current_offers
from restaurant_management_system.config import Settings
from restaurant_management_system.restaurant.services import get_profile_or_blank

logger = logging.getLogger(__name__)

MAX_PARTY_SIZE = 50
# A guest can hold only a few upcoming bookings through the bot; more needs a person.
MAX_UPCOMING_BOOKINGS = 3
BOOKING_SOURCE = "whatsapp"


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

    @property
    def local_now(self) -> datetime:
        return aware(self.now).astimezone(self.zone)

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
                "Check table availability for a party. Without a date it answers whether there "
                "is space to walk in right now. With a date (YYYY-MM-DD) it lists which booking "
                "time slots that day are free. It never reserves anything."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "party_size": {
                        "type": "integer",
                        "description": "Number of people in the party",
                        "minimum": 1,
                        "maximum": MAX_PARTY_SIZE,
                    },
                    "date": {
                        "type": "string",
                        "description": "Day to check, as YYYY-MM-DD. Omit to check right now.",
                    },
                },
                "required": ["party_size"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking_request",
            "description": (
                "Request a table booking for this guest. First call check_table_availability "
                "with the date and use one of the free slot times. The request is held until "
                "the restaurant confirms it; the guest is then told on WhatsApp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_name": {"type": "string", "description": "Name for the booking"},
                    "party_size": {"type": "integer", "minimum": 1, "maximum": MAX_PARTY_SIZE},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "Slot start time, 24-hour HH:MM"},
                    "notes": {"type": "string", "description": "Optional note, e.g. a birthday"},
                },
                "required": ["guest_name", "party_size", "date", "time"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_bookings",
            "description": "List this guest's upcoming table bookings and their status.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
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
                "wants something you cannot do (food orders, changing or cancelling a booking, "
                "large groups, complaints, refunds), is upset, or asks something you cannot "
                "answer from tool results."
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
            remaining = aware(offer.valid_until) - aware(ctx.now)
            data["minutes_remaining"] = max(0, int(remaining.total_seconds() // 60))
    return data


async def get_active_offers(ctx: ToolContext, args: dict) -> dict:
    active, upcoming = await current_offers(ctx.session, aware(ctx.now))
    return {
        "now": ctx.local(ctx.now),
        "active_offers": [_offer_dict(o, ctx, active=True) for o in active],
        "upcoming_offers": [_offer_dict(o, ctx, active=False) for o in upcoming],
    }


def _valid_party(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_PARTY_SIZE


def _parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_time(value: Any) -> time | None:
    try:
        return time.fromisoformat(str(value)).replace(second=0, microsecond=0)
    except ValueError:
        return None


def _hhmm(moment: time) -> str:
    return moment.strftime("%H:%M")


async def _walk_in(ctx: ToolContext, party_size: int) -> dict:
    """Is there room right now for a party that walks in?"""
    settings_row = await get_settings_row(ctx.session)
    local = ctx.local_now
    clock = local.time().replace(second=0, microsecond=0, tzinfo=None)
    open_now = settings_row.opens_at <= clock < settings_row.closes_at

    tables = list(
        await ctx.session.scalars(select(RestaurantTable).where(RestaurantTable.is_active.is_(True)))
    )
    busy = set(
        await ctx.session.scalars(
            select(Order.table_id).where(
                Order.status == OrderStatus.OPEN.value, Order.table_id.is_not(None)
            )
        )
    )
    fitting = [t for t in tables if t.id not in busy and t.capacity >= party_size]
    # Tables held by bookings that overlap this moment are not free either.
    unbooked = await is_available(ctx.session, settings_row, local.date(), clock, party_size)
    return {
        "party_size": party_size,
        "open_now": open_now,
        "opens_at": _hhmm(settings_row.opens_at),
        "closes_at": _hhmm(settings_row.closes_at),
        "can_seat_right_now": open_now and bool(fitting) and unbooked,
        "free_tables_that_fit": len(fitting),
        "largest_table_seats": max((t.capacity for t in tables), default=0),
        "note": "Walk-in availability at this moment. To hold a table, create a booking request.",
    }


async def check_table_availability(ctx: ToolContext, args: dict) -> dict:
    party_size = args.get("party_size")
    if not _valid_party(party_size):
        return {"error": f"party_size must be a whole number from 1 to {MAX_PARTY_SIZE}"}

    raw_day = args.get("date")
    if raw_day in (None, ""):
        return await _walk_in(ctx, party_size)

    day = _parse_day(raw_day)
    if day is None:
        return {"error": "date must be written as YYYY-MM-DD"}
    settings_row = await get_settings_row(ctx.session)
    today = ctx.local_now.date()
    if day < today:
        return {"error": "That date has already passed."}
    if (day - today).days > settings_row.max_days_ahead:
        return {"error": f"Bookings open up to {settings_row.max_days_ahead} days ahead."}
    if party_size > settings_row.max_party_size:
        return {
            "error": f"Online bookings are for up to {settings_row.max_party_size} guests. "
            "Larger groups need a call."
        }

    slots = await availability(ctx.session, settings_row, day, party_size, ctx.settings.timezone)
    return {
        "date": day.isoformat(),
        "party_size": party_size,
        "slot_minutes": settings_row.slot_minutes,
        "slots": [{"time": _hhmm(start), "free": free} for start, free in slots],
        "free_slots": [_hhmm(start) for start, free in slots if free],
    }


async def _upcoming_bookings(ctx: ToolContext, limit: int | None = None) -> list[Booking]:
    query = (
        select(Booking)
        .where(
            Booking.phone == ctx.phone,
            Booking.status.in_(ACTIVE_STATUSES),
            Booking.booking_date >= ctx.local_now.date(),
        )
        .order_by(Booking.booking_date, Booking.start_time)
    )
    if limit is not None:
        query = query.limit(limit)
    return list(await ctx.session.scalars(query))


def _booking_dict(booking: Booking) -> dict[str, Any]:
    return {
        "booking_id": booking.id,
        "date": booking.booking_date.isoformat(),
        "time": _hhmm(booking.start_time),
        "party_size": booking.party_size,
        "status": booking.status,
    }


async def create_booking_request(ctx: ToolContext, args: dict) -> dict:
    guest_name = str(args.get("guest_name", "")).strip()[:120]
    party_size = args.get("party_size")
    day = _parse_day(args.get("date"))
    start = _parse_time(args.get("time"))
    notes = str(args["notes"]).strip()[:300] if args.get("notes") else None

    if not guest_name:
        return {"error": "Ask the guest for the name to put the booking under."}
    if not _valid_party(party_size):
        return {"error": f"party_size must be a whole number from 1 to {MAX_PARTY_SIZE}"}
    if day is None:
        return {"error": "date must be written as YYYY-MM-DD"}
    if start is None:
        return {"error": "time must be written as 24-hour HH:MM"}

    held = await _upcoming_bookings(ctx)
    if len(held) >= MAX_UPCOMING_BOOKINGS:
        return {
            "error": f"This guest already has {MAX_UPCOMING_BOOKINGS} upcoming bookings. "
            "Hand over to a person for more."
        }

    try:
        booking = await create_booking(
            ctx.session,
            guest_name=guest_name,
            phone=ctx.phone,
            party_size=party_size,
            day=day,
            start=start,
            notes=notes,
            source=BOOKING_SOURCE,
            zone_name=ctx.settings.timezone,
        )
    except HTTPException as error:  # a rule was broken (full slot, passed, too far ahead...)
        return {"error": str(error.detail)}
    return {
        **_booking_dict(booking),
        "message": "Request received. The restaurant will confirm it here on WhatsApp.",
    }


async def get_my_bookings(ctx: ToolContext, args: dict) -> dict:
    bookings = await _upcoming_bookings(ctx, limit=5)
    return {
        "bookings": [_booking_dict(b) for b in bookings],
        "note": None if bookings else "No upcoming bookings for this phone number.",
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
    profile = await get_profile_or_blank(ctx.session)
    return {"receipt_text": render_receipt(bill, bill.order, ctx.zone, profile)}


async def request_human_handoff(ctx: ToolContext, args: dict) -> dict:
    reason = str(args.get("reason", "")).strip()[:300] or "Guest asked for a person"
    ctx.conversation.needs_human = True
    ctx.conversation.handoff_reason = reason
    result: dict[str, Any] = {
        "ok": True,
        "message": "A team member has been notified and will reply here.",
    }
    if ctx.settings.owner_contact:
        result["contact_for_urgent_help"] = ctx.settings.owner_contact
    return result


TOOLS: dict[str, Callable[[ToolContext, dict], Awaitable[dict]]] = {
    "get_active_offers": get_active_offers,
    "check_table_availability": check_table_availability,
    "create_booking_request": create_booking_request,
    "get_my_bookings": get_my_bookings,
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
