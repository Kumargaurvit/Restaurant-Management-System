from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.chatbot.models import Offer
from restaurant_management_system.chatbot.offers import aware, current_offers, offer_status
from restaurant_management_system.db.session import get_session

router = APIRouter(prefix="/api/offers", tags=["offers"])

MANAGERS = (Role.OWNER, Role.MANAGER)
STAFF = (Role.OWNER, Role.MANAGER, Role.CASHIER, Role.WAITER)


class OfferIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def check_window(self) -> "OfferIn":
        start, end = aware(self.valid_from), aware(self.valid_until)
        if start is not None and end is not None and end <= start:
            raise ValueError("The end time must be after the start time")
        return self


class OfferOut(BaseModel):
    id: int
    title: str
    description: str
    discount_percent: Decimal | None
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    status: str


def _out(offer: Offer) -> OfferOut:
    return OfferOut(
        id=offer.id,
        title=offer.title,
        description=offer.description,
        discount_percent=offer.discount_percent,
        valid_from=offer.valid_from,
        valid_until=offer.valid_until,
        is_active=offer.is_active,
        status=offer_status(offer, datetime.now(UTC)),
    )


@router.get("", response_model=list[OfferOut], dependencies=[Depends(require_roles(*MANAGERS))])
async def list_offers(session: AsyncSession = Depends(get_session)) -> list[OfferOut]:
    offers = await session.scalars(select(Offer).order_by(Offer.id.desc()))
    return [_out(offer) for offer in offers]


@router.get(
    "/active", response_model=list[OfferOut], dependencies=[Depends(require_roles(*STAFF))]
)
async def active_offers(session: AsyncSession = Depends(get_session)) -> list[OfferOut]:
    """Offers valid right now, so staff can quote them and apply a matching discount."""
    active, _ = await current_offers(session, datetime.now(UTC))
    return [_out(offer) for offer in active]


@router.post(
    "",
    response_model=OfferOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def create_offer(body: OfferIn, session: AsyncSession = Depends(get_session)) -> OfferOut:
    offer = Offer(**body.model_dump())
    session.add(offer)
    await session.commit()
    await session.refresh(offer)
    return _out(offer)


@router.put(
    "/{offer_id}", response_model=OfferOut, dependencies=[Depends(require_roles(*MANAGERS))]
)
async def update_offer(
    offer_id: int, body: OfferIn, session: AsyncSession = Depends(get_session)
) -> OfferOut:
    offer = await session.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    for field, value in body.model_dump().items():
        setattr(offer, field, value)
    await session.commit()
    await session.refresh(offer)
    return _out(offer)


@router.delete(
    "/{offer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def delete_offer(offer_id: int, session: AsyncSession = Depends(get_session)) -> None:
    offer = await session.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Offer not found")
    await session.delete(offer)
    await session.commit()
