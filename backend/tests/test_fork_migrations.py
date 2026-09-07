"""The retired fork marker must not skip upstream's new migrations."""

import pytest
import sqlalchemy as sa

from app.core.fork_migrations import normalize_legacy_funding_revision


@pytest.fixture
def engine():
    engine = sa.create_engine("sqlite://")
    yield engine
    engine.dispose()


def seed_legacy(connection):
    for sql in (
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)",
        "INSERT INTO alembic_version VALUES ('079')",
        "CREATE TABLE funding_domains (id TEXT, user_id TEXT, workspace_id TEXT NOT NULL)",
        "INSERT INTO funding_domains VALUES ('domain', 'user', 'workspace')",
        "CREATE TABLE transactions (funding_domain_id TEXT)",
        "INSERT INTO transactions VALUES ('domain')",
        "CREATE TABLE recurring_transactions (funding_domain_id TEXT)",
        "CREATE TABLE credit_card_payment_allocations (funding_domain_id TEXT, statement_due_date DATE)",
    ):
        connection.execute(sa.text(sql))


def version(connection):
    return connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()


def test_fresh_database_needs_no_bridge(engine):
    with engine.begin() as connection:
        normalize_legacy_funding_revision(connection)
        assert not sa.inspect(connection).has_table("alembic_version")


def test_legacy_schema_is_relabelled_without_replaying_funding_backfill(engine):
    with engine.begin() as connection:
        seed_legacy(connection)
        normalize_legacy_funding_revision(connection)
        assert version(connection) == "f005"
        assert connection.execute(sa.text("SELECT * FROM funding_domains")).all() == [
            ("domain", "user", "workspace")
        ]
        assert connection.execute(sa.text("SELECT * FROM transactions")).all() == [("domain",)]
        normalize_legacy_funding_revision(connection)
        assert version(connection) == "f005"


def test_upstream_079_is_not_relabelled(engine):
    with engine.begin() as connection:
        seed_legacy(connection)
        connection.execute(sa.text("CREATE TABLE institutions (id TEXT)"))
        connection.execute(sa.text("CREATE TABLE invoices (id TEXT)"))
        normalize_legacy_funding_revision(connection)
        assert version(connection) == "079"


@pytest.mark.parametrize("change", [
    "DROP TABLE credit_card_payment_allocations",
    "CREATE TABLE institutions (id TEXT)",
    "ALTER TABLE funding_domains RENAME COLUMN workspace_id TO obsolete_workspace_id",
])
def test_incomplete_or_mixed_schema_is_refused(engine, change):
    with engine.begin() as connection:
        seed_legacy(connection)
        connection.execute(sa.text(change))
        with pytest.raises(RuntimeError, match="inspect the schema"):
            normalize_legacy_funding_revision(connection)
        assert version(connection) == "079"


def test_failed_upgrade_rolls_back_the_marker(engine):
    with engine.begin() as connection:
        seed_legacy(connection)
    with pytest.raises(RuntimeError, match="migration failed"):
        with engine.begin() as connection:
            normalize_legacy_funding_revision(connection)
            assert version(connection) == "f005"
            raise RuntimeError("migration failed")
    with engine.connect() as connection:
        assert version(connection) == "079"
