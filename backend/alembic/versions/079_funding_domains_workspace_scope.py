"""scope funding domains to workspaces without losing existing references

Revision ID: 079
Revises: 078
Create Date: 2026-08-25
"""

from collections import Counter
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "079"
down_revision: Union[str, None] = "078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_FK = "fk_funding_domains_workspace_id_workspaces"
_WORKSPACE_INDEX = "ix_funding_domains_workspace_id"
_WORKSPACE_ACTIVE_INDEX = "ix_funding_domains_workspace_active"


def _workspace_ids_for_user(bind, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = bind.execute(
        sa.text(
            """
            SELECT w.id
            FROM workspaces AS w
            WHERE w.is_archived IS FALSE
              AND (
                    EXISTS (
                        SELECT 1
                        FROM workspace_members AS wm
                        WHERE wm.workspace_id = w.id
                          AND wm.user_id = :user_id
                    )
                    OR w.created_by_user_id = :user_id
                    OR w.managed_by_user_id = :user_id
              )
            """
        ),
        {"user_id": user_id},
    )
    return {row[0] for row in rows}


def _referenced_workspace_counts(bind, domain_id: uuid.UUID) -> Counter[uuid.UUID]:
    rows = bind.execute(
        sa.text(
            """
            SELECT workspace_id
            FROM transactions
            WHERE funding_domain_id = :domain_id
            UNION ALL
            SELECT workspace_id
            FROM recurring_transactions
            WHERE funding_domain_id = :domain_id
            UNION ALL
            SELECT t.workspace_id
            FROM credit_card_payment_allocations AS a
            JOIN transactions AS t ON t.id = a.payment_transaction_id
            WHERE a.funding_domain_id = :domain_id
            """
        ),
        {"domain_id": domain_id},
    )
    return Counter(row[0] for row in rows if row[0] is not None)


def _copy_domain(bind, source: dict, workspace_id: uuid.UUID) -> uuid.UUID:
    new_id = uuid.uuid4()
    bind.execute(
        sa.text(
            """
            INSERT INTO funding_domains
                (id, user_id, workspace_id, name, icon, color, description,
                 is_active, created_at)
            VALUES
                (:id, :user_id, :workspace_id, :name, :icon, :color,
                 :description, :is_active, :created_at)
            """
        ),
        {
            "id": new_id,
            "user_id": source["user_id"],
            "workspace_id": workspace_id,
            "name": source["name"],
            "icon": source["icon"],
            "color": source["color"],
            "description": source["description"],
            "is_active": source["is_active"],
            "created_at": source["created_at"],
        },
    )
    return new_id


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    domain_columns = {column["name"] for column in inspector.get_columns("funding_domains")}
    if "workspace_id" not in domain_columns:
        op.add_column(
            "funding_domains",
            sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
        )

    domains = bind.execute(
        sa.text(
            """
            SELECT id, user_id, name, icon, color, description, is_active,
                   created_at, workspace_id
            FROM funding_domains
            ORDER BY id
            """
        )
    ).mappings().all()

    for domain in domains:
        domain_id = domain["id"]
        referenced = _referenced_workspace_counts(bind, domain_id)
        workspace_ids = set(referenced)
        workspace_ids.update(_workspace_ids_for_user(bind, domain["user_id"]))

        existing_workspace_id = domain["workspace_id"]
        if existing_workspace_id is not None:
            workspace_ids.add(existing_workspace_id)

        if not workspace_ids:
            raise RuntimeError(
                f"Cannot assign funding domain {domain_id} to a workspace: "
                f"its owner has no accessible workspace and it has no references"
            )

        # Keep the original UUID in the workspace with the most historical
        # references. Ties are deterministic, which makes dry-run and recovery
        # results reproducible. Unreferenced domains keep it in the first
        # workspace returned by the stable UUID ordering.
        primary_workspace_id = min(
            workspace_ids,
            key=lambda workspace_id: (-referenced.get(workspace_id, 0), str(workspace_id)),
        )
        bind.execute(
            sa.text(
                "UPDATE funding_domains "
                "SET workspace_id = :workspace_id "
                "WHERE id = :domain_id"
            ),
            {"workspace_id": primary_workspace_id, "domain_id": domain_id},
        )

        for workspace_id in sorted(workspace_ids - {primary_workspace_id}, key=str):
            copied_id = _copy_domain(bind, domain, workspace_id)
            bind.execute(
                sa.text(
                    """
                    UPDATE transactions
                    SET funding_domain_id = :copied_id
                    WHERE funding_domain_id = :source_id
                      AND workspace_id = :workspace_id
                    """
                ),
                {
                    "copied_id": copied_id,
                    "source_id": domain_id,
                    "workspace_id": workspace_id,
                },
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE recurring_transactions
                    SET funding_domain_id = :copied_id
                    WHERE funding_domain_id = :source_id
                      AND workspace_id = :workspace_id
                    """
                ),
                {
                    "copied_id": copied_id,
                    "source_id": domain_id,
                    "workspace_id": workspace_id,
                },
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE credit_card_payment_allocations AS a
                    SET funding_domain_id = :copied_id
                    FROM transactions AS t
                    WHERE a.funding_domain_id = :source_id
                      AND t.id = a.payment_transaction_id
                      AND t.workspace_id = :workspace_id
                    """
                ),
                {
                    "copied_id": copied_id,
                    "source_id": domain_id,
                    "workspace_id": workspace_id,
                },
            )

    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys("funding_domains")
    if not any(
        set(foreign_key.get("constrained_columns") or []) == {"workspace_id"}
        and foreign_key.get("referred_table") == "workspaces"
        for foreign_key in foreign_keys
    ):
        op.create_foreign_key(
            _WORKSPACE_FK,
            "funding_domains",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("funding_domains")}
    if _WORKSPACE_INDEX not in indexes:
        op.create_index(_WORKSPACE_INDEX, "funding_domains", ["workspace_id"])
    if _WORKSPACE_ACTIVE_INDEX not in indexes:
        op.create_index(
            _WORKSPACE_ACTIVE_INDEX,
            "funding_domains",
            ["workspace_id", "is_active"],
        )

    op.alter_column(
        "funding_domains",
        "workspace_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_index(_WORKSPACE_ACTIVE_INDEX, table_name="funding_domains")
    op.drop_index(_WORKSPACE_INDEX, table_name="funding_domains")
    op.drop_constraint(_WORKSPACE_FK, "funding_domains", type_="foreignkey")
    op.alter_column(
        "funding_domains",
        "workspace_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )
    op.drop_column("funding_domains", "workspace_id")
