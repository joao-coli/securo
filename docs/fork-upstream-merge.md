# Fork: merging upstream and running Docker

This guide is for maintaining a long-lived feature branch (for example `feat/funding-domains`) that regularly merges [`securo-finance/securo`](https://github.com/securo-finance/securo) `main` while keeping fork-only migrations and features.

## Remotes (recommended)

```bash
git remote add upstream https://github.com/securo-finance/securo.git
git remote set-url --push upstream no_push   # optional: block accidental push
git fetch upstream main
```

- **`origin`** — your fork (`git@github.com:<you>/securo.git`)
- **`upstream`** — read-only source of truth for `main`

## Merge upstream into your branch

```bash
git checkout feat/your-branch
git fetch upstream main
git merge upstream/main
```

Resolve conflicts, then verify locally (see below) before pushing to `origin`.

Typical conflict areas after a large upstream pull:

- `backend/app/api/transactions.py`, `transaction_service.py`, schemas
- `frontend/src/pages/account-detail.tsx`, `rules.tsx`, `transaction-dialog.tsx`
- `backend/tests/conftest.py` (pgvector SQLite shim vs fork model imports)

Keep **both** upstream behaviour and fork features (for example funding domains + upstream ignore transactions / agents).

## Docker after an upstream merge

Upstream often adds Python and npm dependencies. Bind mounts sync **code**, not **installed packages** inside the image or cached `node_modules` volumes.

### 1. Rebuild images

```bash
docker compose build backend frontend
```

Required when `backend/pyproject.toml` gains packages (for example `pgvector`, `fastembed` for agents) or `frontend/package.json` gains deps (for example `react-markdown`, `remark-gfm`).

**Symptom if skipped (backend):**

```
ModuleNotFoundError: No module named 'pgvector'
```

during `alembic upgrade head` on container start.

**Symptom if skipped (frontend):**

```
react-markdown / remark-gfm … Are they installed?
```

### 2. Refresh the frontend `node_modules` volume

Compose mounts `./frontend` over `/app` but keeps dependencies in an anonymous volume at `/app/node_modules`. That volume can stay stale across merges.

```bash
docker compose up --build --renew-anon-volumes
```

Or recreate only the frontend service:

```bash
docker compose up -d --force-recreate --renew-anon-volumes frontend
```

### 3. Start the stack

```bash
docker compose up
```

Backend runs `alembic upgrade head` before uvicorn. Confirm in logs:

```
INFO:     Application startup complete.
```

## Database migrations on a fork

Upstream and a fork must not use the **same Alembic revision numbers** for different changes. After merging upstream, fork-only migrations should chain **after** upstream’s current head. Revision numbers collide easily:

| Upstream merge | Upstream took | Fork funding migrations moved to |
|----------------|---------------|----------------------------------|
| Workspaces     | `052`–`054`   | `055`–`058`                      |
| 0.13.x         | `055`–`061`   | `062`–`065`                      |
| 0.13.7         | `062`–`063`   | `066`–`069`                      |
| Latest upstream | `064`–`074`  | `075`–`078`, then `079`          |

Check the graph:

```bash
cd backend && uv run alembic heads    # should show a single head
```

### Fresh database

Normal startup is enough:

```bash
docker compose up --build
```

### Existing DB at the old fork head (`069`)

The old fork used `066`–`069` for funding features. The merged graph now uses
those IDs for upstream changes, so an old database whose `alembic_version` says
`069` must not upgrade from that marker: Alembic would skip upstream `064`–`069`.

After making and verifying a fresh database backup, stop writers and run this
once against that database:

```bash
docker compose run --rm backend sh -c "alembic stamp 063 && alembic upgrade head"
```

`stamp 063` changes only Alembic metadata. The subsequent upgrade applies
upstream `064`–`074`, then the idempotent fork migrations `075`–`078`, and the
lossless workspace-scope migration `079`. The migration preserves each domain
UUID where possible and clones/repoints it only when the old user-scoped domain
was shared by multiple workspaces.

Verify the result:

```bash
docker compose run --rm backend alembic current
docker compose exec db psql -U postgres -d securo \
  -c "SELECT COUNT(*) FROM transactions;" \
  -c "SELECT COUNT(*) FROM recurring_transactions;" \
  -c "SELECT COUNT(*) FROM credit_card_payment_allocations;" \
  -c "SELECT COUNT(*) FROM funding_domains WHERE workspace_id IS NULL;"
```

The last query must return `0`. Do not use this recovery path on a database
that never ran the old fork funding migrations; use `alembic upgrade head`
directly for a normal or fresh database.

### `alembic_version` at `058` but `workspaces` table missing (empty app after login)

Symptoms:

- Login succeeds but dashboards/accounts look empty.
- Postgres logs: `relation "workspaces" does not exist`.
- `alembic_version` is already `058`, yet `\dt workspaces` returns nothing.

Cause: fork funding migrations used revision numbers `052`–`055` before upstream’s workspace migrations claimed `052`–`054`. Alembic thought the DB was at head while workspace migrations were never applied.

Your data is usually still there — check:

```bash
docker compose exec db psql -U postgres -d securo \
  -c "SELECT COUNT(*) FROM transactions;" \
  -c "SELECT COUNT(*) FROM accounts;"
```

**Recovery** (run once):

```bash
docker compose run --rm backend sh -c "alembic stamp 051 && alembic upgrade head"
docker compose restart backend
```

This runs upstream `052`–`054` (creates workspaces, backfills `workspace_id` on all rows), then the later upstream and fork chain. Afterward verify:

```bash
docker compose exec db psql -U postgres -d securo \
  -c "SELECT version_num FROM alembic_version;" \
  -c "SELECT COUNT(*) FROM workspaces;" \
  -c "SELECT COUNT(*) FROM transactions WHERE workspace_id IS NOT NULL;"
```

Refresh the browser (or log out and back in).

### New fork-only migrations

When adding migrations after another upstream merge:

1. `git fetch upstream main && git merge upstream/main`
2. Find upstream head: `uv run alembic heads` (on merged tree)
3. Create the next revision with `down_revision` = that head (do not reuse upstream revision numbers)
4. Rebuild Docker images and renew frontend anonymous volumes if dependencies changed

## Quick checklist after each upstream merge

| Step | Command |
|------|---------|
| Merge | `git merge upstream/main` |
| Backend lint | `cd backend && uv run ruff check app tests` |
| Tests | `cd backend && uv run pytest` (or `docker compose exec backend pytest`) |
| Frontend build | `cd frontend && npm install && npm run build` |
| Rebuild Docker | `docker compose build backend frontend` |
| DB (collision case only) | `docker compose run --rm backend sh -c "alembic stamp 045 && alembic upgrade head"` |
| Run | `docker compose up --renew-anon-volumes` |

## Optional: agents profile

Agents need extra compose profile and env (see root [README](../README.md#ai-agents-optional)). Migrations for agent tables are in the main chain (`046`–`049` upstream); they run even when `AGENTS_ENABLED=false`, but the feature stays off at runtime unless configured.
