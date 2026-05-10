"""funding domains

Revision ID: 046
Revises: 045
Create Date: 2026-05-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "funding_domains",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_funding_domains_user_active",
        "funding_domains",
        ["user_id", "is_active"],
    )
    op.add_column(
        "transactions",
        sa.Column(
            "funding_domain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("funding_domains.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_transactions_funding_domain_id",
        "transactions",
        ["funding_domain_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_funding_domain_id", table_name="transactions")
    op.drop_column("transactions", "funding_domain_id")
    op.drop_index("ix_funding_domains_user_active", table_name="funding_domains")
    op.drop_table("funding_domains")
