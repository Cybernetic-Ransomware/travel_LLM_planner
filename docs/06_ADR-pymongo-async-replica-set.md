# ADR-06: PyMongo native async client with single-node Replica Set

## Context
ADR-01 chose Motor as the async MongoDB driver. Since then, PyMongo 4.x introduced a native async API (`AsyncMongoClient`, `pymongo.asynchronous.*`) that mirrors Motor's interface but is maintained directly by MongoDB Inc. as part of the official driver — eliminating the need for a separate dependency.

Additionally, the project began implementing multi-document storage operations (`bulk_write` upserts, enrichment pipelines) and a `PATCH /places/{id}` endpoint that exhibited a TOCTOU race condition (read → check → write across two round-trips). Resolving these correctly requires either atomic single-document operations or, for future multi-collection workflows, ACID transactions — which MongoDB supports only on a Replica Set.

## Decision
1. Replace Motor (`motor`) with PyMongo's native async client (`pymongo>=4.16`).
2. Run MongoDB as a single-node Replica Set (`--replSet rs0`) in Docker Compose, enabling ACID transactions.
3. Expose `AsyncMongoClient` on `app.state.client` alongside `app.state.db`, and provide two reusable context managers — `mongo_session` and `mongo_transaction` — in `src/core/db/deps.py`.
4. Fix the `PATCH /places/{id}` TOCTOU by replacing the two-step `update_one` + `find_one` with an atomic `find_one_and_update(return_document=ReturnDocument.AFTER)`.

## Rationale
### Evaluation of Alternatives
- **Keep Motor** — Motor 3.x wraps PyMongo 4.x internally; it adds a dependency layer with no functional benefit now that PyMongo ships its own async API.
- **Beanie ODM** — rejected for the same reasons as ADR-01: too opinionated for the bulk/enrichment query patterns in use.
- **PyMongo async + RS (chosen)** — single official dependency, identical API surface to Motor, unlocks transactions without a third-party wrapper.

### Technical Considerations
- `AsyncMongoClient.close()` is now a coroutine; `MongoDBManager.disconnect()` correctly `await`s it.
- `app.state.client` is required because sessions are started from the client, not the database handle. `MongoDBManager` exposes a `.client` property with a runtime guard (`RuntimeError` if called before `connect()`).
- `mongo_session` provides causal consistency (a subsequent read always sees its own writes, even on a secondary). `mongo_transaction` wraps `session.start_transaction()` and rolls back automatically on exception.
- `bulk_write(ordered=False)` is intentionally kept outside transactions: partial success is acceptable for idempotent upserts (failed documents are re-imported on the next run). Wrapping in a transaction would turn any single conflict into a full rollback — the wrong behaviour for a scraping pipeline.
- Single-node RS in Docker is initialised via the `mongo` healthcheck itself: `rs.initiate()` is called if `rs.status()` raises, making the setup self-contained with no separate init container.

### Integration with Existing Environment
- `app.state.client` and `app.state.db` are both set in `lifespan.py`; `get_client` / `get_db` FastAPI dependencies expose them to route handlers.
- `mongo_transaction` requires a Replica Set. On a standalone `mongod` (local dev without Docker) it raises `OperationFailure`. Local dev should either use `docker compose up` or start `mongod --replSet rs0` manually.
- Tests using testcontainers (ADR-04) should configure the container image with `--replSet rs0` if they exercise transaction paths.

### Future Potential
- `mongo_transaction` is ready for multi-collection atomic workflows (e.g., user creation spanning `users` + `profiles` collections if auth is added).
- Change streams remain available via `AsyncMongoClient` if real-time UI updates are needed.

## Consequences
### Positive Outcomes
- One fewer dependency (`motor` removed); PyMongo async is the canonical path forward per MongoDB's own roadmap.
- TOCTOU in `PATCH /places/{id}` eliminated: `find_one_and_update` is a single server-side atomic operation.
- ACID transactions are available project-wide without further infrastructure changes.
- `mongo_session` / `mongo_transaction` context managers are generic enough to be used in background tasks and scripts, not just HTTP handlers.

### Challenges & Mitigation
- Single-node RS adds a small startup delay (~5 s) while the node elects itself PRIMARY; mitigated by `start_period: 10s` and `retries: 15` in the Docker healthcheck.
- `mongo_transaction` silently fails on standalone; mitigated by always using Docker Compose for integration work and documenting the requirement here.

## Status
`Accepted` — effective from branch `refactor/mongo_connector`. Supersedes [ADR-01](./01_ADR-motor-async-driver.md).