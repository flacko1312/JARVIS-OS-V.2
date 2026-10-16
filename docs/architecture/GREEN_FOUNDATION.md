# GREEN Foundation Architecture

Status: **IMPLEMENTED + RUNTIME INTEGRATED**. Last verified from code: 2026-10-16.

## Overview

Eighteen passive, observational, metadata-only infrastructure components split across two layers (3541 total source lines, 372 tests):

- **Foundation** (10 components): Core infrastructure — tracing, events, registry, contracts, capabilities, loop guards, budgets, skills, documentary RAG, capability catalog.
- **Runtime Integration** (8 components): Bridges connecting foundation to the live JARVIS runtime — shadow instrumentation in `_execute_tool`, tool metadata parity, agent adapters, capabilities query surface, budget guard, skills runtime, RAG runtime.

OpenJarvis is an architectural reference only. It is not a runtime dependency or authority in JARVIS.

## Authority boundaries

All GREEN components are subordinate to existing JARVIS authority:

```
USER → JARVIS / Gemini Live → JARVIS Authority → guards/approvals → tool/LILITH → result → user
                                                    ↓ (shadow)
                                              GREEN observability
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
- **Runtime Bridge**: instruments `_execute_tool`, never changes dispatch

LILITH remains canonical for persistent personal memory, Home Assistant authority, persistent routines, and its existing security/approval model.

---

## Foundation Components

### 1. ExecutionTrace (`core/green/execution_trace.py`) — 199 lines

Structured tracing with unique trace IDs, parent/child correlation, session/turn/FunctionCall correlation, timing, centralized secret redaction, and bounded in-memory storage.

- Feature flag: `JARVIS_EXECUTION_TRACE_ENABLED=1`
- Redacts: password, token, api_key, authorization, cookie, secret, private_key, access_token, refresh_token, credential
- 28 tests

### 2. Event Bus (`core/green/event_bus.py`) — 109 lines

Lightweight in-process pub/sub. Subscriber exceptions are isolated — a failing handler never crashes core operations. Event vocabulary: TURN, ROUTING, TOOL, AGENT, LILITH, TRACE lifecycle events.

- Feature flag: `JARVIS_EVENT_BUS_ENABLED=1`
- 15 tests

### 3. Tool Registry (`core/green/tool_registry.py`) — 151 lines

Central catalogue of JARVIS tools with domain, risk level, capabilities, schema validation. Includes `catalogue_from_declarations()` for parity with existing TOOL_DECLARATIONS.

- Feature flag: `JARVIS_TOOL_REGISTRY_ENABLED=1`
- Has no `execute()` method by design
- 20 tests

### 4. Agent Contract (`core/green/agent_contract.py`) — 175 lines

Common interface (AgentProtocol) for existing agents. BaseAgent with adapter pattern for planner, executor, dev_agent, deep_research. Structured AgentRequest/AgentContext/AgentResult/AgentError.

- States: CREATED, RUNNING, WAITING, COMPLETED, FAILED, CANCELLED, TIMED_OUT, BUDGET_EXHAUSTED, LOOP_DETECTED
- 19 tests

### 5. Capabilities (`core/green/capabilities.py`) — 127 lines

Validated enum vocabulary describing what tools/agents/skills can do: filesystem, browser, windows, vision, memory, home, development, network, system, multimedia, communication. Unknown capabilities are rejected (fail-closed).

- 18 tests

### 6. Loop Guards (`core/green/loop_guard.py`) — 131 lines

Deterministic fingerprint-based detection: same-operation, same-error, no-progress stagnation. Configurable thresholds. Returns structured LoopDetection — never autonomously acts.

- 14 tests

### 7. Agent Budgets (`core/green/agent_budget.py`) — 145 lines

Step, tool-call, failure, consecutive-failure, and runtime-seconds limits. Clean BUDGET_EXHAUSTED with structured reason. Integrates with Agent Contract.

- 12 tests

### 8. Skills Framework (`core/green/skills.py`) — 217 lines

Local-only, version-controlled skill definitions with validated capabilities, allowed-tool enforcement, and step validation. SkillRunner produces tool requests — never calls handlers directly. Two safe reference skills included.

- No community/remote skills
- No arbitrary code execution
- 21 tests

### 9. Documentary RAG (`core/green/documentary_rag.py`) — 289 lines

Local document retrieval with path exclusions for secrets/binaries, lexical TF scoring, source attribution, stable chunk IDs. Interface supports future BM25/embedding/hybrid backends.

- Never feeds into personal memory
- Feature flag: `JARVIS_RAG_ENABLED=1`
- 28 tests

### 10. Capability Catalog (`core/green/capability_catalog.py`) — 762 lines

Auto-generated searchable Markdown document of all JARVIS capabilities. Built from real Tool Registry, Capabilities, and Agent metadata. Includes Spanish/English search terms, status symbols, authority attribution, and side-effect/approval indicators.

- Output: `docs/JARVIS_CAPABILITIES.md` (generated, not manually maintained)
- Opens in VS Code (preferred) or Notepad (fallback)
- API: `build_inventory()`, `render_markdown()`, `write_catalog()`, `open_catalog()`
- All 48 JARVIS tools mapped to categories with bilingual search terms
- 33 tests (catalog) + 18 tests (integration)

---

## Runtime Integration Components

### 11. Runtime Bridge (`core/green/runtime.py`) — 248 lines

Single integration surface between JARVIS `_execute_tool` and GREEN infrastructure. Wired into main.py via lazy imports. Instruments tool rejection, authorization, start/complete/fail lifecycle, and turn lifecycle.

- Recursion guard prevents trace→event→trace loops
- Dynamic module references for testable flag checking
- All exceptions caught and isolated from user-facing execution
- 24 tests

### 12. Tool Metadata (`core/green/tool_metadata.py`) — 265 lines

Canonical domain, risk level, capability, and side-effect mapping for all 48 JARVIS tools. Powers the enriched Tool Registry and parity checker.

- Full parity: 48/48 tools mapped
- `enrich_registry_from_declarations()` and `check_parity()` APIs
- 21 tests

### 13. Agent Adapters (`core/green/agent_adapters.py`) — 107 lines

BaseAgent wrappers for the three real JARVIS agents: AgentExecutor, dev_agent, deep_research. Lazy imports keep existing execution unchanged. Provides structured lifecycle via `_do_execute` pattern.

- AgentExecutorAdapter: planning, tool_use, replanning + cancel support
- DevAgentAdapter: code_generation, code_editing, development
- DeepResearchAdapter: web_search, analysis, report_generation
- 29 tests

### 14. Capabilities Runtime (`core/green/capabilities_runtime.py`) — 171 lines

Unified read-only query surface for capability metadata. Supports lookup by tool name, agent ID, domain, and capability tag. Ties together tool_metadata + agent_adapters.

- Feature flag: `JARVIS_CAPABILITIES_RUNTIME_ENABLED=1`
- 23 tests

### 15. Budget Guard (`core/green/budget_guard.py`) — 159 lines

Per-agent budget tracking (steps, tool calls, time, consecutive failures) integrated with LoopGuard. Reports exhaustion but does not kill agents. Default budgets for all three agent adapters.

- Feature flag: `JARVIS_BUDGET_GUARD_ENABLED=1`
- 18 tests

### 16. Skills Runtime (`core/green/skills_runtime.py`) — 133 lines

Read-only skill listing, detail lookup, and execution preview. Built-in safe skills auto-registered. Skills execute through normal JARVIS authority — never bypass guards.

- Feature flag: `JARVIS_SKILLS_RUNTIME_ENABLED=1`
- 16 tests

### 17. RAG Runtime (`core/green/rag_runtime.py`) — 146 lines

Read-only documentary retrieval with source attribution. Auto-indexes docs/ directories. Excludes secrets from indexing. Separate from personal memory (LILITH).

- Feature flag: `JARVIS_RAG_RUNTIME_ENABLED=1`
- 15 tests

---

## Feature Flags

All GREEN components default to disabled. Existing JARVIS behavior is unchanged when flags are unset:

| Flag | Component | Layer |
|---|---|---|
| `JARVIS_EXECUTION_TRACE_ENABLED` | ExecutionTrace | Foundation |
| `JARVIS_EVENT_BUS_ENABLED` | Event Bus | Foundation + Runtime |
| `JARVIS_TOOL_REGISTRY_ENABLED` | Tool Registry | Foundation |
| `JARVIS_RAG_ENABLED` | Documentary RAG | Foundation |
| `JARVIS_CAPABILITIES_RUNTIME_ENABLED` | Capabilities query | Runtime |
| `JARVIS_BUDGET_GUARD_ENABLED` | Budget enforcement | Runtime |
| `JARVIS_SKILLS_RUNTIME_ENABLED` | Skills listing/preview | Runtime |
| `JARVIS_RAG_RUNTIME_ENABLED` | RAG retrieval | Runtime |

Components without runtime integration (Agent Contract, Capabilities, Loop Guards, Budgets, Skills, Capability Catalog) need no feature flag — they are library code used by explicit callers.

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

## Test Summary

**372 GREEN tests**, all passing (verified 2026-10-16). 18 test files across foundation and runtime layers:

| Test file | Tests | Component |
|---|---|---|
| test_execution_trace.py | 28 | ExecutionTrace |
| test_event_bus.py | 15 | Event Bus |
| test_tool_registry.py | 20 | Tool Registry |
| test_agent_contract.py | 19 | Agent Contract |
| test_capabilities.py | 18 | Capabilities |
| test_loop_guard.py | 14 | Loop Guards |
| test_agent_budget.py | 12 | Agent Budgets |
| test_skills.py | 21 | Skills Framework |
| test_documentary_rag.py | 28 | Documentary RAG |
| test_capability_catalog.py | 33 | Capability Catalog |
| test_catalog_integration.py | 18 | Catalog Integration |
| test_runtime_integration.py | 24 | Runtime Bridge (P1+2) |
| test_tool_parity.py | 21 | Tool Metadata (P3) |
| test_agent_adapters.py | 29 | Agent Adapters (P4) |
| test_capabilities_runtime.py | 23 | Capabilities Runtime (P5) |
| test_budget_guard.py | 18 | Budget Guard (P6) |
| test_skills_runtime.py | 16 | Skills Runtime (P7) |
| test_rag_runtime.py | 15 | RAG Runtime (P8) |
| **Total** | **372** | |

Existing JARVIS regression suite unaffected.

## Commit History

| Commit | Description |
|---|---|
| `1901a1e` | GREEN architectural foundation (10 components, 226 tests) |
| `0120d24` | Visual capability catalog with searchable Markdown output |
| `61208f7` | Wire capability catalog into JARVIS runtime |
| `64626ff` | Wire execution tracing and event bus into JARVIS runtime |
| `78550a5` | Tool registry shadow parity with full metadata |
| `aee85d7` | Agent contract adapters for existing JARVIS agents |
| `66e4a11` | Capabilities runtime query surface |
| `97e5a59` | Budget guard with loop detection integration |
| `62cfd67` | Skills safe runtime integration |
| `b5739b4` | Documentary RAG read-only runtime integration |
| `dc4f61f` | Integration handoff document |
