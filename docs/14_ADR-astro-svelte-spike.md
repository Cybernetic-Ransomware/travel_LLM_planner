# ADR: Astro + Svelte islands spike as an alternative frontend shell

## Context
The application frontend lives in `apps/frontend` as a SvelteKit 5 app (ADR-11, ADR-12). Most of its
pages are data-heavy but only partially interactive: a dashboard of place statistics, a places explorer
with filters and a Leaflet map, and diagnostic views. SvelteKit ships a full client-side router and
hydrates whole routes, which raised the question whether an islands-oriented framework would serve the
mostly-static parts of the UI with less client-side JavaScript.

To answer this with evidence instead of vendor material, a time-boxed spike was built at
`apps/astro-frontend`: an Astro 7 application with Svelte 5 islands covering three screens — `/`
(dashboard statistics), `/places` (filterable table plus on-demand Leaflet map), and `/health`
(backend connectivity check). The existing SvelteKit app was left untouched as the reference point.

## Decision
Build the spike as a separate Astro 7 + Svelte 5 + Tailwind CSS v4 application in `apps/astro-frontend`,
talking directly to the FastAPI backend from the browser, with a development CORS configuration added to
the backend instead of an API proxy. The spike is an experiment; no migration decision is implied by its
existence.

## Rationale
### Evaluation of Alternatives
- **Extend the SvelteKit app** — would not answer the question; SvelteKit hydrates per-route, so the
  JavaScript-per-page comparison needs a genuinely different shell.
- **Astro proxy endpoints instead of CORS** — rejected for the spike; a proxy adds a second server hop
  and hides the real integration cost. Direct browser calls plus a `CORS_ALLOW_ORIGINS` setting in the
  FastAPI app (default `http://localhost:4321`) is smaller and reversible.
- **Server-side data fetching in Astro frontmatter** — rejected; with static output the fetch runs at
  build time, coupling `npm run build` to a running backend and baking stale data. All backend data is
  fetched client-side from islands via `PUBLIC_BACKEND_URL`.

### Technical Considerations
- One island per page: `DashboardStats`, `PlacesExplorer`, `HealthCheck` (`client:load`). Filter, table
  and map components are plain Svelte children inside the `PlacesExplorer` island, sharing one reactive
  graph — nested components must not carry their own `client:` directives.
- Leaflet (~150 kB) is code-split automatically: `LeafletMap.svelte` dynamically imports `leaflet` in
  `onMount`, and the component only mounts behind a "Show map" toggle, so the chunk is fetched on demand.
- Tailwind v4 via `@tailwindcss/vite`, same zero-config approach as `apps/frontend`.
- The stack tracks current majors: Astro 7 (Vite 8, stricter Rust-based compiler) with `@astrojs/svelte` 9
  and TypeScript 6, matching the TypeScript major used by `apps/frontend`.
- `npm run check` chains `astro check` and `svelte-check`; `astro check` alone does not type-check
  `.svelte` files.
- Types (`PlaceOut`, `RouteStep`) are duplicated by hand into `src/lib/types.ts`; an OpenAPI type
  generator was deliberately left out of the spike.

### Integration with Existing Environment
- `apps/astro-frontend` is excluded from the uv workspace in `pyproject.toml`, mirroring `apps/frontend`.
- Backend changes are limited to `CORSMiddleware` in `src/main.py` driven by a new
  `cors_allow_origins` field in `Settings`; API routes, models and tests are untouched.
- The SvelteKit app keeps working unchanged; both frontends can run side by side against the same
  backend.

### Future Potential
The spike enables three follow-up paths: (A) continue migrating application screens to Astro, (B) keep
SvelteKit for the application and discard the spike, or (C) keep Astro only for public/documentation
pages. It also leaves reusable groundwork either way: the dev CORS setting and the measured baseline of
JavaScript shipped per page.

Quantitative results (payload, requests, Leaflet loading, build times, error visibility, code
ergonomics) are recorded in [spike-astro-vs-sveltekit-metrics.md](spike-astro-vs-sveltekit-metrics.md),
reproducible via `scripts/measure_frontends.py`.

Preliminary observations against the spike's evaluation questions:
- *Did Astro simplify the frontend?* The page shells are simpler (no router, no load functions), but the
  data flow is more manual — every island fetches for itself, where SvelteKit centralises this in load
  functions and shared state.
- *Does island hydration give real control?* Yes — layout, navigation and headers ship zero JavaScript,
  and the Leaflet chunk demonstrably loads only on demand.
- *Is the FastAPI integration convenient?* Yes, once CORS exists; the trade-off is that browser-visible
  errors cannot distinguish "backend down" from "CORS missing".
- *Is SvelteKit still better for this application?* For the interactive core (route planner,
  orchestrator chat) most logic would end up inside large islands anyway, which weakens Astro's benefit
  there.
- *Continue, stop, or scope down?* **Option C chosen (2026-07-04)**: Astro is retained for
  public-facing, mostly-static screens (marketing, documentation, landing pages). SvelteKit
  (`apps/frontend`) remains the shell for interactive application screens. The route-preview spike
  on `feature/astro-route-preview` confirmed the boundary: a form-input → optimizer → map workflow
  fits inside a coherent 178-LOC island, but any cross-component coordination (map marker ↔ place
  checklist) would require a shared store or a single mega-island — neither of which Astro makes
  ergonomic. The JS saving is real (51.9 kB vs ~280 kB SvelteKit `/places`), but it erodes in
  proportion to interactivity; for screens with orchestrator chat or drag-and-drop it would vanish.

## Consequences
### Positive Outcomes
- Working three-screen Astro app with measurable per-page JavaScript payloads.
- `npm run dev`, `npm run build` and `npm run check` all pass without a running backend.
- Minimal, reversible backend footprint (one setting, one middleware registration).

### Challenges & Mitigation
- **Duplicated types** drift from the backend models — acceptable for the spike; an OpenAPI generator is
  the known fix if the migration continues.
- **CORS origin mismatch** if the Astro dev server auto-increments its port — surfaced on the `/health`
  page; override via `CORS_ALLOW_ORIGINS` in the backend `.env`.
- **Two frontends in the repo** cost maintenance attention — mitigated by the spike's explicit
  time-box and this ADR recording the exit criteria.

## Status
`Accepted` — option C: Astro for public/static screens, SvelteKit for the interactive application
core. Decision taken 2026-07-04 after the route-preview spike (`feature/astro-route-preview`)
confirmed the complexity boundary. `apps/astro-frontend` is kept; `apps/frontend` (SvelteKit)
remains the primary application shell.
