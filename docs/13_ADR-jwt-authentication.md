# ADR-13: JWT RS256 authentication for protected endpoints

## Context
`POST /chat` (orchestrator) was publicly accessible — any caller could drive the LLM and incur
API costs without limit.  The same was true for all place-write endpoints (`POST /import`,
`POST /enrich`, `PATCH /places/{id}`, `DELETE /places/{id}`).  The auth plan was sketched in
`docs/ROADMAP.md` roadmap item A1.

The application uses Auth0 as the identity provider.  Auth0 issues RS256 JWTs whose public keys
are published at `https://{domain}/.well-known/jwks.json`.

## Decision
Add RS256 JWT verification to FastAPI using **`authlib`**.  A `get_current_user` FastAPI
dependency fetches and caches the Auth0 JWKS, verifies the Bearer token on each request, and
maps the claims to a `CurrentUser` Pydantic model.  Protection is gated by an `AUTH_ENABLED`
flag so that local development and CI can run without an Auth0 tenant.

## Rationale
### Evaluation of Alternatives
- **`authlib`** (chosen) — actively maintained, native JWKS support (`JsonWebKey.import_key_set`),
  clean `jwt.decode` API with `claims_options` for audience/issuer/expiry, widely adopted.
- **`PyJWT`** — also actively maintained; `PyJWKClient` handles JWKS fetching.  Would work, but
  `authlib` has richer first-class JOSE support matching the Auth0 recommended path.
- **`python-jose`** — has seen reduced maintenance activity.  Rejected in favour of `authlib`.

### Technical Considerations
- JWKS are fetched by `httpx.AsyncClient` (already in the project dependency tree) and cached
  in a module-level `_JwksCache` with a 1-hour TTL.
- On JWT verification failure (possible key rotation), the cache is refreshed once and
  verification is retried before returning HTTP 401.
- The dependency `get_current_user` is type-aliased as `CurrentUserDep = Annotated[CurrentUser,
  Depends(get_current_user)]` — same convention as `MongoDbDep` and `OrchestratorDep`.
- `AuthenticationError(HTTPException, status_code=401)` is handled by the existing
  `StarletteHTTPException` handler registered in `src/core/middleware.py` (ADR-07) — no new
  handler required.

### Integration with Existing Environment
| Endpoint | Protected | Notes |
|---|---|---|
| `POST /chat` | ✅ | LLM cost driver — highest priority |
| `POST /import` | ✅ | triggers Playwright scrape |
| `POST /enrich` | ✅ | calls Google Places API |
| `PATCH /places/{id}` | ✅ | write operation |
| `DELETE /places/{id}` | ✅ | write operation |
| `GET /places`, `GET /places/{id}` | public | read-only |
| `GET /keycheck`, `GET /orchestrator/status` | public | diagnostics |
| `GET /` (health) | public | health check |

**Graceful degradation**: when `AUTH_ENABLED=False` (default) or `AUTH0_DOMAIN`/`AUTH0_AUDIENCE`
are blank, `settings.auth_active` returns `False` and `get_current_user` returns
`CurrentUser.anonymous()` without any network call.  This mirrors the orchestrator's own
graceful skip when no LLM API key is configured.

**Token forwarding**:
- SvelteKit frontend — `apps/frontend/src/lib/auth/token.ts` exposes `setToken`/`clearToken`/
  `authHeaders()`.  Both `apiFetch` (regular API calls) and `streamChat` (SSE) include the token
  when present.  The proxy (`+server.ts`) already forwards all request headers upstream.
- Streamlit panel — `src/panel/api_client.py` and `src/panel/chat_client.py` read the token from
  the `API_TOKEN` environment variable via `_auth_headers()`.

### Future Potential
- `setToken` / `clearToken` in the SvelteKit token store provide the integration point for a full
  Auth0 Universal Login redirect flow (future PR).
- Per-user resource isolation (e.g. scoped place lists) can leverage the `CurrentUser.sub` field
  once auth is in place.
- `CurrentUser.permissions` is populated from the JWT `permissions` claim, ready for role-based
  access control in a future iteration.

## Consequences
### Positive Outcomes
- `POST /chat` requires a valid token — prevents unbounded LLM API cost from unauthenticated
  callers.
- All place-write endpoints are protected from anonymous mutations.
- `AUTH_ENABLED=False` default means zero configuration change for local development and CI.
- No new infrastructure: Auth0 is a SaaS identity provider; JWKS are fetched over HTTPS.

### Challenges & Mitigation
- **`authlib` dependency**: add with `uv add authlib`.  `cryptography` is a transitive dependency
  already present via other packages.
- **Token attachment on the frontend is minimal**: `setToken` must be called after a successful
  Auth0 login.  Until a full login flow is implemented, the frontend operates in anonymous mode
  (backend accepts this when `AUTH_ENABLED=False`).
- **Panel token via env var**: `API_TOKEN` must be injected into the Streamlit container for the
  panel to authenticate.  Until Auth0 session support is added to the panel, this is the
  operational path.
- **Documents without `Authorization`** will receive HTTP 401 with `WWW-Authenticate: Bearer`
  when `AUTH_ENABLED=True`.  Existing tests use `dependency_overrides` or rely on
  `AUTH_ENABLED=False` (the default in test settings) to remain unaffected.

## Status
`Accepted` — implemented in production-hardening PR (roadmap A1).
