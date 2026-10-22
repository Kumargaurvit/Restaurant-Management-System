"""restaurant profile; remove the VIP segment

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-10-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e5a7b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('restaurant_profile',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # A rule aimed at the removed VIP segment is paused rather than silently re-targeted.
    op.execute("UPDATE campaign_rules SET segment = 'regular', is_active = false WHERE segment = 'vip'")
    op.drop_column('retention_settings', 'vip_min_visits')
    op.drop_column('retention_settings', 'vip_min_spend')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('retention_settings', sa.Column('vip_min_spend', sa.Numeric(precision=12, scale=2), nullable=False, server_default='5000'))
    op.add_column('retention_settings', sa.Column('vip_min_visits', sa.Integer(), nullable=False, server_default='5'))
    op.drop_table('restaurant_profile')
