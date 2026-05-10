"""credit-card payment allocations

Revision ID: 047
Revises: 046
Create Date: 2026-05-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_card_payment_allocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "payment_transaction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "credit_card_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bill_id",
            UUID(as_uuid=True),
            sa.ForeignKey("credit_card_bills.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "funding_domain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("funding_domains.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_cc_payment_allocations_payment_transaction_id",
        "credit_card_payment_allocations",
        ["payment_transaction_id"],
    )
    op.create_index(
        "ix_cc_payment_allocations_credit_card_account_id",
        "credit_card_payment_allocations",
        ["credit_card_account_id"],
    )
    op.create_index(
        "ix_cc_payment_allocations_bill_id",
        "credit_card_payment_allocations",
        ["bill_id"],
    )
    op.create_index(
        "ix_cc_payment_allocations_funding_domain_id",
        "credit_card_payment_allocations",
        ["funding_domain_id"],
    )
    op.create_index(
        "ix_cc_payment_allocations_account_created",
        "credit_card_payment_allocations",
        ["user_id", "credit_card_account_id", "created_at"],
    )
    op.create_index(
        "ix_cc_payment_allocations_account_bill_created",
        "credit_card_payment_allocations",
        ["user_id", "credit_card_account_id", "bill_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cc_payment_allocations_account_bill_created", table_name="credit_card_payment_allocations")
    op.drop_index("ix_cc_payment_allocations_account_created", table_name="credit_card_payment_allocations")
    op.drop_index("ix_cc_payment_allocations_funding_domain_id", table_name="credit_card_payment_allocations")
    op.drop_index("ix_cc_payment_allocations_bill_id", table_name="credit_card_payment_allocations")
    op.drop_index("ix_cc_payment_allocations_credit_card_account_id", table_name="credit_card_payment_allocations")
    op.drop_index("ix_cc_payment_allocations_payment_transaction_id", table_name="credit_card_payment_allocations")
    op.drop_table("credit_card_payment_allocations")
