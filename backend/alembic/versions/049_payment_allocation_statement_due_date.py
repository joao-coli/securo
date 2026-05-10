"""payment allocation statement due date

Revision ID: 049
Revises: 048
Create Date: 2026-05-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credit_card_payment_allocations",
        sa.Column("statement_due_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_cc_payment_allocations_account_due_created",
        "credit_card_payment_allocations",
        ["user_id", "credit_card_account_id", "statement_due_date", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cc_payment_allocations_account_due_created",
        table_name="credit_card_payment_allocations",
    )
    op.drop_column("credit_card_payment_allocations", "statement_due_date")
