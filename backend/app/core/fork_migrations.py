"""Translate the retired funding revision before Alembic walks the new graph.

The fork formerly used upstream-looking IDs 075–079 after upstream 074.
Those exact migrations are now f001–f005, in the same position. Upstream 075
follows f005. This bridge only relabels the fully applied old fork schema;
it never replays its workspace backfill or skips incoming upstream DDL.
"""

import sqlalchemy as sa
from sqlalchemy.engine import Connection


def normalize_legacy_funding_revision(connection: Connection) -> None:
    inspector = sa.inspect(connection)
    if not inspector.has_table("alembic_version"):
        return
    revisions = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
    if revisions != ["079"]:
        return
    # Upstream's own 079 already has institutions and invoices. It is not the
    # retired fork marker, even on a database containing funding tables.
    if inspector.has_table("institutions") and inspector.has_table("invoices"):
        return

    required = {
        "funding_domains": {"id", "user_id", "workspace_id"},
        "transactions": {"funding_domain_id"},
        "recurring_transactions": {"funding_domain_id"},
        "credit_card_payment_allocations": {"funding_domain_id", "statement_due_date"},
    }
    for table, columns in required.items():
        if not inspector.has_table(table) or not columns.issubset(
            column["name"] for column in inspector.get_columns(table)
        ):
            raise RuntimeError("Ambiguous revision 079: inspect the schema before migrating this fork")
    workspace = next(
        column for column in inspector.get_columns("funding_domains")
        if column["name"] == "workspace_id"
    )
    if workspace["nullable"] or inspector.has_table("institutions") or inspector.has_table("invoices"):
        raise RuntimeError("Partial revision 079: inspect the schema before migrating this fork")

    # Runs inside Alembic's DDL transaction: a failed upgrade rolls back this
    # marker along with the schema changes, leaving a retryable old database.
    connection.execute(sa.text("UPDATE alembic_version SET version_num = 'f005' WHERE version_num = '079'"))
