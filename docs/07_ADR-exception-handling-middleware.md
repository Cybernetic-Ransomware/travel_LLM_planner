# ADR-07: Hybrid exception handling — exception handlers + catch-all middleware

## Context
The FastAPI application had no standardised error response format. Each endpoint returned errors in different shapes, custom exception classes were inconsistently coded (`EndpointUnexpectedException` carried status code 404 instead of 500), and unhandled exceptions produced FastAPI's default 500 response with no logging.

A consistent `ErrorResponse` shape and centralised logging of unexpected errors were required before adding further endpoints.

## Decision
Adopt a hybrid approach: `@app.exception_handler` decorators handle `HTTPException` subclasses and `RequestValidationError`; `ExceptionHandlerMiddleware(BaseHTTPMiddleware)` acts as a catch-all for any exception that escapes the handler layer. All error responses share the `ErrorResponse` model: `{ status_code, error, detail }`.

## Rationale
### Evaluation of Alternatives
- **Exception handlers only** — `@app.exception_handler` cannot catch arbitrary unhandled exceptions (e.g. `RuntimeError` raised outside an endpoint). Unhandled errors would still return FastAPI's default 500 without logging.
- **Middleware only** — `BaseHTTPMiddleware.dispatch()` wraps `call_next()`, but FastAPI converts `HTTPException` into an HTTP response *before* `call_next` returns. The middleware therefore never sees `HTTPException` as a Python exception; it only receives the already-formed response. Custom status codes and details would need to be re-parsed from the response, which is fragile.
- **Hybrid (chosen)** — exception handlers intercept `HTTPException` (including custom subclasses) and `RequestValidationError` at the FastAPI layer and format them into `ErrorResponse`. The middleware catches anything that is not an `HTTPException` and reaches the ASGI layer, logs the full traceback, and returns a safe generic 500.

### Technical Considerations
- `StarletteHTTPException` is used instead of `fastapi.HTTPException` in the handler registration so that all subclasses — current and future — are caught by a single handler.
- `ExceptionHandlerMiddleware` catches `Exception`, not `BaseException`, so `KeyboardInterrupt` and `SystemExit` propagate normally and allow graceful shutdown.
- `HTTPStatus(exc.status_code).phrase` resolves the human-readable error name automatically (e.g. `"Not Found"`, `"Not Implemented"`), avoiding a hardcoded lookup table.
- Handler registration is extracted into `register_exception_handlers(app: FastAPI)` in `src/core/middleware.py`, keeping `main.py` as a pure compositor (see architectural convention).

### Integration with Existing Environment
- `main.py` order: `add_middleware` → `register_exception_handlers` → `include_router`. This ordering ensures middleware wraps the entire application before routes are declared.
- Existing integration tests (`tests/gmaps/test_router.py`) implicitly exercise the handlers on every 404 and 422 response.
- Dedicated unit tests in `tests/core/` cover `ErrorResponse`, both custom exception classes, all handler branches, middleware catch-all, and traceback logging — without requiring MongoDB or Docker.

### Future Potential
Additional exception types (e.g. authentication errors, rate-limit errors) can be registered by adding handlers inside `register_exception_handlers` without touching `main.py`. The `ErrorResponse` model can be extended with optional fields (e.g. `request_id`) in a backwards-compatible way.

## Consequences
### Positive Outcomes
- All error responses share a single JSON shape, making client-side error handling predictable.
- Unhandled exceptions are logged with full traceback to `middleware.log` without leaking stack traces to clients.
- The fix to `EndpointUnexpectedException` (404 → 500) is now covered by a regression test.

### Challenges & Mitigation
- `BaseHTTPMiddleware` has a known interaction with streaming responses — it buffers the response body. Not relevant for this JSON API, but worth noting if streaming endpoints are added later.
- The type checker (`ty`) reports a false positive on `add_middleware(ExceptionHandlerMiddleware)` due to Starlette's `_MiddlewareFactory` parameterisation. Suppressed with `# type: ignore[arg-type]`.

## Status
`Accepted` — project-wide. Effective from the `feature/exceptions_middleware` branch.
