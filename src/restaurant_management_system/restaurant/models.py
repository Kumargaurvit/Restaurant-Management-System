from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class RestaurantProfile(Base):
    """The single row describing this restaurant; printed on receipts."""

    __tablename__ = "restaurant_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    gstin: Mapped[str] = mapped_column(String(15), default="")
    fssai: Mapped[str] = mapped_column(String(14), default="")
    receipt_footer: Mapped[str] = mapped_column(String(200), default="")
