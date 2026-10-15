# AUT-01 — INTENT ROUTER COMPLETION

**Date:** 2026-10-15  
**Base HEAD:** `1c05b3edfbe3345cae9a5f8aa699d306bc7a2010` plus preserved working-tree changes  
**Avatar:** DEFERRED BY USER — OUT OF CURRENT SCOPE

## Result

The deterministic router now has explicit `GMAIL`, `MULTIMEDIA`, `REMINDERS` and `PRESENTATIONS` domains. These are classified locally and passed to the existing Gemini tool-dispatch surface; they do not depend on LILITH. `LOCAL_AI` is also correctly independent from LILITH and routes explicit local/Ollama wording to its own domain. Provider execution is implemented in AUT-02.

## Safety and precedence

- Explicit development wording wins over an application name: `Arregla mi aplicación Spotify` → development.
- Application launch remains Windows control: `Abre Spotify` → windows.
- Informational wording remains conversation: `¿Qué es Spotify?` → conversation fallback.
- Gmail, media, reminder and presentation rules require action-bearing wording rather than a bare product/entity word.
- Competing domains inside the ambiguity gap now produce a structured clarification request before dispatch. No action is guessed from fuzzy overlap.
- `LOCAL_AI` was removed from the set of LILITH-required domains.

## Files changed

- `router/models.py`
- `router/classifier.py`
- `router/core.py`
- `runtime.py`
- `tests/test_aut01_router_completion.py` (new)

## Validation

```text
256 passed, 0 failed, 0 skipped, 1 warning, 19 subtests passed
```

The focused run covered the new routing matrix plus existing Block 1, Block 3 and runtime/LILITH routing regressions. The warning is the existing third-party `google.genai.types` deprecation warning.

## Remaining boundary

`LOCAL_AI` is now classified safely and no longer incorrectly blocked by LILITH availability. Its real local text provider, health/model checks and connectivity registry belong to AUT-02 and are the exact next block.
