from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class RestaurantProfile(Base):
    """One row: the restaurant this deployment belongs to. Created when the owner registers.

    `name` is set at registration. The other fields are the details printed on receipts.
    """

    __tablename__ = "restaurant_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(300), default="", server_default="")
    phone: Mapped[str] = mapped_column(String(20), default="", server_default="")
    gstin: Mapped[str] = mapped_column(String(15), default="", server_default="")
    fssai: Mapped[str] = mapped_column(String(14), default="", server_default="")
    receipt_footer: Mapped[str] = mapped_column(String(200), default="", server_default="")
