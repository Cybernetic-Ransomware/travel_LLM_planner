# ADR-01: Motor async driver with FastAPI lifespan connection pooling

## Context
The project uses FastAPI, which is built on an async event loop. The initial implementation used PyMongo — a synchronous driver — for MongoDB access. Synchronous I/O in an async context blocks the event loop, eliminating the concurrency benefits of FastAPI and causing latency under load. Each request was also creating a new client instance instead of reusing a connection pool.

## Decision
Replace PyMongo with Motor (the official async MongoDB driver) and manage the client lifecycle through a FastAPI lifespan context manager that initialises the pool once on startup and tears it down on shutdown.

## Rationale
### Evaluation of Alternatives
- **PyMongo with `run_in_executor`** — wraps sync calls in a thread pool. Works but adds overhead and obscures the async model.
- **Beanie ODM** — async ODM built on Motor. Rejected as too opinionated; the project needs direct query control for bulk upserts and enrichment pipelines.
- **Motor + lifespan (chosen)** — native async, idiomatic FastAPI pattern, zero thread-pool overhead.

### Technical Considerations
- Motor exposes the same API surface as PyMongo but returns coroutines instead of blocking.
- `maxPoolSize` is configured via `Settings.mongo_pool_size` (default 10) to allow tuning per environment.
- Indexes are created once inside `MongoDBManager.connect()`, ensuring schema parity between environments.

### Integration with Existing Environment
- All storage functions became `async def` and must be awaited by callers.
- `app.state.db` is the single shared `AsyncIOMotorDatabase` instance, injected via `Depends(get_db)` (`MongoDbDep`).
- Tests override the lifespan to inject a testcontainer database without touching settings (see ADR-04).

### Future Potential
Motor supports change streams and async transactions — both relevant if real-time UI updates or multi-document atomicity are needed later.

## Consequences
### Positive Outcomes
- Non-blocking DB access; event loop stays free for concurrent requests.
- Single connection pool shared across the application lifetime.
- Index creation is guaranteed on every startup, keeping schema in sync with code.

### Challenges & Mitigation
- All storage functions must be `async`; forgetting `await` causes silent type errors. Mitigated by `ty` type checking in CI.
- Motor does not support every PyMongo feature (e.g., `gridfs` has a separate async wrapper). Not currently needed.

## Status
`Accepted` — project-wide. Effective from the `features/basic_ui` branch.
