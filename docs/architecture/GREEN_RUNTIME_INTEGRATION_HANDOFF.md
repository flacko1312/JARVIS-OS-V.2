# GREEN Runtime Integration — Handoff Document

**Last updated**: 2026-10-16
**Branch**: main
**Total GREEN tests**: 372 (all passing)

---

## Phase Status

| Phase | Description | Status | Commit | Tests |
|-------|-------------|--------|--------|-------|
| 0 | Baseline (226 foundation tests) | ✅ COMMITTED | `1901a1e` | 226 |
| 1 | ExecutionTrace wired to `_execute_tool` | ✅ COMMITTED | `64626ff` | +24 |
| 2 | Event Bus wired to `_execute_tool` | ✅ COMMITTED | `64626ff` | (shared with P1) |
| 3 | Tool Registry shadow parity | ✅ COMMITTED | `78550a5` | +21 |
| 4 | Agent Contract adapters | ✅ COMMITTED | `aee85d7` | +29 |
| 5 | Capabilities runtime metadata | ✅ COMMITTED | `66e4a11` | +23 |
| 6 | Loop Guards + Agent Budgets | ✅ COMMITTED | `97e5a59` | +18 |
| 7 | Skills safe runtime | ✅ COMMITTED | `62cfd67` | +16 |
| 8 | Documentary RAG runtime | ✅ COMMITTED | `b5739b4` | +15 |
| 9 | Final validation | ✅ COMPLETE | — | 372 total |

---

## Architecture Summary

### Integration Pattern: Shadow/Passive

All GREEN runtime components follow the shadow integration pattern:
1. Legacy JARVIS dispatch remains authoritative
2. GREEN components run alongside as passive observers
3. Feature flags control activation (all default OFF)
4. Exceptions inside GREEN instrumentation are caught and isolated
5. Rollback = set feature flag to "0"

### Feature Flags

| Flag | Component | Default |
|------|-----------|---------|
| `JARVIS_TRACE_ENABLED` | ExecutionTrace recording | off |
| `JARVIS_EVENT_BUS_ENABLED` | Event Bus emission | off |
| `JARVIS_CAPABILITIES_RUNTIME_ENABLED` | Capabilities query surface | off |
| `JARVIS_BUDGET_GUARD_ENABLED` | Budget enforcement + loop detection | off |
| `JARVIS_SKILLS_RUNTIME_ENABLED` | Skills listing + preview | off |
| `JARVIS_RAG_RUNTIME_ENABLED` | Documentary RAG retrieval | off |

### Files Created/Modified

**Runtime bridge** (wired into main.py):
- `core/green/runtime.py` — ExecutionTrace + Event Bus bridge (248 lines)

**Phase 3 — Tool parity**:
- `core/green/tool_metadata.py` — Domain/risk/capability/side-effect maps for 48 tools

**Phase 4 — Agent adapters**:
- `core/green/agent_adapters.py` — BaseAgent wrappers for AgentExecutor, dev_agent, deep_research

**Phase 5 — Capabilities runtime**:
- `core/green/capabilities_runtime.py` — Unified capability query (by tool, agent, domain, tag)

**Phase 6 — Budget guard**:
- `core/green/budget_guard.py` — Per-agent budgets + LoopGuard integration

**Phase 7 — Skills runtime**:
- `core/green/skills_runtime.py` — Read-only skill listing + execution preview

**Phase 8 — RAG runtime**:
- `core/green/rag_runtime.py` — Documentary retrieval with source attribution

**Tests**:
- `core/green/tests/test_runtime_integration.py` — 24 tests (Phases 1+2)
- `core/green/tests/test_tool_parity.py` — 21 tests (Phase 3)
- `core/green/tests/test_agent_adapters.py` — 29 tests (Phase 4)
- `core/green/tests/test_capabilities_runtime.py` — 23 tests (Phase 5)
- `core/green/tests/test_budget_guard.py` — 18 tests (Phase 6)
- `core/green/tests/test_skills_runtime.py` — 16 tests (Phase 7)
- `core/green/tests/test_rag_runtime.py` — 15 tests (Phase 8)

### Authority Chain (unchanged)

```
USER → Gemini Live → JARVIS Authority → guards → tool/LILITH → result
                                          ↓ (shadow)
                                    GREEN observability
```

GREEN never changes authorization, routing, or execution results.

### What Was NOT Modified

- `main.py` dispatch logic (only instrumentation added, no routing changes)
- JL-A10 validation status (CLOSED/PHYSICAL — not touched)
- LILITH authority (remains canonical for persistent memory, routines, Home Assistant)
- Existing agent implementations (adapters wrap, not replace)

---

## Resuming From Here

If continuing this work in a new session:

1. **Run tests**: `.venv\Scripts\python.exe -m pytest core/green/tests/ -v`
2. **Verify 372 passing, 0 failures**
3. **All phases are COMMITTED** — no in-progress work remains
4. **Next potential work**:
   - Enable feature flags for controlled testing
   - Add embeddings/BM25 to RAG retriever (currently TF-based)
   - Wire budget_guard into agent_adapters for live budget enforcement
   - Add GREEN status dashboard to JARVIS UI
   - Performance benchmarks for trace/event overhead

---

## Security Invariants

- No secrets in traces, tests, logs, commits, or fixtures
- Documentary RAG is separate from personal memory (LILITH)
- No new personal-memory authority created
- Feature flags gate all GREEN runtime behavior
- All GREEN exceptions are caught and isolated from user-facing execution
