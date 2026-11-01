from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class Message(Base):
    """Every WhatsApp message in or out, kept as the conversation log."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(10), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # "in" or "out"
    # chat, booking, reminder, campaign, bill
    kind: Mapped[str] = mapped_column(String(20), default="chat")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="sent")  # sent or failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
