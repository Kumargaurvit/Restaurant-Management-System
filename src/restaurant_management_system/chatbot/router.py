import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import require_roles
from restaurant_management_system.auth.models import Role
from restaurant_management_system.chatbot.llm import LLMClient, get_optional_llm
from restaurant_management_system.chatbot.models import ChatMessage, Conversation
from restaurant_management_system.chatbot.service import handle_guest_message
from restaurant_management_system.config import Settings, get_settings
from restaurant_management_system.customers.models import Customer
from restaurant_management_system.db.session import get_session
from restaurant_management_system.messaging.base import MessageProvider
from restaurant_management_system.messaging.factory import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chatbot"])

MANAGERS = (Role.OWNER, Role.MANAGER)


class InboundMessage(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=4000)


class ReplyOut(BaseModel):
    reply: str
    needs_human: bool


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    phone: str
    customer_name: str | None
    needs_human: bool
    handoff_reason: str | None
    last_message_at: datetime
    message_count: int
    last_message: str | None


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


@router.post("/webhook", response_model=ReplyOut)
async def webhook(
    body: InboundMessage,
    x_webhook_secret: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    llm: LLMClient | None = Depends(get_optional_llm),
    provider: MessageProvider = Depends(get_provider),
) -> ReplyOut:
    """Inbound guest message from the messaging provider. The reply is also sent to the guest."""
    if not settings.webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Chat webhook is not enabled")
    if not x_webhook_secret or not secrets.compare_digest(x_webhook_secret, settings.webhook_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook secret")

    result = await handle_guest_message(session, llm, settings, body.phone, body.text)
    try:
        await provider.send_text(result.conversation.phone, result.reply)
    except Exception:  # the reply is stored either way; a person can resend it
        logger.exception("Could not send WhatsApp reply to %s", result.conversation.phone)
    return ReplyOut(reply=result.reply, needs_human=result.needs_human)


@router.post(
    "/simulate",
    response_model=ReplyOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def simulate(
    body: InboundMessage,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    llm: LLMClient | None = Depends(get_optional_llm),
) -> ReplyOut:
    """Try the bot as a guest would. Nothing is sent to WhatsApp."""
    result = await handle_guest_message(session, llm, settings, body.phone, body.text)
    return ReplyOut(reply=result.reply, needs_human=result.needs_human)


async def _summaries(
    session: AsyncSession, conversations: list[Conversation]
) -> list[ConversationOut]:
    ids = [c.id for c in conversations]
    counts = dict(
        (
            await session.execute(
                select(ChatMessage.conversation_id, func.count())
                .where(ChatMessage.conversation_id.in_(ids))
                .group_by(ChatMessage.conversation_id)
            )
        ).all()
    )
    latest_ids = (
        select(func.max(ChatMessage.id))
        .where(ChatMessage.conversation_id.in_(ids))
        .group_by(ChatMessage.conversation_id)
    )
    last = {
        m.conversation_id: m.content
        for m in await session.scalars(select(ChatMessage).where(ChatMessage.id.in_(latest_ids)))
    }
    customer_ids = [c.customer_id for c in conversations if c.customer_id]
    names = dict(
        (
            await session.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
            )
        ).all()
    )
    return [
        ConversationOut(
            id=c.id,
            phone=c.phone,
            customer_name=names.get(c.customer_id),
            needs_human=c.needs_human,
            handoff_reason=c.handoff_reason,
            last_message_at=c.last_message_at,
            message_count=counts.get(c.id, 0),
            last_message=last.get(c.id),
        )
        for c in conversations
    ]


@router.get(
    "/conversations",
    response_model=list[ConversationOut],
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def list_conversations(session: AsyncSession = Depends(get_session)) -> list[ConversationOut]:
    conversations = list(
        await session.scalars(
            select(Conversation)
            .order_by(Conversation.needs_human.desc(), Conversation.last_message_at.desc())
            .limit(100)
        )
    )
    return await _summaries(session, conversations)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def read_conversation(
    conversation_id: int, session: AsyncSession = Depends(get_session)
) -> ConversationDetailOut:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    summary = (await _summaries(session, [conversation]))[0]
    messages = await session.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id)
    )
    return ConversationDetailOut(
        **summary.model_dump(), messages=[MessageOut.model_validate(m) for m in messages]
    )


@router.post(
    "/conversations/{conversation_id}/resolve",
    response_model=ConversationOut,
    dependencies=[Depends(require_roles(*MANAGERS))],
)
async def resolve_conversation(
    conversation_id: int, session: AsyncSession = Depends(get_session)
) -> ConversationOut:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    conversation.needs_human = False
    conversation.handoff_reason = None
    await session.commit()
    return (await _summaries(session, [conversation]))[0]
