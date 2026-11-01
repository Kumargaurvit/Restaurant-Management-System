from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from restaurant_management_system.db.base import Base


class Segment(StrEnum):
    REGULAR = "regular"
    NEW = "new"
    AT_RISK = "at_risk"
    LOST = "lost"


class Mode(StrEnum):
    AUTOMATIC = "automatic"
    APPROVAL = "approval"


class MessageStatus(StrEnum):
    PENDING = "pending"  # waiting for the owner's approval
    SENT = "sent"
    FAILED = "failed"
    REJECTED = "rejected"
    SKIPPED = "skipped"  # guest opted out before it was sent


class RetentionSettings(Base):
    """One row: the owner's segment thresholds. Created with defaults on first use."""

    __tablename__ = "retention_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    at_risk_days: Mapped[int]  # no visit for this many days -> at risk
    lost_days: Mapped[int]  # no visit for this many days -> lost


class CampaignRule(Base):
    __tablename__ = "campaign_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    segment: Mapped[str] = mapped_column(String(20))
    template: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20), default=Mode.APPROVAL.value)
    # A guest is not messaged by the same rule again within this many days.
    cooldown_days: Mapped[int] = mapped_column(default=30)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignMessage(Base):
    __tablename__ = "campaign_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("campaign_rules.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    phone: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=MessageStatus.PENDING.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
