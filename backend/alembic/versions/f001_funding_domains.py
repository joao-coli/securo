"""funding domains

Revision ID: f001
Revises: 074
Create Date: 2026-05-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f001"
down_revision: Union[str, None] = "074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return _insp().has_table(name)


def _column_exists(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def _index_exists(table: str, index: str) -> bool:
    return any(i["name"] == index for i in _insp().get_indexes(table))


def upgrade() -> None:
    if not _table_exists("funding_domains"):
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
    if not _index_exists("funding_domains", "ix_funding_domains_user_active"):
        op.create_index(
            "ix_funding_domains_user_active",
            "funding_domains",
            ["user_id", "is_active"],
        )
    if not _column_exists("transactions", "funding_domain_id"):
        op.add_column(
            "transactions",
            sa.Column(
                "funding_domain_id",
                UUID(as_uuid=True),
                sa.ForeignKey("funding_domains.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _index_exists("transactions", "ix_transactions_funding_domain_id"):
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
