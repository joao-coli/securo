"""recurring transaction funding domain

Revision ID: 048
Revises: 047
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_transactions",
        sa.Column("funding_domain_id", UUID(as_uuid=True), sa.ForeignKey("funding_domains.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recurring_transactions", "funding_domain_id")
