from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class Customer(Base):
    """A guest, identified by their 10-digit mobile number (also their WhatsApp number)."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Marketing consent (DPDP Act 2023). Bills and booking messages are not marketing.
    marketing_opt_out: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opt_out_source: Mapped[str | None] = mapped_column(String(20))
