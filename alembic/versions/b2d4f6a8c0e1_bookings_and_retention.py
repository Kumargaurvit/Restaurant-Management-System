"""bookings, retention and messaging

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-10-22 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=10), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_phone'), 'messages', ['phone'], unique=False)
    op.create_index(op.f('ix_messages_created_at'), 'messages', ['created_at'], unique=False)

    op.create_table('booking_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('opens_at', sa.Time(), nullable=False),
    sa.Column('closes_at', sa.Time(), nullable=False),
    sa.Column('slot_minutes', sa.Integer(), nullable=False),
    sa.Column('max_party_size', sa.Integer(), nullable=False),
    sa.Column('max_days_ahead', sa.Integer(), nullable=False),
    sa.Column('reminder_hours_before', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('guest_name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=10), nullable=False),
    sa.Column('party_size', sa.Integer(), nullable=False),
    sa.Column('booking_date', sa.Date(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('slot_minutes', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('notes', sa.String(length=300), nullable=True),
    sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bookings_customer_id'), 'bookings', ['customer_id'], unique=False)
    op.create_index(op.f('ix_bookings_booking_date'), 'bookings', ['booking_date'], unique=False)
    op.create_index(op.f('ix_bookings_status'), 'bookings', ['status'], unique=False)

    op.create_table('retention_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('at_risk_days', sa.Integer(), nullable=False),
    sa.Column('lost_days', sa.Integer(), nullable=False),
    sa.Column('vip_min_visits', sa.Integer(), nullable=False),
    sa.Column('vip_min_spend', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('campaign_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('segment', sa.String(length=20), nullable=False),
    sa.Column('template', sa.Text(), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('cooldown_days', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('campaign_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=10), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['rule_id'], ['campaign_rules.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_campaign_messages_rule_id'), 'campaign_messages', ['rule_id'], unique=False)
    op.create_index(op.f('ix_campaign_messages_customer_id'), 'campaign_messages', ['customer_id'], unique=False)
    op.create_index(op.f('ix_campaign_messages_status'), 'campaign_messages', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('campaign_messages')
    op.drop_table('campaign_rules')
    op.drop_table('retention_settings')
    op.drop_table('bookings')
    op.drop_table('booking_settings')
    op.drop_table('messages')
