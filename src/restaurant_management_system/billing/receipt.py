import textwrap
from datetime import UTC, datetime, tzinfo
from decimal import Decimal

from restaurant_management_system.billing.models import Bill, KitchenTicket, Order
from restaurant_management_system.restaurant.models import RestaurantProfile

WIDTH = 42  # characters per line on a 3-inch thermal printer


def _rule(char: str = "-") -> str:
    return char * WIDTH


def _center(text: str) -> str:
    return text[:WIDTH].center(WIDTH).rstrip()


def _pair(left: str, right: str) -> str:
    gap = max(1, WIDTH - len(left) - len(right))
    return f"{left}{' ' * gap}{right}"


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _local(moment: datetime, zone: tzinfo) -> datetime:
    # Timestamps are stored in UTC; some drivers return them without tzinfo.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(zone)


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, WIDTH) or []


def _header(profile: RestaurantProfile | None) -> list[str]:
    """Restaurant name, then address and registration numbers when saved."""
    if profile is None:
        return []
    lines = []
    if profile.name:
        lines.append(_center(profile.name.upper()))
    details = [*_wrap(profile.address)]
    if profile.phone:
        details.append(f"Ph: {profile.phone}")
    if profile.gstin:
        details.append(f"GSTIN: {profile.gstin}")
    if profile.fssai:
        details.append(f"FSSAI: {profile.fssai}")
    lines.extend(_center(part) for part in details)
    # A divider only when there is more than the name, so a name-only receipt stays compact.
    if details:
        lines.append(_rule("-"))
    return lines


def render_receipt(
    bill: Bill, order: Order, zone: tzinfo, profile: RestaurantProfile | None = None
) -> str:
    lines = [
        *_header(profile),
        _center("TAX INVOICE"),
        _rule("="),
        _pair("Invoice:", bill.invoice_number),
        _pair("Date:", _local(bill.created_at, zone).strftime("%d-%m-%Y %H:%M")),
        _pair("Type:", order.order_type.replace("_", " ").title()),
    ]
    if order.table is not None:
        lines.append(_pair("Table:", order.table.name))
    if order.customer_name:
        lines.append(_pair("Customer:", order.customer_name))
    lines.append(_rule())

    for item in order.items:
        amount = item.unit_price * item.quantity
        lines.append(item.name[:WIDTH])
        lines.append(_pair(f"  {item.quantity} x {_amount(item.unit_price)}", _amount(amount)))

    lines.append(_rule())
    lines.append(_pair("Subtotal", _amount(bill.subtotal)))
    if bill.discount > 0:
        lines.append(_pair("Discount", f"-{_amount(bill.discount)}"))
    lines.append(_pair("CGST", _amount(bill.cgst)))
    lines.append(_pair("SGST", _amount(bill.sgst)))
    if bill.round_off != 0:
        lines.append(_pair("Round off", _amount(bill.round_off)))
    lines.append(_rule("="))
    lines.append(_pair("TOTAL", _amount(bill.total)))
    lines.append(_rule("="))

    for payment in bill.payments:
        lines.append(_pair(payment.mode.upper(), _amount(payment.amount)))
    lines.append(_pair("Status", bill.status.upper()))
    lines.append("")
    footer = profile.receipt_footer if profile and profile.receipt_footer else "Thank you! Visit again."
    lines.extend(_center(part) for part in _wrap(footer))
    return "\n".join(lines) + "\n"


def render_kot(ticket: KitchenTicket, order: Order, zone: tzinfo) -> str:
    lines = [
        _center("KITCHEN ORDER"),
        _rule("="),
        _pair(f"KOT #{ticket.id}", _local(ticket.created_at, zone).strftime("%H:%M")),
        _pair("Order:", f"#{order.id} {order.order_type.replace('_', ' ')}"),
    ]
    if order.table is not None:
        lines.append(_pair("Table:", order.table.name))
    lines.append(_rule())
    for item in ticket.items:
        lines.append(f"{item.quantity} x {item.name}"[:WIDTH])
        if item.notes:
            lines.append(f"   Note: {item.notes}"[:WIDTH])
    lines.append(_rule("="))
    return "\n".join(lines) + "\n"
