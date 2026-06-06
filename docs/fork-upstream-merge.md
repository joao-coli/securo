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

Upstream and a fork must not use the **same Alembic revision numbers** for different changes. After merging upstream, fork-only migrations should chain **after** upstream’s current head. Revision numbers collide easily — upstream added `052`–`054` (workspaces) after our fork had already used `052`–`055` (funding domains). Funding migrations now live at **`055`–`058`** (after upstream `054`).

Check the graph:

```bash
cd backend && uv run alembic heads    # should show a single head
```

### Fresh database

Normal startup is enough:

```bash
docker compose up --build
```

### Existing dev DB (funding tables already applied under old revision ids)

If you previously ran fork migrations numbered `046`–`049` **before** renumbering, `alembic_version` may still say `049` while:

- funding-domain tables already exist, and
- upstream agent migrations (`046`–`049` agents) and `050`/`051` never ran.

**Recovery** (run once per affected database):

```bash
docker compose run --rm backend sh -c "alembic stamp 045 && alembic upgrade head"
```

What this does:

1. **`stamp 045`** — tells Alembic to treat the DB as at revision `045` (last shared revision before the collision).
2. **`upgrade head`** — applies any missing upstream revisions, then fork `055`–`058` (funding domains). Fork funding migrations are **idempotent**: they skip tables/columns/indexes that already exist.

If upstream added workspace migrations (`052`–`054`) since your last merge, a normal `alembic upgrade head` is usually enough — funding migrations were renumbered to follow `054`.

Confirm:

```bash
docker compose run --rm backend alembic current
# 058 (head)
```

**Do not** use `stamp 045` on a database that never had fork funding migrations — use `alembic upgrade head` only.

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
