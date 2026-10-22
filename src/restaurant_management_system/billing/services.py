from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from restaurant_management_system.billing.calc import (
    DiscountTooLargeError,
    Line,
    compute_bill,
)
from restaurant_management_system.billing.models import (
    Bill,
    BillStatus,
    InvoiceCounter,
    KitchenTicket,
    Order,
    OrderStatus,
    Payment,
)
from restaurant_management_system.billing.schemas import PaymentCreate


async def get_order(session: AsyncSession, order_id: int) -> Order:
    order = await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.table))
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


async def get_bill(session: AsyncSession, bill_id: int) -> Bill:
    bill = await session.scalar(
        select(Bill)
        .where(Bill.id == bill_id)
        .options(
            selectinload(Bill.payments),
            selectinload(Bill.order).selectinload(Order.items),
            selectinload(Bill.order).selectinload(Order.table),
        )
        .execution_options(populate_existing=True)
    )
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bill not found")
    return bill


async def get_ticket(session: AsyncSession, ticket_id: int) -> KitchenTicket:
    ticket = await session.scalar(
        select(KitchenTicket)
        .where(KitchenTicket.id == ticket_id)
        .options(selectinload(KitchenTicket.items))
        .execution_options(populate_existing=True)
    )
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kitchen ticket not found")
    return ticket


def require_open(order: Order) -> None:
    if order.status != OrderStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order is {order.status}")


async def create_kitchen_ticket(session: AsyncSession, order: Order) -> KitchenTicket:
    require_open(order)
    unsent = [item for item in order.items if item.kitchen_ticket_id is None]
    if not unsent:
        raise HTTPException(status.HTTP_409_CONFLICT, "No new items to send to the kitchen")

    ticket = KitchenTicket(order_id=order.id)
    session.add(ticket)
    await session.flush()
    for item in unsent:
        item.kitchen_ticket_id = ticket.id
    await session.commit()
    return await get_ticket(session, ticket.id)


async def _next_invoice_number(session: AsyncSession) -> str:
    counter = await session.scalar(
        select(InvoiceCounter).where(InvoiceCounter.id == 1).with_for_update()
    )
    if counter is None:
        counter = InvoiceCounter(id=1, last_number=0)
        session.add(counter)
        await session.flush()
    counter.last_number += 1
    await session.flush()
    return f"INV-{datetime.now().year}-{counter.last_number:06d}"


async def generate_bill(
    session: AsyncSession, order: Order, discount: Decimal, user_id: int
) -> Bill:
    require_open(order)
    if not order.items:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot bill an empty order")

    lines = [Line(item.unit_price, item.quantity, item.gst_rate) for item in order.items]
    try:
        totals = compute_bill(lines, discount)
    except DiscountTooLargeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None

    bill = Bill(
        invoice_number=await _next_invoice_number(session),
        order_id=order.id,
        subtotal=totals.subtotal,
        discount=totals.discount,
        cgst=totals.cgst,
        sgst=totals.sgst,
        round_off=totals.round_off,
        total=totals.total,
        status=BillStatus.UNPAID.value,
        created_by=user_id,
    )
    session.add(bill)
    order.status = OrderStatus.BILLED.value
    await session.commit()
    return await get_bill(session, bill.id)


async def record_payment(session: AsyncSession, bill: Bill, body: PaymentCreate) -> Bill:
    if bill.status == BillStatus.PAID.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bill is already paid")
    if body.amount > bill.amount_due:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Amount exceeds the amount due ({bill.amount_due})",
        )

    session.add(
        Payment(
            bill_id=bill.id,
            mode=body.mode.value,
            amount=body.amount,
            reference=body.reference,
        )
    )
    await session.flush()
    await session.refresh(bill, attribute_names=["payments"])
    if bill.amount_due <= 0:
        bill.status = BillStatus.PAID.value
    await session.commit()
    return await get_bill(session, bill.id)
