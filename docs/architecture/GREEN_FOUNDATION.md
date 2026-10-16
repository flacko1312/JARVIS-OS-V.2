# GREEN Foundation Architecture

Status: **IMPLEMENTED** as of 2026-10-16.

## Overview

Nine passive, observational, metadata-only infrastructure components that improve JARVIS observability, modularity, agent lifecycle, tool organization, capabilities, loop protection, execution budgets, reusable workflows, and documentary knowledge retrieval.

OpenJarvis is an architectural reference only. It is not a runtime dependency or authority in JARVIS.

## Authority boundaries

All GREEN components are subordinate to existing JARVIS authority:

```
USER → JARVIS / Gemini Live → JARVIS Authority → guards/approvals → tool/LILITH → result → user
```

- **ExecutionTrace**: observes, never authorizes
- **Event Bus**: reports events, never authorizes
- **Tool Registry**: catalogues tools, never authorizes or executes
- **Agent Contract**: standardizes lifecycle, never routes or authorizes
- **Capabilities**: metadata/validation, never replaces existing guards
- **Loop Guards**: detect repetition, return STOP — never choose alternatives
- **Agent Budgets**: enforce limits, return BUDGET_EXHAUSTED — never escalate
- **Skills**: produce tool requests that go through normal JARVIS authority
- **Documentary RAG**: read-only retrieval, never writes personal memory

LILITH remains canonical for persistent personal memory, Home Assistant authority, persistent routines, and its existing security/approval model.

## Components

### 1. ExecutionTrace (`core/green/execution_trace.py`)

Structured tracing with unique trace IDs, parent/child correlation, session/turn/FunctionCall correlation, timing, centralized secret redaction, and bounded in-memory storage.

- Feature flag: `JARVIS_EXECUTION_TRACE_ENABLED=1`
- Redacts: password, token, api_key, authorization, cookie, secret, private_key, access_token, refresh_token, credential
- 28 tests

### 2. Event Bus (`core/green/event_bus.py`)

Lightweight in-process pub/sub. Subscriber exceptions are isolated — a failing handler never crashes core operations. Event vocabulary: TURN, ROUTING, TOOL, AGENT, LILITH, TRACE lifecycle events.

- Feature flag: `JARVIS_EVENT_BUS_ENABLED=1`
- 15 tests

### 3. Tool Registry (`core/green/tool_registry.py`)

Central catalogue of JARVIS tools with domain, risk level, capabilities, schema validation. Includes `catalogue_from_declarations()` for parity with existing TOOL_DECLARATIONS.

- Feature flag: `JARVIS_TOOL_REGISTRY_ENABLED=1`
- Has no `execute()` method by design
- 20 tests

### 4. Agent Contract (`core/green/agent_contract.py`)

Common interface (AgentProtocol) for existing agents. BaseAgent with adapter pattern for planner, executor, dev_agent, deep_research. Structured AgentRequest/AgentContext/AgentResult/AgentError.

- States: CREATED, RUNNING, WAITING, COMPLETED, FAILED, CANCELLED, TIMED_OUT, BUDGET_EXHAUSTED, LOOP_DETECTED
- 19 tests

### 5. Capabilities (`core/green/capabilities.py`)

Validated enum vocabulary describing what tools/agents/skills can do: filesystem, browser, windows, vision, memory, home, development, network, system, multimedia, communication. Unknown capabilities are rejected (fail-closed).

- 18 tests

### 6. Loop Guards (`core/green/loop_guard.py`)

Deterministic fingerprint-based detection: same-operation, same-error, no-progress stagnation. Configurable thresholds. Returns structured LoopDetection — never autonomously acts.

- 14 tests

### 7. Agent Budgets (`core/green/agent_budget.py`)

Step, tool-call, failure, consecutive-failure, and runtime-seconds limits. Clean BUDGET_EXHAUSTED with structured reason. Integrates with Agent Contract.

- 12 tests

### 8. Skills Framework (`core/green/skills.py`)

Local-only, version-controlled skill definitions with validated capabilities, allowed-tool enforcement, and step validation. SkillRunner produces tool requests — never calls handlers directly. Two safe reference skills included.

- No community/remote skills
- No arbitrary code execution
- 21 tests

### 9. Documentary RAG (`core/green/documentary_rag.py`)

Local document retrieval with path exclusions for secrets/binaries, lexical TF scoring, source attribution, stable chunk IDs. Interface supports future BM25/embedding/hybrid backends.

- Never feeds into personal memory
- Feature flag: `JARVIS_RAG_ENABLED=1`
- 28 tests

## Feature flags

All GREEN components default to disabled. Existing JARVIS behavior is unchanged when flags are unset:

| Flag | Component |
|---|---|
| `JARVIS_EXECUTION_TRACE_ENABLED` | ExecutionTrace |
| `JARVIS_EVENT_BUS_ENABLED` | Event Bus |
| `JARVIS_TOOL_REGISTRY_ENABLED` | Tool Registry |
| `JARVIS_RAG_ENABLED` | Documentary RAG |

Components without runtime integration (Agent Contract, Capabilities, Loop Guards, Budgets, Skills) need no feature flag — they are library code used by explicit callers.

## Rollback / disable

Set all feature flags to `0` (or remove them). GREEN components have zero side effects when disabled. To fully remove: delete `core/green/` and `core/green/tests/`.

## JL relationship

GREEN does not modify or rewrite JL-A10 execution paths. JL-A10 is CLOSED with physical E2E PASS. GREEN observability can attach to JL paths (trace/event emission) only as metadata; it never changes routing, authorization, or results.

## NOT implemented (by design)

- MCP
- Generic sandbox execution
- Monitor Agents connected to real LILITH
- Complete offline voice system
- Learned router
- Policy/autonomous learning
- Self-modification
- OpenJarvis runtime/agent loop/memory/scheduler/frontend/voice stack
- Second Home Assistant authority
- Second personal memory

## Test summary

175 focused GREEN tests, all passing. Existing JARVIS regression suite unaffected.
