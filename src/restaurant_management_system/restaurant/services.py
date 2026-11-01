from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.restaurant.models import RestaurantProfile

# Used in guest messages when no name has been saved yet (accounts made before names existed).
FALLBACK_NAME = "our restaurant"


async def get_profile(session: AsyncSession) -> RestaurantProfile | None:
    return await session.scalar(select(RestaurantProfile))


async def get_restaurant_name(session: AsyncSession) -> str | None:
    profile = await get_profile(session)
    return profile.name if profile else None


async def set_restaurant_name(session: AsyncSession, name: str) -> RestaurantProfile:
    profile = await get_profile(session)
    if profile is None:
        profile = RestaurantProfile(name=name.strip())
        session.add(profile)
    else:
        profile.name = name.strip()
    await session.flush()
    return profile
