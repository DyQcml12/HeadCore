# S1 Database V2 Control Plane Test Report

Date: 2026-07-14

## Scope

- Typed control-plane contracts and repository port.
- Database-backed actor authorization boundary.
- Minimum read-only FastAPI router contract.
- Domain error mapping and platform identifier redaction.

## Commands

```powershell
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m py_compile (Get-ChildItem app\database_control\*.py).FullName (Get-ChildItem tests\database_control\*.py).FullName
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests\database_control -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests\test_database_v2.py -q
& "D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe" -m pytest tests\test_api.py tests\test_project_surface_audit.py -q
```

## Results

- Compile check: PASS.
- S1 focused tests: `12 passed`.
- Existing Database V2 regression: `56 passed`.
- API and project-surface regression: `19 passed`.
- Write-control focused tests after integration: `25 passed`.
- Latest related Database V2/storage/API/project-surface regression: `94 passed`.
- Known warning: pytest could not write `.pytest_cache` because Windows denied access; test execution passed.

## Safety boundary

- No real database connection or migration was executed.
- No existing V2 repository, shared FastAPI entry point, runtime setting, frontend, or environment file was modified.
- Production router registration and the read-only MySQL adapter remain integration-owner tasks.

## Persona persistence transaction contract increment

- Added async `PersonaPersistenceStore` and transaction-semantic in-memory fake.
- Added concurrent version allocation, single-active release, publish/rollback idempotency,
  operation-id conflict, cross-profile rejection, and active-version binding tests.
- S1 focused suite: `31 passed in 0.96s`.
- S1/S5 combined contract suite: `55 passed in 1.17s`.
- Database V2/API/project-surface/S4 regression: `84 passed in 0.93s`.
- Compile check: PASS.
- Final full project regression: `543 passed in 13.22s`.

The first full run had one unrelated 10ms provider timeout test fail under suite load
(`542 passed, 1 failed`). The test passed in isolation and the complete rerun passed.
No provider code was changed.

No migration, existing V2 repository, or real database was modified. The schema gaps blocking
a production MySQL persona adapter are documented in `persona-persistence-contract.md`.

## 2026-07-15 Database Control hardening

- Compile: PASS.
- Database Control focused: `36 passed, 1 skipped`.
- Related Database V2/storage/API/project-surface regression: `96 passed`.
- Real isolated MySQL read contract: SKIP because `DATABASE_CONTROL_TEST_DATABASE` was not configured.
- Full suite: `556 passed, 1 skipped, 3 failed`.
- The three failures reproduce independently in existing QQ voice tests and are outside S1; no QQ code was changed.

### Async S5 consumer verification

- S5 now consumes `PersonaPersistenceStore` through a native async service.
- S1/S5 focused tests: `60 passed in 1.27s`.
- S1/S4/S5/Database V2 regression: `125 passed in 1.30s`.
- Final full project regression: `550 passed in 13.31s`.

### Persona write audit verification

- Added the redacted persona control audit contract and in-memory fake.
- S1/S4/S5/Database V2 regression: `145 passed, 1 skipped in 1.92s`.
- Final full project regression: `600 passed, 1 skipped in 13.74s`.
- The skipped test still requires an explicitly configured isolated MySQL test database.
