from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.billing.models import Bill, Order, OrderItem, OrderStatus
from restaurant_management_system.customers import schemas
from restaurant_management_system.customers.models import Customer
from restaurant_management_system.customers.services import normalize_phone, set_marketing_opt_out
from restaurant_management_system.db.session import get_session

router = APIRouter(prefix="/api/customers", tags=["customers"])
reports_router = APIRouter(prefix="/api/reports", tags=["reports"])

STAFF = (Role.OWNER, Role.MANAGER, Role.CASHIER, Role.WAITER)
MANAGERS = (Role.OWNER, Role.MANAGER)


def _dec(value) -> Decimal:
    # SQLite returns floats for SUM(); going through str avoids binary-float noise.
    return Decimal(str(value or 0))


def _since(days: int | None) -> datetime | None:
    return datetime.now(UTC) - timedelta(days=days) if days else None


def _stats(since: datetime | None = None):
    """Per-customer visits and spend. A visit is one billed order."""
    query = (
        select(
            Order.customer_id.label("customer_id"),
            func.count(Bill.id).label("visits"),
            func.coalesce(func.sum(Bill.total), 0).label("spent"),
            func.min(Bill.created_at).label("first_visit"),
            func.max(Bill.created_at).label("last_visit"),
        )
        .join(Bill, Bill.order_id == Order.id)
        .where(Order.customer_id.is_not(None))
        .group_by(Order.customer_id)
    )
    if since is not None:
        query = query.where(Bill.created_at >= since)
    return query.subquery()


def _customer_out(customer: Customer, row) -> schemas.CustomerOut:
    visits = row.visits or 0
    return schemas.CustomerOut(
        id=customer.id,
        phone=customer.phone,
        name=customer.name,
        visits=visits,
        total_spent=_dec(row.spent),
        first_visit=row.first_visit,
        last_visit=row.last_visit,
        is_returning=visits >= 2,
        marketing_opt_out=customer.marketing_opt_out,
        opted_out_at=customer.opted_out_at,
    )


def _top_dishes_query(limit: int, since: datetime | None, customer_id: int | None = None) -> Select:
    quantity = func.sum(OrderItem.quantity)
    revenue = func.sum(OrderItem.unit_price * OrderItem.quantity)
    query = (
        select(
            OrderItem.menu_item_id,
            func.max(OrderItem.name).label("name"),
            quantity.label("quantity"),
            func.count(func.distinct(OrderItem.order_id)).label("orders"),
            revenue.label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .join(Bill, Bill.order_id == Order.id)
        .where(Order.status == OrderStatus.BILLED.value)
        .group_by(OrderItem.menu_item_id)
        .order_by(quantity.desc(), revenue.desc())
        .limit(limit)
    )
    if since is not None:
        query = query.where(Bill.created_at >= since)
    if customer_id is not None:
        query = query.where(Order.customer_id == customer_id)
    return query


def _dish_out(row) -> schemas.TopDishOut:
    return schemas.TopDishOut(
        menu_item_id=row.menu_item_id,
        name=row.name,
        quantity=int(row.quantity),
        orders=int(row.orders),
        revenue=_dec(row.revenue),
    )


# ------------------------------------------------------------ customers


@router.get(
    "/lookup",
    response_model=schemas.CustomerLookupOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def lookup_customer(
    phone: str, session: AsyncSession = Depends(get_session)
) -> schemas.CustomerLookupOut:
    """Used while taking an order to recognise a returning guest by their number."""
    normalized = normalize_phone(phone)
    stats = _stats()
    row = (
        await session.execute(
            select(Customer, stats.c.visits)
            .outerjoin(stats, stats.c.customer_id == Customer.id)
            .where(Customer.phone == normalized)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "New customer")
    customer, visits = row
    visits = visits or 0
    return schemas.CustomerLookupOut(
        id=customer.id,
        phone=customer.phone,
        name=customer.name,
        visits=visits,
        is_returning=visits >= 2,
    )


@router.get(
    "",
    response_model=list[schemas.CustomerOut],
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def list_customers(
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[schemas.CustomerOut]:
    stats = _stats()
    query = (
        select(
            Customer,
            stats.c.visits,
            stats.c.spent,
            stats.c.first_visit,
            stats.c.last_visit,
        )
        .outerjoin(stats, stats.c.customer_id == Customer.id)
        .order_by(func.coalesce(stats.c.visits, 0).desc(), Customer.id)
        .limit(limit)
    )
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(Customer.name.ilike(pattern) | Customer.phone.like(pattern))

    rows = (await session.execute(query)).all()
    return [_customer_out(row[0], row) for row in rows]


@router.get(
    "/{customer_id}",
    response_model=schemas.CustomerDetailOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def customer_detail(
    customer_id: int, session: AsyncSession = Depends(get_session)
) -> schemas.CustomerDetailOut:
    stats = _stats()
    row = (
        await session.execute(
            select(
                Customer,
                stats.c.visits,
                stats.c.spent,
                stats.c.first_visit,
                stats.c.last_visit,
            )
            .outerjoin(stats, stats.c.customer_id == Customer.id)
            .where(Customer.id == customer_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    bills = await session.scalars(
        select(Bill)
        .join(Order, Order.id == Bill.order_id)
        .where(Order.customer_id == customer_id)
        .options(selectinload(Bill.order).selectinload(Order.items))
        .order_by(Bill.id.desc())
    )
    dishes = (await session.execute(_top_dishes_query(5, None, customer_id))).all()

    return schemas.CustomerDetailOut(
        **_customer_out(row[0], row).model_dump(),
        favourite_dishes=[_dish_out(dish) for dish in dishes],
        orders=[
            schemas.CustomerOrderOut(
                order_id=bill.order_id,
                invoice_number=bill.invoice_number,
                billed_at=bill.created_at,
                order_type=bill.order.order_type,
                bill_status=bill.status,
                total=bill.total,
                items=[
                    schemas.OrderedItemOut(name=item.name, quantity=item.quantity)
                    for item in bill.order.items
                ],
            )
            for bill in bills
        ],
    )


@router.put(
    "/{customer_id}/marketing-opt-out",
    response_model=schemas.CustomerOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def update_marketing_opt_out(
    customer_id: int,
    body: schemas.MarketingOptOutIn,
    session: AsyncSession = Depends(get_session),
) -> schemas.CustomerOut:
    """Record that a guest asked (in person, by phone) to stop or resume marketing messages."""
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    set_marketing_opt_out(customer, body.opt_out, "staff")
    await session.commit()
    stats = _stats()
    row = (
        await session.execute(
            select(stats.c.visits, stats.c.spent, stats.c.first_visit, stats.c.last_visit).where(
                stats.c.customer_id == customer_id
            )
        )
    ).first()
    return _customer_out(customer, row or SimpleNamespace(visits=0, spent=0, first_visit=None, last_visit=None))


# -------------------------------------------------------------- reports


@reports_router.get(
    "/top-dishes",
    response_model=list[schemas.TopDishOut],
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def top_dishes(
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[schemas.TopDishOut]:
    """Most ordered dishes across billed orders. Leave `days` empty for all time."""
    rows = (await session.execute(_top_dishes_query(limit, _since(days)))).all()
    return [_dish_out(row) for row in rows]


@reports_router.get(
    "/top-customers",
    response_model=list[schemas.CustomerOut],
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def top_customers(
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[schemas.CustomerOut]:
    """Customers who visit most (billed orders), ties broken by how much they spent."""
    stats = _stats(_since(days))
    rows = (
        await session.execute(
            select(Customer, stats.c.visits, stats.c.spent, stats.c.first_visit, stats.c.last_visit)
            .join(stats, stats.c.customer_id == Customer.id)
            .order_by(stats.c.visits.desc(), stats.c.spent.desc(), Customer.id)
            .limit(limit)
        )
    ).all()
    return [_customer_out(row[0], row) for row in rows]
