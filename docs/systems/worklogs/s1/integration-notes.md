# S1 Database V2 Control Plane Integration Notes

## Delivered boundary

- Typed contracts, actor authorization, domain errors, application service, and an independent FastAPI router live under `app/database_control/`.
- The minimum read-only API contains `GET /status`, `GET /admin`, `GET /profiles`, and `GET /profiles/{profile_id}`.
- Every endpoint resolves the actor through `DatabaseControlRepository.resolve_actor`; request roles are never trusted.
- Profile account identifiers are redacted before HTTP serialization.
- The write subset now includes local bootstrap, profile relationship changes,
  account binding, and claim approval/rejection.
- Normal writes enforce mutation permission and Database V2 readiness before
  calling repository write methods.
- Accepted and rejected normal writes produce redacted control audit events.

## Integration completed

`MySQLDatabaseControlAdapter` now implements `DatabaseControlRepository` using
public methods on `MySQLDatabaseV2Repository`. The router never calls
`_fetchone`, `_fetchall`, or other private SQL helpers.

The integration owner registered the constructed router in `app/main.py`:

```python
app.include_router(create_database_control_router(database_control_service))
```

The production adapter implements:

- database readiness/status projection;
- read-only actor lookup without creating a profile or account;
- singleton admin lookup;
- cursor-paginated profile list;
- aggregate profile detail lookup.

Control authentication uses `find_relationship_context`, which performs no
create, update, last-seen touch, or audit write. The mutating
`resolve_relationship_context` method is not used by control authentication.

## Shared-file integration

- Router registration is present in `app/main.py`.
- Delivery is recorded in `README.md` and `AGENTS.md`.
- Keep Database V2 disabled until real readiness and owner bootstrap checks pass.

## Out of scope

- No existing V2 repository, migration, runtime configuration, frontend, or real database was changed.
- Admin transfer, account editing, labels, portraits, memories, and frontend
  controls remain later phases.

## Persona management persistence extension

S1 now exports `PersonaPersistenceStore` and an in-memory transaction-semantic fake for S5.
The contract covers draft/validation/version storage, atomic publish/rollback, idempotency keys,
release audit, and version-specific bindings. Focused S1 tests pass with `31 passed`.

The current V2 schema cannot implement this contract because it lacks draft, validation, release,
operation-id, and version-specific binding storage. See `persona-persistence-contract.md`. No migration,
existing V2 repository, or real database was changed.
