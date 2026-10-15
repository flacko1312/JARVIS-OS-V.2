# AUT-02 — LOCAL AI / OLLAMA TEXT & CONNECTIVITY

**Date:** 2026-10-15  
**Avatar:** DEFERRED BY USER — OUT OF CURRENT SCOPE

## Implemented

- A dedicated async Ollama text provider in `core/local_ai.py`.
- Credential-free loopback URL enforcement (`localhost`, `127.0.0.1`, `::1` only).
- Environment/config resolution for enabled state, URL, model, connect timeout and read timeout.
- Bounded timeouts and exactly one status request plus one generation request; no retry loop and no Gemini↔Ollama loop.
- `/api/tags` health/model discovery with distinct `offline`, `model_missing`, `disabled`, `temporary/error` and `online` results.
- Explicit missing-model diagnostics and empty-response handling.
- `/api/chat` non-streaming text generation.
- Provider capability reporting, including the honest offline-capability list.
- `LOCAL_AI` router execution independent of LILITH.
- A provider status registry distinguishing Internet, Gemini, Ollama and LILITH states, with transition history and recovery snapshots.

The registry represents `available`, `unavailable`, `temporary_failure`, `auth_failure`, `not_configured` and `model_missing` separately. Actual Gemini/Internet probes can be supplied by the runtime without coupling the registry to credentials or mandatory network traffic.

## Offline truth

JARVIS can report `local_text` as offline-capable only when Ollama is running and the configured text model is present. This does not claim a complete offline assistant: browser/web/Gmail/Gemini Live/LILITH/HA remain external dependencies.

## Files changed

- `core/local_ai.py` (new)
- `core/provider_status.py` (new)
- `router/core.py`
- `tests/test_aut02_local_ai_offline.py` (new)
- `tests/test_block3_ollama_router.py` (stale not-implemented expectation updated)

## Validation

```text
137 passed, 0 failed, 0 skipped, 1 warning, 25 subtests passed
```

Tests cover loopback rejection, configuration, operational status, stopped provider, missing model, one-shot generation, router independence from LILITH and provider recovery transitions. No real network/provider call or credential was used.

## Remaining physical boundary

An installed Ollama service and real model response remain **PHYSICAL TEST REQUIRED**. Automated tests prove request/state semantics, not local model quality or installation.
