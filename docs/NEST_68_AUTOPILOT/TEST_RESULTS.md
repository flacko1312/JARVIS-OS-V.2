# TEST_RESULTS — Pruebas ejecutadas y resultados

---

## Baseline AURORA — 2026-11-05

**Fuente:** `docs/AURORA_CLOSURE_AUDIT.md` y commit `37b3b35`

| Suite | Passed | Skipped | Failed | Notas |
|---|---|---|---|---|
| pytest completo (commit 37b3b35) | 1463 | 93 | 0 | Incluye 29 tests adapter_connector |
| pytest completo (commit 4e2d890, closure audit) | 1360 | 93 | 0 | Baseline pre-WebSocket |
| Suite reconexión/continuidad/dispositivos | 260 | 0 | 0 | Validación silenciosa 2026-10-23 |
| `python -m compileall` | PASS | — | — | |
| `pip check` | PASS | — | — | Sin dependencias rotas |
| ESLint (web/) | PASS | — | — | |
| TypeScript tsc --noEmit | PASS | — | — | |
| Next.js production build | PASS | — | — | |

**Tests de seguridad (desktop.py exec sandbox):** 74 tests en `tests/test_desktop_exec_security.py` — PASS

---

## Validaciones físicas completadas (humano)

| Test | Fecha | Resultado | Notas |
|---|---|---|---|
| JL-A10: rutinas habladas (lilith_routine create/list/delete) | 2026-10-08 | PASS | "10 de la noche" → 22:00 Europe/Madrid |
| Captura de pantalla + análisis Gemini | 2026-10-23 | PASS | 142KB imagen, gemini-3.8-flash correcto |
| F8 pausa/reanuda continuidad | 2026-10-23 | PASS | 88 → pausa → reanuda → "176" correcto |
| Reinicio proceso + continuidad | 2026-10-23 | PASS | Sin saludo, contexto restaurado |
| VAD 2500ms timing natural | 2026-10-23 | PASS | Sin cortes prematuros |
| Supresión petición repetida | 2026-10-23 | PASS | Sin duplicados |

---

## Tests pendientes de ejecución (NEST 68)

Los siguientes tests deben ejecutarse a medida que se implementen nuevas capacidades:

| Capacidad | Test a crear | Estado |
|---|---|---|
| Timer (E42) | `tests/test_timer.py` | PENDIENTE — tool no implementado |
| Calendario (E44-45) | `tests/test_calendar_control.py` | PENDIENTE |
| Tráfico (E49) | `tests/test_traffic_info.py` | PENDIENTE |
| WebSocket adapter habilitado | `tests/test_adapter_integration.py` | PENDIENTE — feature-flagged |

---

## Tests de integración pendientes (todo el ecosistema)

| Test | Prerequisito |
|---|---|
| AURORA ↔ LILITH HTTP round-trip real | LILITH accesible en red |
| AURORA ↔ LILITH WebSocket handshake | LILITH WS server + ADAPTER_CONNECTION_ENABLED=true |
| LILITH → HA: control dispositivo real | SSH Ubuntu + HA accesible |
| Ubuntu: Gemini Live STT/TTS | SSH Ubuntu + hardware audio |
| Ubuntu: activación por palabra clave | SSH Ubuntu + hardware micrófono |
| Rutina creada desde AURORA → ejecutada en Ubuntu | Ecosistema completo |
