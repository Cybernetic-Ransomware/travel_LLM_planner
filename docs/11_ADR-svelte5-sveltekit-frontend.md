# ADR-11: Svelte 5 + SvelteKit as frontend framework

## Context
The travel-planner application includes a Streamlit management panel (`src/panel/`) that is tightly coupled to Python and unsuitable for building a proper user-facing chat interface. The orchestrator module (ADR-08) exposes an SSE streaming endpoint (`POST /api/v1/core/orchestrator/chat`) that emits four distinct event types: `session_id`, `content` (token chunks), `tool_proposal` (interrupt awaiting user confirmation), and `[DONE]`. The frontend must handle streaming state transitions reactively — including a confirm/cancel UI for `tool_proposal` interrupts — without full-page re-renders on every incoming token.

A dedicated JavaScript frontend is required to replace and extend the Streamlit panel.

## Decision
Use **Svelte 5** (runes mode, enforced globally via `svelte.config.js`) with **SvelteKit** as the application framework. The frontend lives in `apps/frontend/` and communicates with the FastAPI backend exclusively via HTTP and SSE.

Supporting technology choices made alongside this decision:
- **Tailwind CSS v4** (via `@tailwindcss/vite`) for styling
- **Paraglide** for i18n (Polish + English)
- **Vitest** with browser and server test projects for component and unit testing
- **npm** as the package manager (over Bun/Deno — see Rationale)

## Rationale
### Evaluation of Alternatives
- **React 19** — the dominant choice in the ecosystem. Virtual DOM diffing introduces unnecessary overhead for token-by-token streaming: each incoming `content` token triggers a subtree reconciliation. Hook-based reactivity (`useState`, `useEffect`) requires careful management of stale closures when consuming an `EventSource` or `ReadableStream`. The ecosystem advantage (shadcn/ui, React Query, Tanstack Router) is not needed at this project scale.
- **Vue 3 (Composition API)** — closer to Svelte in philosophy, but the Vite plugin + Options/Composition API dual surface adds cognitive overhead for a developer new to the JS ecosystem.
- **Vanilla JS / HTMX** — viable for simple form-based UIs, not for a streaming chat interface with reactive confirmation dialogs.
- **Svelte 5 with runes (chosen)** — compiled framework with no virtual DOM runtime. Fine-grained reactivity via `$state` and `$derived` means each token update touches only the affected DOM node. The `$effect` rune provides explicit cleanup for SSE consumers. Runes mode is the Svelte 6 API surface, making this a forward-compatible choice.

### Technical Considerations
- **SSE + runes**: the four SSE event types map naturally to rune-based state. `session_id` and `tool_proposal` are discrete values (`$state<string | null>`); `content` is accumulated into a string. No external state management library is needed.
- **`tool_proposal` confirm flow**: when the backend graph pauses at a tool interrupt, the frontend receives a `tool_proposal` event and must render a confirm/cancel UI, then resume by sending `resume_confirmed: true/false` in the next `POST /chat`. This conditional UI pattern is clean in Svelte: a single `$state` variable controls rendering.
- **Tailwind v4**: uses the new CSS-first configuration model with `@tailwindcss/vite` instead of a `tailwind.config.js` file. Aligns with the project's preference for minimal configuration surface.
- **npm over Bun/Deno**: Bun has documented Windows instability edge cases. Deno's Node.js compatibility layer introduces friction with SvelteKit (a Node.js-first framework). npm is the most battle-tested choice on Windows 11 and produces no surprises with `@sveltejs/kit`.
- **Runes enforced globally**: `svelte.config.js` sets `runes: ({ filename }) => !filename.includes('node_modules')`. This prevents mixing legacy `$: reactive` syntax with rune syntax in the same project.

### Integration with Existing Environment
- The frontend is a fully independent Node.js project with its own `package.json` and `node_modules/`. It has no Python build dependency.
- API communication uses standard `fetch` (SSE via `ReadableStream`) against `http://localhost:8080/api/v1/core/orchestrator/chat`. The base URL will be environment-variable driven via SvelteKit's `$env/static/public`.
- The `@sveltejs/mcp` MCP server is registered in the root `.mcp.json` with `"cwd": "apps/frontend"` so Claude Code can access Svelte documentation without changing working directory.
- `apps/frontend/CLAUDE.md` provides Svelte MCP tool usage instructions, loaded hierarchically alongside the root `CLAUDE.md`.

### Future Potential
- SvelteKit's adapter system allows deployment as a static site (`adapter-static`), a Node.js server (`adapter-node`), or a Docker container alongside the FastAPI backend — no framework change required, only an adapter swap.
- Paraglide i18n is wired from day one; adding a new language requires only a new messages file.
- Vitest browser project (Playwright/Chromium) enables future component tests without a separate test runner.

## Consequences
### Positive Outcomes
- Token streaming updates are handled with zero virtual DOM overhead.
- The `tool_proposal` confirmation flow requires no external state library.
- Runes mode is the canonical Svelte 5 API — documentation, MCP tooling, and community examples are all rune-first.
- The frontend is independently deployable and independently testable.

### Challenges & Mitigation
- **JS ecosystem familiarity**: the developer is new to TypeScript/JS at this scale. Mitigated by the Svelte MCP server (`list-sections`, `svelte-autofixer`) and svelte-skills plugin providing in-session documentation.
- **Svelte 5 is recent (2024)**: fewer Stack Overflow answers than React. Mitigated by official MCP documentation and the enforced runes-only mode, which eliminates legacy API confusion.
- **CORS**: the browser frontend on a different port will require `allow_origins` in FastAPI's `CORSMiddleware`. Handled at integration time.

## Status
`Accepted` — effective from branch `feature/frontend`.
