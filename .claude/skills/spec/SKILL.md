---
description: "Generate a draft PR plan from requirements using parallel Explore and Plan sub-agents"
argument-hint: "<feature description> — describe the feature or change to spec out"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Agent
  - Bash(git log*)
  - Bash(git diff*)
  - Bash(git show*)
  - Bash(git branch*)
  - AskUserQuestion
  - EnterPlanMode
  - ExitPlanMode
  - Edit
  - Write
model: inherit
context: inherit
hooks: {}
user-invocable: true
---

# Spec — Draft PR Planner

Takes a feature description or change request and produces a structured draft PR plan by orchestrating **Explore** and **Plan** sub-agents in parallel phases.

## Spec Agents

Launch **only agents marked `ON`** below. Phase 1 agents (Explore) run first in parallel, then Phase 2 agents (Plan) run in parallel with exploration results.

| # | Tag     | Name                    | `subagent_type` | Focus                                              | Phase | Enabled |
|---|---------|-------------------------|-----------------|-----------------------------------------------------|-------|---------|
| 1 | STRUCT  | Project Structure       | `Explore`       | Find files/modules relevant to the requirements     | 1     | ON      |
| 2 | PATTERN | Patterns & Conventions  | `Explore`       | Existing patterns, utilities, helpers to reuse       | 1     | ON      |
| 3 | RELATED | Related Code & Tests    | `Explore`       | Affected dependencies, existing tests, imports       | 1     | ON      |
| 4 | IMPL    | Implementation Planner  | `Plan`          | Step-by-step implementation plan with file paths     | 2     | ON      |
| 5 | TEST    | Test Planner            | `Plan`          | TDD test plan — what tests to write first            | 2     | ON      |
| 6 | RISK    | Risk Assessor           | `Plan`          | Breaking changes, edge cases, security concerns      | 2     | ON      |

---

## 1. Parse Requirements

Extract `$ARGUMENTS` as the feature/change description.

If `$ARGUMENTS` is empty or too vague to act on, ask the user to provide a clear description of the feature or change before proceeding.

Store the requirements text for use in all agent prompts.

## 2. Enter Plan Mode

Use `EnterPlanMode` tool to enter planning mode. The spec output will form the draft PR plan.

## 3. Launch Explore Agents (Phase 1 — parallel)

For every agent row marked **ON** with Phase **1**, spawn an Agent. Launch all Phase 1 agents **in a single message** (concurrent execution).

Pass the requirements text to each agent.

### STRUCT — Project Structure

**Scope:** Focus ONLY on file paths, directory structure, and entry points. Do NOT analyze code patterns or test coverage.

**First:** Check if the requested feature already exists in the codebase. If it does, report what exists, what's missing (tests, docs, enhancements), and reframe the scope accordingly.

Explore the codebase to find:
- Files and modules most relevant to the requirements
- Directory structure and organization patterns
- Entry points (routes, controllers, handlers) that will be affected
- Database models/schemas involved
- Configuration files that may need changes

Report: list of relevant file paths with brief descriptions of their role.

### PATTERN — Patterns & Conventions

**Scope:** Focus ONLY on code patterns, utilities, and reusable helpers. Do NOT map directory structure or test files.

**First:** Check if the requested feature already exists in the codebase. If it does, report what exists, what's missing (tests, docs, enhancements), and reframe the scope accordingly.

Explore the codebase to identify:
- Existing patterns that should be followed (naming, structure, error handling)
- Reusable utilities, helpers, middleware already available
- Similar features already implemented that can serve as templates
- Validation patterns (Pydantic models/validators)
- Test patterns used in the project (`just test` / `just test-integration`, pytest markers, fixture hierarchy in `tests/conftest.py`)

Report: list of patterns and utilities to reuse, with file paths and examples.

### RELATED — Related Code & Tests

**Scope:** Focus ONLY on dependencies, imports, and existing test coverage. Do NOT analyze code patterns or directory structure.

**First:** Check if the requested feature already exists in the codebase. If it does, report what exists, what's missing (tests, docs, enhancements), and reframe the scope accordingly.

Explore the codebase to find:
- Code that will be directly affected by the change (imports, dependencies)
- Existing tests that cover related functionality
- Shared models/protocols/type aliases that may need extension
- API routes or middleware in the dependency chain
- Database queries or aggregations that touch the same collections

Report: dependency map of affected files and existing test coverage.

## 4. Launch Plan Agents (Phase 2 — parallel)

After all Phase 1 agents return, collect their results. For every agent row marked **ON** with Phase **2**, spawn an Agent. Launch all Phase 2 agents **in a single message** (concurrent execution).

Pass both the original requirements AND the combined Phase 1 exploration results to each Phase 2 agent.

### IMPL — Implementation Planner

Using the exploration results, produce:
- Ordered step-by-step implementation plan
- Specific file paths for each change (modify, create, or delete)
- Code approach for each step (which pattern to follow, which utility to reuse)
- Dependencies between steps (what must be done first)
- Estimated complexity per step (small / medium / large)

### TEST — Test Planner

Using the exploration results, produce:
- TDD test plan: tests to write BEFORE implementation
- Unit tests with file paths and pytest class/function structure, including pytest markers (`unit`, `integration`, `regression`)
- Integration tests for API endpoints
- Edge cases and error scenarios to cover
- Existing tests that need updating
- Mock strategy (what to mock, what to test end-to-end)

### RISK — Risk Assessor

Using the exploration results, assess:
- Breaking changes to existing API contracts or behavior
- Security considerations (auth, input validation, data exposure)
- Performance impact (new queries, N+1 risks, missing indexes)
- Migration needs (MongoDB index changes, collection schema evolution, data backfill)
- Backward compatibility concerns
- Race conditions or concurrency issues
- Impact on existing tests (what might break)

## 5. Aggregate into Draft PR

After all Phase 2 agents return, combine all agent outputs into a unified draft PR plan. Write the plan to the plan file in this format:

```
## Draft PR: <title>

### Summary
<1-3 bullet points on what this change does and why>

### Files to Modify/Create
| File | Action | Description |
|------|--------|-------------|
| path | modify/create/delete | what changes |

### Implementation Checklist
- [ ] Step 1: `path/to/file.py` — description of change
- [ ] Step 2: `path/to/file.py` — description of change
- [ ] ...

### Test Checklist
- [ ] `tests/path/to/test_file.py` — TestClass / test_function — N tests
- [ ] `tests/path/to/test_file.py` — TestClass / test_function — N tests
- [ ] ...

### Risk Assessment
- Breaking changes
- Security considerations
- Performance impact
- Migration needs

### Effort Estimate
- Size: S / M / L / XL
- Files touched: N
- New tests: ~N
- Review complexity: low / medium / high
```

## 5.5. Interactive Refinement from RISK Findings

After aggregating the draft PR, review the RISK agent's findings. If the RISK agent flagged any **HIGH** or **CRITICAL** findings:

1. Use `AskUserQuestion` to ask the user **one targeted question** about whether to include the fix in scope or track it separately
2. Update the plan based on the user's answer before proceeding

If no HIGH or CRITICAL risks were flagged, skip this step.

## 6. Exit Plan Mode

Use `ExitPlanMode` tool to present the draft PR plan for user approval.

The user can then:
- **Approve** — proceed to implementation (use TDD workflow from the test plan)
- **Modify** — adjust the plan before any code changes
- **Reject** — discard and start over with refined requirements

When the user approves the plan, offer to invoke `/tdd` with the test plan pre-populated. Present this as: **"Ready to start TDD? I can invoke `/tdd` with the test plan from this spec."**
