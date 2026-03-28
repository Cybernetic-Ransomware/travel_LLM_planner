# ADR-08: LangGraph orchestrator module with configurable LLM provider

## Context
The travel_planner application handles place scraping (gmaps module), route optimisation (optimizer module), and a Streamlit management panel — but has no AI/LLM interaction layer. The next product milestone requires conversational features: a chat interface for discussing planned travel points, correcting visit hour preferences, and searching for ticket reservation websites. These capabilities demand an agent orchestration framework that can manage multi-step LLM reasoning, tool calling, and stateful conversations.

Three LLM ecosystem dependencies were already declared in `pyproject.toml` (`langchain>=1.2.13`, `langgraph>=1.1.3`, `langsmith>=0.7.22`) alongside `pydantic-ai>=1.63.0`, but no implementation existed.

## Decision
1. Introduce a new top-level module `src/orchestrator/` as the AI agent layer, built on **LangGraph StateGraph**.
2. Use a **configurable LLM provider** (OpenAI or Anthropic) selectable via the `LLM_PROVIDER` environment variable, with a factory function in `OrchestratorManager._create_llm()`.
3. Expose a **Server-Sent Events (SSE) streaming endpoint** (`POST /api/v1/core/orchestrator/chat`) from day one, using `StreamingResponse` + LangGraph's `astream_events()`.
4. Implement **graceful degradation**: if no LLM API key is configured, `app.state.orchestrator` is set to `None`, the application starts normally, and the `/chat` endpoint returns HTTP 503. Existing modules (gmaps, optimizer) are unaffected.
5. Exclude `src/orchestrator/*` from the `ty` type checker due to incompatibility between `ty` v0.0.21 and LangGraph's `TypeVar` bounds.

## Rationale
### Evaluation of Alternatives
- **Raw LangChain chains (LCEL)** — functional for simple prompt→response pipelines, but lacks built-in state management, conditional routing, and the graph-based control flow needed for multi-step agent reasoning with tool calls.
- **pydantic-ai** — already in `pyproject.toml` but designed for structured output extraction, not multi-turn conversational agents with tool-calling loops. May complement LangGraph in the future for output parsing.
- **crewAI / autogen** — higher-level multi-agent frameworks; over-engineered for the current single-agent use case. LangGraph provides the right level of abstraction: explicit graph topology with full control over node logic.
- **LangGraph (chosen)** — StateGraph provides typed state (TypedDict), conditional routing, built-in support for tool-calling loops, checkpointing for conversation persistence, and native async streaming. The graph topology is explicit and testable.

### Technical Considerations
- **StateGraph with TypedDict**: `AgentState` uses `Annotated[list, add_messages]` as the message reducer, providing Redux-like automatic message accumulation across graph nodes. This avoids manual state management bugs.
- **Factory pattern for LLM**: `_create_llm()` returns `ChatOpenAI` or `ChatAnthropic` based on `LLM_PROVIDER`. Adding a new provider requires only a new `if` branch — no changes to the graph or router.
- **SSE from the start**: LLM responses have 2–30 s latency. SSE streaming provides immediate feedback to the client as tokens are generated, avoiding timeout-prone long-polling. The `astream_events(version="v2")` API yields structured events that the router formats as `data: {"content": "..."}\n\n` lines.
- **Graceful skip**: The lifespan checks `settings.openai_api_key` or `settings.anthropic_api_key` (based on provider) before initialising `OrchestratorManager`. This allows the full Docker stack to start in environments where LLM keys are not yet configured (CI, local dev focused on gmaps/optimizer).
- **ty exclusion**: LangGraph uses `TypedDictLikeV1 | DataclassLike` as TypeVar bounds that `ty` v0.0.21 cannot resolve for our `TypedDict` subclass. All five diagnostics are false positives. The exclusion is scoped to `src/orchestrator/*` only; the rest of the codebase remains fully type-checked.

### Integration with Existing Environment
- `OrchestratorManager` follows the identical lifecycle pattern as `GooglePlacesManager` and `GoogleRoutesManager`: `__aenter__`/`__aexit__`, initialised in `lifespan.py`, stored on `app.state`, accessed via `Annotated[..., Depends()]` in `deps.py`.
- Router registration follows the existing three-level chain: `src/orchestrator/__init__.py` → `src/core/__init__.py` → `src/core/routers.py`.
- Seven new `Settings` fields were added to `src/config/config.py` (`LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_MODEL_NAME`, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`) with empty/false defaults.
- `tests/conftest.py` `client` fixture sets `app.state.orchestrator = None`, ensuring existing tests pass without an LLM key.

### Future Potential
- The `router_node` conditional edge is the extension point for tool-calling: new tool nodes are added to the graph, and `router_node` gains dispatch logic based on `AIMessage.tool_calls`.
- LangSmith tracing is already wired (env vars set in `connect()`) — enabling it requires only setting `LANGSMITH_TRACING=True` and providing an API key.
- The graph topology (`START → router → chatbot → END`) will evolve into `START → router → chatbot/tools → router → ... → END` as tool nodes are added.

## Consequences
### Positive Outcomes
- The application has a functional AI endpoint from the skeleton stage, with SSE streaming and automatic LangSmith tracing.
- The orchestrator is fully optional — zero impact on existing functionality when unconfigured.
- The module structure and DI patterns are consistent with the rest of the codebase, lowering the learning curve.
- 49 unit tests cover models, graph structure, manager lifecycle, and router endpoints.

### Challenges & Mitigation
- **LangChain/LangGraph version instability**: these libraries evolve rapidly. Mitigated by isolating all LangChain usage behind `OrchestratorManager`; if a breaking change occurs, only the manager and graph files need updating.
- **`ty` exclusion**: reduces type-checking coverage for the orchestrator module. Mitigated by comprehensive unit tests and future re-evaluation as `ty` matures.
- **Prompt injection risk**: user-supplied messages are passed directly to the LLM. Mitigated in future phases by input sanitisation, length limits, and restricting tool nodes to a well-defined allowlist.

## Status
`Accepted` — effective from branch `feature/langgraph-orchestrator`.
