from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.db.session import get_session
from restaurant_management_system.restaurant import schemas
from restaurant_management_system.restaurant.models import RestaurantProfile
from restaurant_management_system.restaurant.services import get_profile

router = APIRouter(prefix="/api/restaurant", tags=["restaurant"])


@router.get(
    "",
    response_model=schemas.ProfileOut,
    dependencies=[Depends(require_roles(Role.OWNER, Role.MANAGER, Role.CASHIER, Role.WAITER))],
)
async def read_profile(session: AsyncSession = Depends(get_session)) -> RestaurantProfile:
    return await get_profile(session)


@router.put(
    "",
    response_model=schemas.ProfileOut,
    dependencies=[Depends(require_roles(Role.OWNER, Role.MANAGER))],
)
async def update_profile(
    body: schemas.ProfileIn, session: AsyncSession = Depends(get_session)
) -> RestaurantProfile:
    profile = await session.get(RestaurantProfile, 1)
    if profile is None:
        profile = RestaurantProfile(id=1)
        session.add(profile)
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    await session.commit()
    return profile
