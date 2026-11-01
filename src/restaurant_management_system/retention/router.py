from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.customers.models import Customer
from restaurant_management_system.db.session import get_session
from restaurant_management_system.messaging.provider import MessageProvider, get_provider
from restaurant_management_system.restaurant.services import FALLBACK_NAME, get_restaurant_name
from restaurant_management_system.retention import schemas, services
from restaurant_management_system.retention.models import (
    CampaignMessage,
    CampaignRule,
    Segment,
)

router = APIRouter(
    prefix="/api/retention",
    tags=["retention"],
    dependencies=[Depends(require_roles(Role.OWNER, Role.MANAGER))],
)

SEGMENT_ORDER = [Segment.REGULAR, Segment.NEW, Segment.AT_RISK, Segment.LOST]


# ------------------------------------------------------------ settings


@router.get("/settings", response_model=schemas.SettingsOut)
async def read_settings(session: AsyncSession = Depends(get_session)):
    row = await services.get_settings_row(session)
    await session.commit()
    return row


@router.put("/settings", response_model=schemas.SettingsOut)
async def update_settings(body: schemas.SettingsIn, session: AsyncSession = Depends(get_session)):
    row = await services.get_settings_row(session)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    await session.commit()
    return row


# ------------------------------------------------------------ segments


@router.get("/segments", response_model=schemas.SegmentsOut)
async def segments(
    segment: str | None = None, session: AsyncSession = Depends(get_session)
) -> schemas.SegmentsOut:
    """RFM scores and the segment of every customer who has been billed."""
    members = await services.compute_members(session)
    await session.commit()
    summary = [
        schemas.SegmentSummaryOut(
            segment=name.value, customers=sum(1 for m in members if m.segment == name.value)
        )
        for name in SEGMENT_ORDER
    ]
    shown = [m for m in members if segment is None or m.segment == segment]
    shown.sort(key=lambda m: (m.days_since_visit, -m.visits))
    return schemas.SegmentsOut(
        summary=summary,
        members=[
            schemas.MemberOut(
                customer_id=m.customer.id,
                name=m.customer.name,
                phone=m.customer.phone,
                segment=m.segment,
                visits=m.visits,
                total_spent=m.total_spent,
                days_since_visit=m.days_since_visit,
                recency_score=m.recency_score,
                frequency_score=m.frequency_score,
                monetary_score=m.monetary_score,
                marketing_opt_out=m.customer.marketing_opt_out,
            )
            for m in shown
        ],
    )


# --------------------------------------------------------------- rules


@router.get("/rules", response_model=list[schemas.RuleOut])
async def list_rules(session: AsyncSession = Depends(get_session)):
    return list(await session.scalars(select(CampaignRule).order_by(CampaignRule.id)))


@router.post("/rules", response_model=schemas.RuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(body: schemas.RuleIn, session: AsyncSession = Depends(get_session)):
    rule = CampaignRule(**body.model_dump())
    session.add(rule)
    await session.commit()
    return rule


@router.put("/rules/{rule_id}", response_model=schemas.RuleOut)
async def update_rule(
    rule_id: int, body: schemas.RuleIn, session: AsyncSession = Depends(get_session)
):
    rule = await session.get(CampaignRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    for field, value in body.model_dump().items():
        setattr(rule, field, value)
    await session.commit()
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, session: AsyncSession = Depends(get_session)) -> None:
    """Deactivates the rule. Its sent messages stay so the report keeps its history."""
    rule = await session.get(CampaignRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    rule.is_active = False
    await session.commit()


@router.post("/run", response_model=schemas.RunOut)
async def run_now(
    rule_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    provider: MessageProvider = Depends(get_provider),
) -> dict[str, int]:
    """Run all active rules (or one) now. Automatic rules send; approval rules queue."""
    result = await services.run_rules(
        session,
        provider,
        await get_restaurant_name(session) or FALLBACK_NAME,
        rule_ids=[rule_id] if rule_id is not None else None,
    )
    await session.commit()
    return result


# ------------------------------------------------------ approval queue


async def _message_out(session: AsyncSession, message: CampaignMessage) -> schemas.CampaignMessageOut:
    rule = await session.get(CampaignRule, message.rule_id)
    customer = await session.get(Customer, message.customer_id)
    return schemas.CampaignMessageOut(
        id=message.id,
        rule_id=message.rule_id,
        rule_name=rule.name if rule else "",
        customer_id=message.customer_id,
        customer_name=customer.name if customer else None,
        phone=message.phone,
        body=message.body,
        status=message.status,
        created_at=message.created_at,
        sent_at=message.sent_at,
    )


@router.get("/messages", response_model=list[schemas.CampaignMessageOut])
async def list_messages(
    message_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    query = select(CampaignMessage).order_by(CampaignMessage.id.desc()).limit(limit)
    if message_status:
        query = query.where(CampaignMessage.status == message_status)
    return [await _message_out(session, m) for m in await session.scalars(query)]


async def _decide(
    session: AsyncSession, provider: MessageProvider, message_id: int, approve: bool
) -> schemas.CampaignMessageOut:
    message = await session.get(CampaignMessage, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    await services.decide(session, provider, message, approve)
    await session.commit()
    return await _message_out(session, message)


@router.post("/messages/{message_id}/approve", response_model=schemas.CampaignMessageOut)
async def approve_message(
    message_id: int,
    session: AsyncSession = Depends(get_session),
    provider: MessageProvider = Depends(get_provider),
):
    return await _decide(session, provider, message_id, True)


@router.post("/messages/{message_id}/reject", response_model=schemas.CampaignMessageOut)
async def reject_message(
    message_id: int,
    session: AsyncSession = Depends(get_session),
    provider: MessageProvider = Depends(get_provider),
):
    return await _decide(session, provider, message_id, False)


# -------------------------------------------------------------- report


@router.get("/report", response_model=list[schemas.RuleReportOut])
async def campaign_report(session: AsyncSession = Depends(get_session)):
    return await services.report(session)

