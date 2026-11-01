from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SegmentName = Literal["regular", "new", "at_risk", "lost"]
ModeName = Literal["automatic", "approval"]


class SettingsIn(BaseModel):
    at_risk_days: int = Field(ge=1, le=3650)
    lost_days: int = Field(ge=1, le=3650)

    @model_validator(mode="after")
    def _lost_after_at_risk(self) -> "SettingsIn":
        if self.lost_days <= self.at_risk_days:
            raise ValueError("'Lost' must be later than 'at risk'")
        return self


class SettingsOut(SettingsIn):
    model_config = ConfigDict(from_attributes=True)


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    segment: SegmentName
    template: str = Field(min_length=1, max_length=900)
    mode: ModeName = "approval"
    cooldown_days: int = Field(default=30, ge=1, le=365)
    is_active: bool = True


class RuleOut(RuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RuleActiveIn(BaseModel):
    is_active: bool


class MemberOut(BaseModel):
    customer_id: int
    name: str | None
    phone: str
    segment: str
    visits: int
    total_spent: Decimal
    days_since_visit: int
    recency_score: int
    frequency_score: int
    monetary_score: int
    marketing_opt_out: bool


class SegmentSummaryOut(BaseModel):
    segment: str
    customers: int


class SegmentsOut(BaseModel):
    summary: list[SegmentSummaryOut]
    members: list[MemberOut]


class CampaignMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    rule_name: str
    customer_id: int
    customer_name: str | None
    phone: str
    body: str
    status: str
    created_at: datetime
    sent_at: datetime | None


class RunOut(BaseModel):
    rules_run: int
    queued: int
    sent: int
    skipped_cooldown: int


class RuleReportOut(BaseModel):
    rule_id: int
    rule_name: str
    pending: int
    sent: int
    failed: int
    rejected: int
    skipped: int
    replied: int
    visited_after: int
