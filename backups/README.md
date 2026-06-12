# Database backups

Local PostgreSQL dumps for the Securo dev stack. **Not committed to git** (see `.gitignore`).

## Create a backup

```bash
docker compose exec -T db pg_dump -U postgres -d securo --no-owner --no-acl \
  | gzip > backups/securo-$(date +%Y%m%d-%H%M%S).sql.gz
```

## Restore (destructive — overwrites current DB)

```bash
# Stop backend so nothing writes during restore
docker compose stop backend celery-worker celery-beat

gunzip -c backups/securo-YYYYMMDD-HHMMSS.sql.gz \
  | docker compose exec -T db psql -U postgres -d securo

docker compose start backend celery-worker celery-beat
```

To restore into a completely empty database, drop and recreate first:

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE securo;"
docker compose exec db psql -U postgres -c "CREATE DATABASE securo;"
# then run the gunzip | psql restore above
```
