# ADR-10: LLM tool pattern — closure factory, RunnableConfig scope guard, conditional interrupt

## Context
ADR-08 introduced the LangGraph orchestrator as a chatbot-only graph (`START → router → chatbot → END`) with an explicit extension point: `router_node` was designed to eventually dispatch to tool nodes based on `AIMessage.tool_calls`. ADR-09 introduced a MongoDB-backed checkpointer enabling conversation persistence and state resumption.

The next product milestone requires the LLM to act on recommendations made during chat — specifically, to update preferred visit hours for places in the trip plan. This is the **first LLM-callable tool** added to the orchestrator. The decisions made here establish the pattern for all subsequent tools.

Three non-obvious questions required architectural choices:
1. How should the database dependency reach the tool function at runtime?
2. How should the tool's write access be scoped to prevent unauthorized modifications?
3. When and how should human confirmation be required before a DB write?

## Decision

### 1. Tool factory with closure-bound DB dependency
Tools are created by a `create_tools(db: AsyncDatabase) -> list` factory function in `src/orchestrator/tools.py`. The `db` reference is closure-bound inside each tool function. `build_graph()` gains a `db: AsyncDatabase | None = None` parameter; when provided, it calls `create_tools(db)` and binds the resulting tools to the LLM via `llm.bind_tools(tools)`.

### 2. Scope guard via `RunnableConfig["configurable"]`, not `AgentState`
The tool enforces that only places belonging to the current session can be modified. The allowed place IDs are passed through `RunnableConfig["configurable"]["allowed_place_ids"]`, set by the router before each graph invocation. The tool function declares a `config: RunnableConfig` parameter, which LangGraph's `ToolNode` injects automatically (excluded from the LLM-visible schema).

`allowed_place_ids` is **not** added to `AgentState`. State is checkpointed and shared across turns; security controls should not be persisted or inherited from prior checkpoints.

### 3. `interrupt_before=["tools"]` conditional on checkpointer availability
The graph is compiled with `interrupt_before=["tools"]` only when a checkpointer is present. Without a checkpointer, tools operate in a standard ReAct loop without pause. This preserves the ability to write unit tests that exercise tool calling without a real MongoDB instance, while ensuring the human-in-the-loop confirmation mechanism is active in production (where the MongoDB checkpointer from ADR-09 is always configured).

The resume flow is implemented in `OrchestratorManager.astream_resume(thread_id, confirmed, user_message)`. On rejection, the pending `AIMessage.tool_calls` are cleared by updating state with a new `AIMessage` sharing the same `id` — exploiting LangGraph's `add_messages` reducer, which replaces messages by ID. The graph then resumes from the `router_node` and routes to `END` or re-invokes the chatbot based on the new message.

### 4. Tool field scope limited to `preferred_hour_from`, `preferred_hour_to`, `visit_duration_min`
The `PlacePatch` model also exposes `skipped: bool`. The tool intentionally excludes this field. Marking a place as `skipped` removes it from route optimisation — a destructive action that is harder to reverse accidentally than an hour change, and not covered by the feature requirement ("preferred hours of visits").

## Rationale

### Evaluation of Alternatives

**DB dependency injection approaches:**

| Approach | Verdict |
|---|---|
| Closure-bound via factory (chosen) | Consistent with existing pattern: `build_graph` already closure-binds `llm` into `_chatbot`. No new abstractions needed. |
| `AgentState` field `db: AsyncDatabase` | Rejected: state is serialised by the checkpointer. An `AsyncDatabase` is not serialisable. |
| `RunnableConfig["configurable"]["db"]` | Rejected: config is a dict, not designed for heavy object references; requires passing db through every router call site. |
| Class-based tool with `self._db` | Rejected: `ToolNode` expects callable tools, not class instances with methods; extra wrapping required for no benefit. |

**Scope guard placement:**

| Approach | Verdict |
|---|---|
| `RunnableConfig["configurable"]` (chosen) | Per-invocation, not checkpointed, not LLM-visible. Enforced at the infrastructure level, independent of LLM output. |
| `AgentState.allowed_place_ids` | Rejected: would be checkpointed and could be inherited from a prior session's checkpoint with different places. |
| System prompt instruction only | Rejected: relies on LLM compliance; prompt injection via a malicious place name could bypass this. |
| Validate inside `find_and_update_place` | Rejected: that function has no session context — it's a pure storage function. |

**Human confirmation approaches:**

| Approach | Verdict |
|---|---|
| `interrupt_before=["tools"]` (chosen) | Infrastructure-level guarantee. The tool cannot execute until the graph is explicitly resumed. Works naturally with the MongoDB checkpointer already in place (ADR-09). |
| LLM system prompt instruction ("always ask first") | Rejected as sole mechanism: relies on LLM compliance; a sufficiently adversarial prompt could bypass it. Used in addition as a UX layer. |
| Separate `/confirm` API endpoint | Rejected: introduces additional API surface and requires client-side state tracking outside the session_id. |
| Two-phase tool (propose + execute) | Rejected: requires the tool to manage its own stateful phase — duplicating what `interrupt_before` provides at the framework level. |

### Technical Considerations

**ReAct loop topology:**

```
START → router_node ─── "chatbot" ──→ chatbot ──→ _after_chatbot ──→ tools (interrupt_before) ──→ chatbot
                     └── "end" ──→ END                            └── END
```

`router_node` retains its original role as the START conditional edge. A new `_after_chatbot` function serves as the conditional edge from the chatbot node, routing to `"tools"` when `AIMessage.tool_calls` is non-empty and to `END` otherwise. This cleanly separates entry-point routing from post-LLM routing.

**Config injection for `config: RunnableConfig`:**

LangChain's `@tool` decorator recognises a parameter typed as `RunnableConfig` and excludes it from the tool's JSON schema (the schema shown to the LLM). `ToolNode` injects the graph's current runtime config before invoking the tool. This is a documented LangGraph pattern; no monkey-patching or wrapper is required.

**Cancellation via message ID replacement:**

LangGraph's `add_messages` reducer deduplicates by message `id`. Calling `graph.aupdate_state(config, {"messages": [AIMessage(id=original_id, content="...")]})` atomically replaces the interrupted `AIMessage` (which carries `tool_calls`) with a clean version that has none. The graph then resumes from this updated state, and `router_node` sees an `AIMessage` without `tool_calls`, routing to `END`.

**`aput_writes` in the checkpointer (ADR-09 interaction):**

ADR-09 noted that `aput_writes` is a no-op. Tool call results are intermediate writes. With tools now active, `ToolMessage` objects produced by `ToolNode` will be written via `aput_writes` between the tool node and the chatbot node. The no-op implementation causes these intermediate results to not be individually persisted — but they are included in the full checkpoint written by `aput` at the end of the resumed turn. This is acceptable: if the process crashes between tool execution and the LLM's final response, the next turn will re-run the chatbot node with the tool result in its message history (from the last `aput` checkpoint).

### Integration with Existing Environment
- `src/gmaps/models.py → PlacePatch` and `src/gmaps/storage.py → find_and_update_place` are reused unchanged. The tool is a thin wrapper that adds scope enforcement and error-to-string conversion.
- `OrchestratorManager.astream()` gains a `configurable: dict | None` parameter, merged into `config["configurable"]`. Existing callers passing only `thread_id` are unaffected (backward compatible).
- `ChatRequest` gains `resume_confirmed: bool | None = None`. Existing clients that do not send this field receive `None` (normal turn, no resume).
- Unit tests pass a `MagicMock()` as `db` to `build_graph()`. Since no checkpointer is provided in tests, `interrupt_before=[]` — tools execute synchronously in the ReAct loop without pausing.

### Future Potential
- Additional tools (e.g., `skip_place`, `update_visit_duration`) follow the same factory pattern: extend `create_tools(db)` to return more items from the list.
- If `aput_writes` is implemented (ADR-09 future work), intermediate tool results will be individually persisted, enabling crash recovery between the tool execution and the LLM's final reply.
- The scope guard pattern (allowed IDs in `configurable`) generalises to any future tool that must be restricted to session-scoped resources.

## Consequences

### Positive Outcomes
- The LLM can now update preferred visit hours in MongoDB from within a conversation, with all writes gated by explicit user confirmation.
- The tool pattern (factory + closure + config scope guard) is reusable: adding the next tool requires only extending `create_tools()`.
- `interrupt_before` is infrastructure-enforced — the DB write cannot happen without graph resumption, regardless of LLM output.
- Existing unit tests required only minimal updates (`**kwargs` in two mock functions, `_checkpointer = None` in `_make_mock_orchestrator`). No integration tests were broken.
- 25 new tests cover the tool function (metadata, success, validation errors, scope guard) and the updated graph topology (ToolNode presence, `_after_chatbot` routing, place ID in system prompt).

### Challenges & Mitigation
- **`aput_writes` no-op (ADR-09)**: tool results are not individually checkpointed. A process crash between tool execution and the LLM's final reply would cause the tool to re-execute on the next turn. For the current tool (`update_visit_hours`) this is idempotent — writing the same hours twice has no harmful effect. Non-idempotent future tools must revisit this.
- **Prompt injection via place names**: place names from MongoDB are embedded in the system prompt. A malicious place name could influence the LLM's tool calls. The scope guard limits the blast radius (only session-scoped places can be modified), but the injection vector itself is not eliminated. Sanitising place names before embedding them in the prompt is recommended before production deployment.
- **No validation against `opening_hours`**: the tool allows setting `preferred_hour_from=22, preferred_hour_to=23` for a place that closes at 18:00. The optimizer handles this correctly (marks the place as `TIME_WINDOW_INFEASIBLE`), but the user receives no warning at the point of update. A future improvement is to check the preferred window against `opening_hours` and include a feasibility hint in the tool's return string.

## Status
`Accepted` — effective from branch `feature/llms-tools-for-db`.
