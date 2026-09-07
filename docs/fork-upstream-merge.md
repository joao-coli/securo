# Fork-update runbook

Use this guide for upstream updates and failures after an update. Keep `origin`
as our separate fork and upstream pushes disabled. Derive versions, service
names, and commands from the active deployment, Compose files, and CI workflow.

## 1. Inspect and back up first

Identify the active branch, local/unpushed work, upstream baseline, running
images, database revision, and actual storage mounts. Preserve configuration
and untracked files; keep secrets out of tool output.

Before changing code or schema, back up PostgreSQL and roles, persistent files,
secrets/configuration, Git history, and any queue/scheduler state needed for
recovery. Pause writers when needed for database/file consistency. Keep backups
private and git-ignored, verify checksums, and restore-test in a separate database.
Retain the backup location and matching rollback commit/image references.

## 2. Merge in isolation

Fetch and pin the intended upstream release or branch. Merge into a separate
checkout of the fork: the live dev stack bind-mounts source and reloads edits.
Isolate test containers, databases, volumes, ports, and credentials too; a new
directory alone does not isolate Compose.

Preserve both upstream intent and fork behavior. Inspect automatic merges as
well as conflicts, particularly schemas, payload builders, generation, rules,
and sync/import. Build our fork's images; upstream images omit our changes.

## 3. Rehearse migrations

Compare the installed schema with the merged graph. Old fork versions reused
numeric IDs later claimed by upstream, so a revision label alone is insufficient.
Never apply a copied `alembic stamp` command without proving the schema matches.
Legacy compatibility lives in `backend/app/core/fork_migrations.py` and
`backend/alembic/env.py`.

Use distinct `fNNN` IDs for fork migrations; preserve applied IDs and their
position instead of repeatedly moving/replaying funding backfills. Connect new
migrations deliberately. Run `python backend/scripts/check_migration_chain.py`;
the repository currently requires one chain and head.

Test both a restored backup and an empty database. Verify inspection stays
read-only, failures are recoverable, and original rows, relationships, amounts,
ownership, and file references survive. For intended data transformations,
verify lossless mappings; row counts alone are insufficient.

## 4. Validate behavior

Install locked dependencies with the supported runtimes. Run the lint, type,
test, and build checks in the current CI workflow/package scripts. Run Python
checks from `backend/` to use its environment.

Check funding domains through the real form payload and persisted API result:
ordinary creation, every installment, recurring generation and matching,
sync/import, rules/previews, statement allocations, and workspace isolation.
Preserve manual choices and add regression tests for any newly bypassed path.

## 5. Deploy and verify

Prepare the tested images and rollback references. Stop all writers, including
workers/schedulers; take and verify a fresh backup and recheck data-sensitive
migration assumptions. Advance the live fork to the tested merge while retaining
local configuration/work. Apply the rehearsed migration and verify data before
resuming writers.

Recreate all consumers of changed backend dependencies, including enabled
optional services. Refresh only the frontend dependency volume as needed;
retain database and uploaded-file volumes. Verify actual mounts/images, startup
logs, frontend-proxied API health, authenticated workspaces, and affected flows.
On failure, stop writers and recover with matching data, code, and images;
rolling back only an image cannot undo schema changes.

## 6. Finish and maintain

Commit the merge/fixes; push only to our fork when within scope and authenticated.
Report unpushed work. Remove temporary test services and sensitive scratch data,
keeping verified backups and rollback references. Never restore-test on the live
database or remove its volumes.

After each update, revise this guide if upstream changes deployment, storage,
dependencies, migrations, or required checks. Keep it general: discover current
versions/IDs and keep one-time compatibility details in code or targeted docs,
rather than accumulating past-run instructions here.
