"""customer marketing opt-out

Revision ID: a1c3e5f7b9d2
Revises: 06814ee5a29f
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = '06814ee5a29f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('customers', sa.Column('marketing_opt_out', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('customers', sa.Column('opted_out_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('customers', sa.Column('opt_out_source', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('customers', 'opt_out_source')
    op.drop_column('customers', 'opted_out_at')
    op.drop_column('customers', 'marketing_opt_out')
