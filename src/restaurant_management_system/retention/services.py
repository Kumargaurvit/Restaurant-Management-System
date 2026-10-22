from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.billing.models import Bill, Order
from restaurant_management_system.customers.models import Customer
from restaurant_management_system.messaging.models import Message
from restaurant_management_system.messaging.provider import MessageProvider, send_message
from restaurant_management_system.retention.models import (
    CampaignMessage,
    CampaignRule,
    MessageStatus,
    Mode,
    RetentionSettings,
    Segment,
)

OPT_OUT_FOOTER = "\nReply STOP to opt out."


@dataclass
class Member:
    customer: Customer
    visits: int
    total_spent: Decimal
    days_since_visit: int
    segment: str
    recency_score: int
    frequency_score: int
    monetary_score: int


def _aware(moment: datetime) -> datetime:
    # Some drivers return timestamps without tzinfo; they are stored in UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _score(value: float, cutoffs: list[float], *, lower_is_better: bool = False) -> int:
    """Map a value to 1-5 by four cutoffs."""
    steps = sum(1 for cutoff in cutoffs if value > cutoff)
    return 5 - steps if lower_is_better else 1 + steps


def recency_score(days: int) -> int:
    return _score(days, [15, 30, 60, 90], lower_is_better=True)


def frequency_score(visits: int) -> int:
    return _score(visits, [1, 2, 4, 9])


def monetary_score(spent: Decimal) -> int:
    return _score(float(spent), [500, 1500, 3000, 6000])


def classify(visits: int, spent: Decimal, days: int, settings: RetentionSettings) -> str:
    if days >= settings.lost_days:
        return Segment.LOST.value
    if days >= settings.at_risk_days:
        return Segment.AT_RISK.value
    if visits <= 1:
        return Segment.NEW.value
    return Segment.REGULAR.value


async def get_settings_row(session: AsyncSession) -> RetentionSettings:
    row = await session.scalar(select(RetentionSettings))
    if row is None:
        row = RetentionSettings(at_risk_days=45, lost_days=90)
        session.add(row)
        await session.flush()
    return row


async def compute_members(session: AsyncSession, now: datetime | None = None) -> list[Member]:
    """Every customer with at least one bill, scored and segmented."""
    now = now or datetime.now(UTC)
    settings = await get_settings_row(session)
    rows = (
        await session.execute(
            select(
                Customer,
                func.count(Bill.id),
                func.coalesce(func.sum(Bill.total), 0),
                func.max(Bill.created_at),
            )
            .join(Order, Order.customer_id == Customer.id)
            .join(Bill, Bill.order_id == Order.id)
            .group_by(Customer.id)
            .order_by(Customer.id)
        )
    ).all()

    members = []
    for customer, visits, spent, last in rows:
        spent = Decimal(str(spent))
        days = max((now - _aware(last)).days, 0)
        members.append(
            Member(
                customer=customer,
                visits=visits,
                total_spent=spent,
                days_since_visit=days,
                segment=classify(visits, spent, days, settings),
                recency_score=recency_score(days),
                frequency_score=frequency_score(visits),
                monetary_score=monetary_score(spent),
            )
        )
    return members


def render_template(template: str, member: Member, restaurant: str) -> str:
    values = {
        "name": member.customer.name or "there",
        "visits": str(member.visits),
        "days_since_visit": str(member.days_since_visit),
        "restaurant": restaurant,
    }
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text.strip() + OPT_OUT_FOOTER


async def _deliver(
    session: AsyncSession, provider: MessageProvider, campaign_message: CampaignMessage
) -> None:
    sent = await send_message(
        session, provider, campaign_message.phone, campaign_message.body, "campaign"
    )
    campaign_message.status = (
        MessageStatus.SENT.value if sent.status == "sent" else MessageStatus.FAILED.value
    )
    campaign_message.sent_at = datetime.now(UTC).replace(microsecond=0)


async def run_rule(
    session: AsyncSession,
    provider: MessageProvider,
    rule: CampaignRule,
    members: list[Member],
    restaurant: str,
    now: datetime,
) -> tuple[int, int, int]:
    """Queue or send one rule's messages. Returns (queued, sent, skipped for cooldown)."""
    since = now - timedelta(days=rule.cooldown_days)
    recently = set(
        await session.scalars(
            select(CampaignMessage.customer_id).where(
                CampaignMessage.rule_id == rule.id, CampaignMessage.created_at >= since
            )
        )
    )

    queued = sent = skipped = 0
    for member in members:
        if member.segment != rule.segment or member.customer.marketing_opt_out:
            continue
        if member.customer.id in recently:
            skipped += 1
            continue
        message = CampaignMessage(
            rule_id=rule.id,
            customer_id=member.customer.id,
            phone=member.customer.phone,
            body=render_template(rule.template, member, restaurant),
        )
        session.add(message)
        if rule.mode == Mode.AUTOMATIC.value:
            await _deliver(session, provider, message)
            sent += message.status == MessageStatus.SENT.value
        else:
            queued += 1
    await session.flush()
    return queued, sent, skipped


async def run_rules(
    session: AsyncSession,
    provider: MessageProvider,
    restaurant: str,
    rule_ids: list[int] | None = None,
    automatic_only: bool = False,
) -> dict[str, int]:
    now = datetime.now(UTC)
    query = select(CampaignRule).where(CampaignRule.is_active.is_(True))
    if rule_ids is not None:
        query = query.where(CampaignRule.id.in_(rule_ids))
    if automatic_only:
        query = query.where(CampaignRule.mode == Mode.AUTOMATIC.value)
    rules = list(await session.scalars(query))
    members = await compute_members(session, now) if rules else []

    totals = {"rules_run": len(rules), "queued": 0, "sent": 0, "skipped_cooldown": 0}
    for rule in rules:
        queued, sent, skipped = await run_rule(session, provider, rule, members, restaurant, now)
        totals["queued"] += queued
        totals["sent"] += sent
        totals["skipped_cooldown"] += skipped
    return totals


async def decide(
    session: AsyncSession,
    provider: MessageProvider,
    message: CampaignMessage,
    approve: bool,
) -> CampaignMessage:
    if message.status != MessageStatus.PENDING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "This message was already handled.")
    if not approve:
        message.status = MessageStatus.REJECTED.value
        return message

    customer = await session.get(Customer, message.customer_id)
    if customer is None or customer.marketing_opt_out:
        # They may have opted out while the message waited in the queue.
        message.status = MessageStatus.SKIPPED.value
        return message
    await _deliver(session, provider, message)
    return message


async def report(session: AsyncSession) -> list[dict]:
    rules = list(await session.scalars(select(CampaignRule).order_by(CampaignRule.id)))
    result = []
    for rule in rules:
        messages = list(
            await session.scalars(select(CampaignMessage).where(CampaignMessage.rule_id == rule.id))
        )
        counts = {state.value: 0 for state in MessageStatus}
        replied = visited = 0
        for message in messages:
            counts[message.status] += 1
            if message.status != MessageStatus.SENT.value or message.sent_at is None:
                continue
            sent_at = _aware(message.sent_at)
            # Compared in Python: SQLite stores timestamps as text, so SQL comparisons are unreliable.
            replies = await session.scalars(
                select(Message.created_at).where(
                    Message.phone == message.phone, Message.direction == "in"
                )
            )
            visits = await session.scalars(
                select(Bill.created_at)
                .join(Order, Order.id == Bill.order_id)
                .where(Order.customer_id == message.customer_id)
            )
            reply = any(_aware(moment) >= sent_at for moment in replies)
            visit = any(_aware(moment) >= sent_at for moment in visits)
            replied += reply
            visited += visit
        result.append(
            {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "pending": counts["pending"],
                "sent": counts["sent"],
                "failed": counts["failed"],
                "rejected": counts["rejected"],
                "skipped": counts["skipped"],
                "replied": replied,
                "visited_after": visited,
            }
        )
    return result
