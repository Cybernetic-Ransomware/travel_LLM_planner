# ADR-04: testcontainers for integration test database isolation

## Context
Integration tests for storage functions and API endpoints require a real MongoDB instance. Using the production database risks data corruption and test interference. A dedicated always-on test database requires Docker infrastructure to be running and maintained separately. Unit tests should remain runnable without any external services.

## Decision
Use `testcontainers[mongo]` to spin up a `mongo:8.0` container scoped to the test session. The container is started once, shared across all integration tests, and stopped automatically after the session ends. Integration tests are marked `@pytest.mark.integration` and excluded from the default `pytest` run; they are only executed explicitly via `just test-integration` (requires Docker Desktop).

Schema synchronisation with production is guaranteed by reusing `MongoDBManager.connect()` inside the test fixture — the same index creation code runs against the testcontainer database.

The FastAPI lifespan is replaced in tests via `app.router.lifespan_context` so the app connects to the testcontainer database instead of the URI from settings.

## Rationale
### Evaluation of Alternatives
- **mongomock** — in-memory fake MongoDB. Poor async/Motor support; behavioural differences from real MongoDB cause false-positive tests.
- **Dedicated test database** — requires a running MongoDB instance; schema drift possible if `MongoDBManager` is not called during setup.
- **testcontainers (chosen)** — real `mongo:8.0`, identical to production image; session-scoped startup amortises container overhead; schema always matches production because `MongoDBManager` is reused.

### Technical Considerations
- `conftest.py` defines three fixtures:
  - `mongo_container` (session, sync) — starts the container.
  - `test_db` (session, async) — connects `MongoDBManager` to the container.
  - `client` (function, async) — HTTP client with the lifespan overridden to inject `test_db`.
- `asyncio_mode = "auto"` in `pyproject.toml` removes the need for `@pytest.mark.asyncio` on every test.
- Test results and coverage reports are written to `tests/result/` (gitignored).

### Integration with Existing Environment
- Docker Desktop must be running for `just test-integration`.
- `just test` (default) runs only `unit` and `regression` marked tests — no Docker required, fast feedback loop.
- `testcontainers[mongo]>=4.14.1` is in the `dev` dependency group.

### Future Potential
Additional containers (Redis, a second Mongo instance for migration tests) can be added as session-scoped fixtures without affecting the existing test structure.

## Consequences
### Positive Outcomes
- Integration tests run against a real MongoDB with the exact production schema.
- No persistent test state between CI runs — container is ephemeral.
- Unit tests remain fast and Docker-free.

### Challenges & Mitigation
- Container startup adds ~5–10 s to the integration test session. Mitigated by session scope (started once).
- Requires Docker Desktop on developer machines. Documented in README.

## Status
`Accepted` — project-wide. Effective from the `features/basic_ui` branch.
