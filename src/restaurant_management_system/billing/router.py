from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role, User
from restaurant_management_system.billing import schemas, services
from restaurant_management_system.billing.models import (
    Bill,
    BillStatus,
    MenuCategory,
    MenuItem,
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    Payment,
    RestaurantTable,
)
from restaurant_management_system.billing.receipt import render_kot, render_receipt
from restaurant_management_system.config import Settings, get_settings
from restaurant_management_system.customers.services import get_or_create_customer
from restaurant_management_system.db.session import get_session
from restaurant_management_system.restaurant.services import get_profile

router = APIRouter(prefix="/api/billing", tags=["billing"])

STAFF = (Role.OWNER, Role.MANAGER, Role.CASHIER, Role.WAITER)
BILLERS = (Role.OWNER, Role.MANAGER, Role.CASHIER)
MANAGERS = (Role.OWNER, Role.MANAGER)


# ---------------------------------------------------------------- menu


@router.get(
    "/menu/categories",
    response_model=list[schemas.CategoryOut],
    dependencies=[Depends(require_roles(*STAFF))],
)
async def list_categories(session: AsyncSession = Depends(get_session)) -> list[MenuCategory]:
    result = await session.scalars(
        select(MenuCategory).order_by(MenuCategory.sort_order, MenuCategory.name)
    )
    return list(result)


@router.post(
    "/menu/categories",
    response_model=schemas.CategoryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def create_category(
    body: schemas.CategoryCreate, session: AsyncSession = Depends(get_session)
) -> MenuCategory:
    if await session.scalar(select(MenuCategory).where(MenuCategory.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    category = MenuCategory(name=body.name, sort_order=body.sort_order)
    session.add(category)
    await session.commit()
    return category


@router.get(
    "/menu/items",
    response_model=list[schemas.MenuItemOut],
    dependencies=[Depends(require_roles(*STAFF))],
)
async def list_menu_items(
    available_only: bool = False, session: AsyncSession = Depends(get_session)
) -> list[MenuItem]:
    query = select(MenuItem).order_by(MenuItem.category_id, MenuItem.name)
    if available_only:
        query = query.where(MenuItem.is_available.is_(True))
    return list(await session.scalars(query))


@router.post(
    "/menu/items",
    response_model=schemas.MenuItemOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def create_menu_item(
    body: schemas.MenuItemCreate, session: AsyncSession = Depends(get_session)
) -> MenuItem:
    if await session.get(MenuCategory, body.category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    item = MenuItem(**body.model_dump())
    session.add(item)
    await session.commit()
    return item


@router.patch(
    "/menu/items/{item_id}",
    response_model=schemas.MenuItemOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def update_menu_item(
    item_id: int, body: schemas.MenuItemUpdate, session: AsyncSession = Depends(get_session)
) -> MenuItem:
    item = await session.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("category_id") is not None:
        if await session.get(MenuCategory, changes["category_id"]) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    for field, value in changes.items():
        if value is not None:
            setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


@router.patch(
    "/menu/categories/{category_id}",
    response_model=schemas.CategoryOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def update_category(
    category_id: int, body: schemas.CategoryUpdate, session: AsyncSession = Depends(get_session)
) -> MenuCategory:
    category = await session.get(MenuCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    changes = body.model_dump(exclude_unset=True)
    new_name = changes.get("name")
    if new_name and new_name != category.name:
        if await session.scalar(select(MenuCategory).where(MenuCategory.name == new_name)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    for field, value in changes.items():
        if value is not None:
            setattr(category, field, value)
    await session.commit()
    return category


@router.delete(
    "/menu/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)) -> None:
    category = await session.get(MenuCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if await session.scalar(select(MenuItem.id).where(MenuItem.category_id == category_id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Move or delete this category's items first"
        )
    await session.delete(category)
    await session.commit()


@router.delete(
    "/menu/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def delete_menu_item(item_id: int, session: AsyncSession = Depends(get_session)) -> None:
    item = await session.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")
    if await session.scalar(select(OrderItem.id).where(OrderItem.menu_item_id == item_id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This item has been ordered before. Mark it unavailable instead.",
        )
    await session.delete(item)
    await session.commit()


# -------------------------------------------------------------- tables


@router.get(
    "/tables",
    response_model=list[schemas.TableOut],
    dependencies=[Depends(require_roles(*STAFF))],
)
async def list_tables(session: AsyncSession = Depends(get_session)) -> list[RestaurantTable]:
    return list(await session.scalars(select(RestaurantTable).order_by(RestaurantTable.name)))


@router.post(
    "/tables",
    response_model=schemas.TableOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def create_table(
    body: schemas.TableCreate, session: AsyncSession = Depends(get_session)
) -> RestaurantTable:
    if await session.scalar(select(RestaurantTable).where(RestaurantTable.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Table already exists")
    table = RestaurantTable(name=body.name, capacity=body.capacity)
    session.add(table)
    await session.commit()
    return table


@router.patch(
    "/tables/{table_id}",
    response_model=schemas.TableOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def update_table(
    table_id: int, body: schemas.TableUpdate, session: AsyncSession = Depends(get_session)
) -> RestaurantTable:
    table = await session.get(RestaurantTable, table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    new_name = changes.get("name")
    if new_name and new_name != table.name:
        if await session.scalar(select(RestaurantTable).where(RestaurantTable.name == new_name)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Table already exists")
    if changes.get("is_active") is False:
        busy = await session.scalar(
            select(Order.id).where(
                Order.table_id == table_id, Order.status == OrderStatus.OPEN.value
            )
        )
        if busy is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Table has an open order")
    for field, value in changes.items():
        setattr(table, field, value)
    await session.commit()
    return table


@router.delete(
    "/tables/{table_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def delete_table(table_id: int, session: AsyncSession = Depends(get_session)) -> None:
    table = await session.get(RestaurantTable, table_id)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")
    if await session.scalar(select(Order.id).where(Order.table_id == table_id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This table has order history. Deactivate it instead."
        )
    await session.delete(table)
    await session.commit()


# -------------------------------------------------------------- orders


@router.get(
    "/orders",
    response_model=list[schemas.OrderOut],
    dependencies=[Depends(require_roles(*STAFF))],
)
async def list_orders(
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> list[Order]:
    query = select(Order).options(selectinload(Order.items)).order_by(Order.id.desc())
    if order_status is not None:
        query = query.where(Order.status == order_status.value)
    return list(await session.scalars(query))


@router.post(
    "/orders",
    response_model=schemas.OrderOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    body: schemas.OrderCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(*STAFF)),
) -> Order:
    if body.order_type == OrderType.DINE_IN:
        if body.table_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Dine-in needs a table")
        table = await session.get(RestaurantTable, body.table_id)
        if table is None or not table.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found")
        busy = await session.scalar(
            select(Order.id).where(
                Order.table_id == body.table_id, Order.status == OrderStatus.OPEN.value
            )
        )
        if busy is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Table already has an open order")
    elif body.order_type == OrderType.DELIVERY and not body.delivery_address:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Delivery needs an address")

    order = Order(
        order_type=body.order_type.value,
        table_id=body.table_id if body.order_type == OrderType.DINE_IN else None,
        customer_name=body.customer_name,
        delivery_address=body.delivery_address,
        created_by=user.id,
    )
    if body.customer_phone:
        customer = await get_or_create_customer(session, body.customer_phone, body.customer_name)
        order.customer_id = customer.id
        order.customer_phone = customer.phone
        order.customer_name = customer.name
    session.add(order)
    await session.commit()
    return await services.get_order(session, order.id)


@router.get(
    "/orders/{order_id}",
    response_model=schemas.OrderOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def read_order(order_id: int, session: AsyncSession = Depends(get_session)) -> Order:
    return await services.get_order(session, order_id)


@router.post(
    "/orders/{order_id}/items",
    response_model=schemas.OrderOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def add_order_item(
    order_id: int, body: schemas.OrderItemAdd, session: AsyncSession = Depends(get_session)
) -> Order:
    order = await services.get_order(session, order_id)
    services.require_open(order)

    menu_item = await session.get(MenuItem, body.menu_item_id)
    if menu_item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")
    if not menu_item.is_available:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{menu_item.name} is not available")

    existing = next(
        (
            line
            for line in order.items
            if line.menu_item_id == menu_item.id
            and line.kitchen_ticket_id is None
            and line.notes == body.notes
        ),
        None,
    )
    if existing is not None:
        existing.quantity += body.quantity
    else:
        session.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                name=menu_item.name,
                unit_price=menu_item.price,
                gst_rate=menu_item.gst_rate,
                quantity=body.quantity,
                notes=body.notes,
            )
        )
    await session.commit()
    return await services.get_order(session, order_id)


@router.patch(
    "/orders/{order_id}/items/{item_id}",
    response_model=schemas.OrderOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def update_order_item(
    order_id: int,
    item_id: int,
    body: schemas.OrderItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> Order:
    order = await services.get_order(session, order_id)
    services.require_open(order)
    line = next((line for line in order.items if line.id == item_id), None)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order item not found")

    if body.quantity == 0:
        order.items.remove(line)
    else:
        line.quantity = body.quantity
    await session.commit()
    return await services.get_order(session, order_id)


@router.put(
    "/orders/{order_id}/customer",
    response_model=schemas.OrderOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def set_order_customer(
    order_id: int, body: schemas.OrderCustomerSet, session: AsyncSession = Depends(get_session)
) -> Order:
    """Attach a guest to an order (they may only give their number after ordering)."""
    order = await services.get_order(session, order_id)
    services.require_open(order)
    customer = await get_or_create_customer(session, body.phone, body.name)
    order.customer_id = customer.id
    order.customer_phone = customer.phone
    order.customer_name = customer.name
    await session.commit()
    return await services.get_order(session, order_id)


@router.post(
    "/orders/{order_id}/cancel",
    response_model=schemas.OrderOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def cancel_order(order_id: int, session: AsyncSession = Depends(get_session)) -> Order:
    order = await services.get_order(session, order_id)
    services.require_open(order)
    order.status = OrderStatus.CANCELLED.value
    await session.commit()
    return await services.get_order(session, order_id)


@router.post(
    "/orders/{order_id}/kot",
    response_model=schemas.KitchenTicketOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def send_to_kitchen(order_id: int, session: AsyncSession = Depends(get_session)):
    order = await services.get_order(session, order_id)
    return await services.create_kitchen_ticket(session, order)


@router.get(
    "/kot/{ticket_id}/print",
    dependencies=[Depends(require_roles(*STAFF))],
)
async def print_kot(
    ticket_id: int,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    ticket = await services.get_ticket(session, ticket_id)
    order = await services.get_order(session, ticket.order_id)
    text = render_kot(ticket, order, ZoneInfo(settings.timezone))
    return Response(text, media_type="text/plain; charset=utf-8")


# --------------------------------------------------------------- bills


@router.post(
    "/orders/{order_id}/bill",
    response_model=schemas.BillOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_bill(
    order_id: int,
    body: schemas.BillCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_roles(*BILLERS)),
) -> Bill:
    order = await services.get_order(session, order_id)
    return await services.generate_bill(session, order, body.discount, user.id)


@router.get(
    "/orders/{order_id}/bill",
    response_model=schemas.BillOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def read_order_bill(order_id: int, session: AsyncSession = Depends(get_session)) -> Bill:
    bill = await session.scalar(select(Bill).where(Bill.order_id == order_id))
    if bill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This order has no bill yet")
    return await services.get_bill(session, bill.id)


@router.get(
    "/bills",
    response_model=list[schemas.BillOut],
    dependencies=[Depends(require_roles(*STAFF))],
)
async def list_bills(
    bill_status: BillStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> list[Bill]:
    query = select(Bill).options(selectinload(Bill.payments)).order_by(Bill.id.desc())
    if bill_status is not None:
        query = query.where(Bill.status == bill_status.value)
    return list(await session.scalars(query))


@router.get(
    "/bills/{bill_id}",
    response_model=schemas.BillOut,
    dependencies=[Depends(require_roles(*STAFF))],
)
async def read_bill(bill_id: int, session: AsyncSession = Depends(get_session)) -> Bill:
    return await services.get_bill(session, bill_id)


@router.post(
    "/bills/{bill_id}/payments",
    response_model=schemas.BillOut,
    dependencies=[Depends(require_roles(*BILLERS))],
)
async def add_payment(
    bill_id: int, body: schemas.PaymentCreate, session: AsyncSession = Depends(get_session)
) -> Bill:
    bill = await services.get_bill(session, bill_id)
    return await services.record_payment(session, bill, body)


@router.get(
    "/bills/{bill_id}/receipt",
    dependencies=[Depends(require_roles(*STAFF))],
)
async def print_receipt(
    bill_id: int,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    bill = await services.get_bill(session, bill_id)
    profile = await get_profile(session)
    text = render_receipt(bill, bill.order, ZoneInfo(settings.timezone), profile)
    return Response(text, media_type="text/plain; charset=utf-8")


# ------------------------------------------------------------- reports


@router.get(
    "/reports/daily",
    response_model=schemas.DailySalesOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def daily_sales(
    day: date | None = None,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> schemas.DailySalesOut:
    zone = ZoneInfo(settings.timezone)
    day = day or datetime.now(zone).date()
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = start + timedelta(days=1)

    bill_count, total_sales = (
        await session.execute(
            select(func.count(Bill.id), func.coalesce(func.sum(Bill.total), 0)).where(
                Bill.created_at >= start, Bill.created_at < end
            )
        )
    ).one()

    by_mode = dict(
        (
            await session.execute(
                select(Payment.mode, func.sum(Payment.amount))
                .where(Payment.created_at >= start, Payment.created_at < end)
                .group_by(Payment.mode)
            )
        ).all()
    )

    def amount(mode: str) -> Decimal:
        return Decimal(by_mode.get(mode) or 0)

    return schemas.DailySalesOut(
        day=day,
        bill_count=bill_count,
        total_sales=Decimal(total_sales),
        cash=amount("cash"),
        upi=amount("upi"),
        card=amount("card"),
    )
