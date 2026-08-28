# Frontend Architecture Roadmap

[ADR-14](14_ADR-astro-svelte-spike.md) (accepted 2026-07-04, Option C) established the split:
two apps coexist, each with a defined role. This document encodes which app owns which screens
and provides a decision rule so new screens don't require a framework discussion from scratch.

## Current split

| App | Path | Screens |
|-----|------|---------|
| Astro | `apps/astro-frontend/` | `/` public dashboard · `/places` read-only list + map island · `/health` connectivity check · `/route-preview` optimizer workflow island |
| SvelteKit | `apps/frontend/` | `/` authenticated entry · `/places` places management (edit, enrich) · `/optimizer` single-day AND multi-day route optimizer workflow (mode switch) · `/health` backend status |

`/optimizer` is the sole owner of both single-day and multi-day trip planning. The earlier
`/trip` route was an incomplete multi-day prototype (no persistence, no accommodations/transfers
awareness, a flattened per-day map) and has been retired now that `/optimizer` fully absorbs its
scope with a production-quality implementation — see `MultiDayPlanner.svelte` and the rest of
`src/lib/components/optimizer/multiDay/`.

## Framework decision rule

**Use Astro when:**

- Screen is public (no auth or minimal auth)
- Data is read-only
- Interactivity fits in one self-contained island
- No shared state between components

**Use SvelteKit when:**

- Screen requires authentication
- Screen is an application workflow (forms, edits, dialogs)
- State is shared across components (map marker ↔ list ↔ form)
- Feature needs orchestrator/chat, drag & drop, or realtime polling

## Upcoming PRs

1. Public Astro landing / docs
2. SvelteKit: backend-down error handling
3. Spike cleanup after ADR-14 decision

REST contract types are generated from the backend's OpenAPI schema — see
[ADR-19](19_ADR-openapi-typescript-contracts.md).
