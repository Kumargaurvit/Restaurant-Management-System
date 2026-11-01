from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.restaurant.models import RestaurantProfile


async def get_profile(session: AsyncSession) -> RestaurantProfile:
    """The saved profile, or an empty one (not persisted) if none has been saved yet."""
    profile = await session.get(RestaurantProfile, 1)
    if profile is None:
        return RestaurantProfile(
            id=1, name="", address="", phone="", gstin="", fssai="", receipt_footer=""
        )
    return profile
