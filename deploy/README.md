# Deployment Staging Baseline

The staging Compose file keeps `core` on its current storage path by default.
Do not switch `STORAGE_BACKEND` to `mysql` until HTTP and desktop identities
use the Database V2 repository; the legacy MySQL schema and Database V2 schema
are not interchangeable.

Database V2 migrations are explicit and do not start with the application:

```powershell
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml --profile database-v2 run --rm migrate-v2
```

The migration command only targets `MYSQL_DATABASE=hutao_chat_core`. Apply it
to an isolated database first, then run the Database V2 readiness check before
enabling `DATABASE_V2_ENABLED`. Do not place database passwords or API keys in
this document.

Semantic memory is a separate profile. It needs an already-migrated V2 database,
an existing local embedding model directory, and `SEMANTIC_MEMORY_ENABLED=true`
in `deploy/.env.staging`. Its Qdrant container is internal only; do not publish
port 6333 to the public network.

```powershell
docker compose --env-file deploy/.env.staging -f deploy/compose.staging.yml --profile semantic-memory up -d qdrant semantic-memory-worker
```

See `docs/deployment/LOCAL_MODEL_LAYOUT.md` before enabling this profile. The
worker will create or validate the collection and synchronize only derived
vectors through the MySQL outbox.
