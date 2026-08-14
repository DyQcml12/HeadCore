# PostgreSQL Web Runtime

The Web product uses PostgreSQL for accounts, sessions, chat records, memory records, and relationship records. Qdrant is not a replacement for PostgreSQL: it is reserved for semantic retrieval after a memory record has been accepted by the relational lifecycle.

## Prepare the database

Create a dedicated local PostgreSQL database and a non-superuser application account with access only to that database. Do this in pgAdmin or with an administrator-approved database workflow; do not place the administrator password in the project.

Set these values in the local `.env` file only:

```dotenv
STORAGE_BACKEND=postgresql
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DATABASE=hutao_chat_core
POSTGRES_USER=hutao_app
POSTGRES_PASSWORD=<local-application-password>
DATABASE_V2_ENABLED=false
PUBLIC_WEB_AUTH_ENABLED=false
```

Use a distinct application password. Do not reuse model-provider, email, or operating-system credentials.

## Apply migrations

Preview the migration set without connecting:

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\apply_postgres_web_migrations.py --dry-run
```

Apply it after the connection settings are present:

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\apply_postgres_web_migrations.py
```

The migration is repeatable. Applied versions are stored in `schema_migrations`; it never creates a database or prints a password.

## Enable account flows

After migrations pass, set `PUBLIC_WEB_AUTH_ENABLED=true` and restart FastAPI. Login becomes available. Registration and password reset remain unavailable until a verified SMTP sender is configured and `EMAIL_DELIVERY_ENABLED=true`; this prevents the UI from claiming an email flow that cannot deliver a verification message.

## Verification

Run the focused PostgreSQL contract checks and the complete application suite:

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests\test_postgres_storage.py -q -p no:cacheprovider
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests -q -p no:cacheprovider
```
