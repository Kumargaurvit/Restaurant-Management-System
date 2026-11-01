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


async def get_profile_or_blank(session: AsyncSession) -> RestaurantProfile:
    """The saved profile, or an empty one (not saved) so callers can always read its fields."""
    profile = await get_profile(session)
    if profile is None:
        return RestaurantProfile(
            name="", address="", phone="", gstin="", fssai="", receipt_footer=""
        )
    return profile


async def update_details(session: AsyncSession, details: dict[str, str]) -> RestaurantProfile:
    """Save the receipt details. Creates the profile (with no name yet) if none exists."""
    profile = await get_profile(session)
    if profile is None:
        profile = RestaurantProfile(name="")
        session.add(profile)
    for field, value in details.items():
        setattr(profile, field, value)
    await session.flush()
    return profile
