from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class RestaurantProfile(Base):
    """One row: the restaurant this deployment belongs to. Created when the owner registers."""

    __tablename__ = "restaurant_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
