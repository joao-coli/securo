"""recurring transaction funding domain

Revision ID: 077
Revises: 076
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "077"
down_revision: Union[str, None] = "076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("recurring_transactions")}
    if "funding_domain_id" in cols:
        return
    op.add_column(
        "recurring_transactions",
        sa.Column("funding_domain_id", UUID(as_uuid=True), sa.ForeignKey("funding_domains.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recurring_transactions", "funding_domain_id")
