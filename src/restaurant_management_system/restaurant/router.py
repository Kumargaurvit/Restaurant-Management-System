from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import get_current_user, require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.db.session import get_session
from restaurant_management_system.restaurant import services

router = APIRouter(prefix="/api/restaurant", tags=["restaurant"])


class RestaurantIn(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")


class RestaurantOut(BaseModel):
    name: str | None


@router.get("", response_model=RestaurantOut, dependencies=[Depends(get_current_user)])
async def read_restaurant(session: AsyncSession = Depends(get_session)) -> RestaurantOut:
    return RestaurantOut(name=await services.get_restaurant_name(session))


@router.put("", response_model=RestaurantOut, dependencies=[Depends(require_roles(Role.OWNER))])
async def rename_restaurant(
    body: RestaurantIn, session: AsyncSession = Depends(get_session)
) -> RestaurantOut:
    profile = await services.set_restaurant_name(session, body.name)
    await session.commit()
    return RestaurantOut(name=profile.name)
