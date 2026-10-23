# BLOCK 03 — OLLAMA, FALLBACK LOCAL & ROUTER AUDIT

**Date**: 2026-10-15
**Auditor**: Claude Opus 4.6

---

## 1. Objetivo

Auditar completamente los subsistemas de: Ollama (deteccion de instalacion, modelo default, fallback Gemini→Ollama, prompt seguro, timeout, errores, respuesta vacia, modelo no disponible), Fallback Local (deteccion de conexion, modo offline, que funciona sin internet, que falla, mensajes de error, recovery), y Router (classifier completo, todos los dominios, handler mapping, confianza, ambiguedad, fallback, passthrough a Gemini, errores).

## 2. Estado inicial

- **808 passed, 0 failed, 84 skipped** en la suite tras Block 2
- Tests previos en `test_screen_processor.py` ya cubrian `_local_vision_answer` y `_request_ollama_vision_answer` (22+ tests)
- Tests previos en `test_block1_windows_files_browser.py` cubrian clasificador basico del router (20+ tests)
- Sin tests para: vision_model.py config, schedule_safety.py, router/core.py handlers, _parse_home_command, _home_error_message

## 3. Archivos inspeccionados

| Archivo | Lineas |
|---------|--------|
| `core/vision_model.py` | 112 |
| `core/schedule_safety.py` | 104 |
| `router/core.py` | 255 |
| `router/classifier.py` | 114 |
| `router/models.py` | 34 |
| `actions/screen_processor.py` | ~370 (secciones Ollama) |
| `lilith_client/errors.py` | ~20 (header) |
| `tests/test_screen_processor.py` | 427 |

## 4. Funciones existentes

### A — OLLAMA (`core/vision_model.py`, `actions/screen_processor.py`)

| Funcion | Estado |
|---------|--------|
| DEFAULT_VISION_MODEL ("gemini-3.8-flash") | IMPLEMENTED |
| DEFAULT_VISION_FALLBACK_MODEL ("gemini-3.6-flash") | IMPLEMENTED |
| DEFAULT_OLLAMA_VISION_MODEL ("qwen3-vl:4b-instruct") | IMPLEMENTED |
| `configured_vision_model()` env → config → default | IMPLEMENTED |
| `configured_vision_fallback_model()` env → config → default | IMPLEMENTED |
| `configured_ollama_vision()` env → config → defaults | IMPLEMENTED |
| OllamaVisionConfig dataclass (enabled, url, model, timeouts) | IMPLEMENTED |
| `_local_ollama_url()` loopback-only validation | IMPLEMENTED |
| `_enabled()` boolean parsing (true/false/yes/no/on/off/1/0) | IMPLEMENTED |
| Trailing slash stripping on URL | IMPLEMENTED |
| Remote URL rejection (non-loopback) | IMPLEMENTED |
| Credentialed URL rejection (user:pass@) | IMPLEMENTED |
| `_request_ollama_vision_answer()` POST to /api/chat | IMPLEMENTED |
| `_local_vision_answer()` Gemini fail → Ollama fallback | IMPLEMENTED |
| Strict vision prompt (describe only what visible) | IMPLEMENTED |
| Connection timeout / read timeout | IMPLEMENTED |
| Empty response handling | IMPLEMENTED |
| Model unavailable error | IMPLEMENTED |
| Ollama auto-detection (no install check) | NOT IMPLEMENTED |

### B — FALLBACK LOCAL (sin modulo dedicado)

| Funcion | Estado |
|---------|--------|
| Ollama as Gemini vision fallback | IMPLEMENTED |
| Router LILITH offline detection | IMPLEMENTED |
| Offline error messages (per domain) | IMPLEMENTED |
| Full offline mode (sin internet) | NOT IMPLEMENTED |
| Connection status detection | NOT IMPLEMENTED |
| Auto-recovery when internet returns | NOT IMPLEMENTED |
| Offline-capable features list | NOT IMPLEMENTED |
| Fallback for text generation (no Gemini) | NOT IMPLEMENTED |

### C — ROUTER (`router/core.py`, `router/classifier.py`)

| Funcion | Estado |
|---------|--------|
| classify() regex-based 10 domains | IMPLEMENTED |
| WINDOWS domain (regex) | IMPLEMENTED |
| FILES domain (regex) | IMPLEMENTED |
| VISION domain (regex) | IMPLEMENTED |
| MEMORY domain (regex) | IMPLEMENTED |
| HOME domain (regex) | IMPLEMENTED |
| DEVELOPMENT domain (regex) | IMPLEMENTED |
| KNOWLEDGE domain (regex) | IMPLEMENTED |
| LOCAL_AI domain (regex) | IMPLEMENTED |
| WEB domain (regex) | IMPLEMENTED |
| CONVERSATION fallback (0.3 confidence) | IMPLEMENTED |
| Ambiguity detection (0.1 confidence gap) | IMPLEMENTED |
| raw_input preservation in params | IMPLEMENTED |
| JarvisRouter.execute() dispatch | IMPLEMENTED |
| LILITH offline guard (requires_lilith) | IMPLEMENTED |
| _handle_memory() store/search | IMPLEMENTED |
| _handle_home() with schedule_semantics guard | IMPLEMENTED |
| _parse_home_command() on/off + filler removal | IMPLEMENTED |
| LILITH entity resolution (ambiguous/unknown/not_allowed) | IMPLEMENTED |
| Home state confirmation polling | IMPLEMENTED |
| _home_error_message() per error code | IMPLEMENTED |
| _handle_conversation() stub | IMPLEMENTED |
| _handle_gemini_passthrough() for 6 domains | IMPLEMENTED |
| _handle_not_implemented() for LOCAL_AI | IMPLEMENTED |
| schedule_semantics() immediate/one_shot/recurring | IMPLEMENTED |
| daily_time_from_text() 24h/AM-PM/Spanish words | IMPLEMENTED |
| normalized_turn_text() accent + whitespace | IMPLEMENTED |
| normalize_timezone() aliases + IANA validation | IMPLEMENTED |
| GMAIL domain | NOT IMPLEMENTED (classifier) |
| MULTIMEDIA domain | NOT IMPLEMENTED (classifier) |
| REMINDERS domain | NOT IMPLEMENTED (classifier) |
| PRESENTATIONS domain | NOT IMPLEMENTED (classifier) |

## 5. Problemas encontrados

### Observaciones (sin bugs criticos)

1. **No hay deteccion de instalacion de Ollama**
   - El sistema asume que Ollama esta disponible si `OLLAMA_VISION_ENABLED` no es "false"
   - No verifica que el proceso Ollama este corriendo antes de enviar requests
   - Impacto: timeout silencioso si Ollama no esta instalado/corriendo

2. **No hay modo offline completo**
   - JARVIS no tiene un modulo dedicado de deteccion de conectividad
   - Sin internet: Gemini falla, Ollama vision funciona localmente, router HOME/MEMORY fallan por LILITH
   - No hay fallback para generacion de texto sin Gemini
   - No hay auto-recovery cuando la conexion se restaura

3. **Router classifier carece de dominios para Gmail, multimedia, recordatorios, presentaciones**
   - Estas peticiones caen a CONVERSATION fallback (confidence 0.3)
   - Gemini las procesa via function calling, que funciona pero pierde contexto del classifier
   - Documentado tambien en Block 1 y Block 2

4. **LOCAL_AI handler devuelve "no implementado"**
   - El clasificador detecta peticiones de IA local (Ollama text), pero el handler no hace nada
   - La vision por Ollama funciona como fallback en screen_processor, no via el router

5. **schedule_semantics guard solo en HOME**
   - El guard que bloquea peticiones programadas se aplica solo al dominio HOME
   - Recordatorios van por CONVERSATION → Gemini, sin pasar por este guard
   - No es un bug (recordatorios tienen su propio modulo), pero es una asimetria

6. **daily_time_from_text() "a las 5" es ambiguo**
   - Sin AM/PM ni "de la manana/tarde", devuelve None
   - Correcto como safety measure pero limita usabilidad

## 6. Cambios realizados

Ningun cambio en codigo de produccion — no se encontraron bugs que rompan funcionalidad existente.

## 7. Tests anadidos

| Archivo | Tests |
|---------|-------|
| `tests/test_block3_ollama_router.py` | **59 tests** |

Cobertura:

**Vision Model Config (17 tests):**
- `TestVisionModelConfig` (6 tests): defaults, config override, env override, missing config
- `TestOllamaVisionConfig` (7 tests): defaults, disabled, remote URL rejected, credentialed URL rejected, custom URL/model, trailing slash, _enabled() parsing
- `TestFallbackModelConfig` (2 tests): default, env override

**Schedule Safety (15 tests):**
- `TestScheduleSemantics` (6 tests): immediate, recurring Spanish/English, one_shot Spanish/English, ISO date
- `TestDailyTimeFromText` (5 tests): 24h, AM/PM, spoken Spanish, ambiguous, no time
- `TestNormalizedTurnText` (2 tests): accents, whitespace
- `TestNormalizeTimezone` (4 tests): default Madrid, local aliases, valid IANA, invalid

**Router Classifier (11 tests):**
- `TestClassifierEdgeCases` (11 tests): empty fallback, mixed language, all 10 domains, raw_input preserved

**Router Core (16 tests):**
- `TestParseHomeCommand` (4 tests): turn_on, turn_off, no command, filler removal
- `TestRouterHandlers` (9 tests): classify, conversation, passthrough, local_ai not implemented, LILITH offline, memory store/search, home scheduled blocked, home no entity
- `TestHomeErrorMessage` (3 tests): denied code, entity not found, unknown code

## 8. Tests ejecutados

```
python -m pytest tests/test_block3_ollama_router.py --tb=short -q
```

## 9. Resultado

| Metrica | Valor |
|---------|-------|
| Passed | 59 |
| Failed | 0 |
| Skipped | 0 |
| Warnings | 0 |

Suite global despues de cambios:

| Metrica | Valor |
|---------|-------|
| Passed | 867 |
| Failed | 0 |
| Skipped | 84 |
| Warnings | 1 |

## 10. Pruebas fisicas pendientes

| ID | Area | Prueba | Estado |
|----|------|--------|--------|
| PHY-B3-001 | Ollama | Instalar Ollama y verificar que el modelo qwen3-vl:4b-instruct descarga | PHYSICAL TEST REQUIRED |
| PHY-B3-002 | Ollama | Enviar imagen a Ollama vision y verificar respuesta coherente | PHYSICAL TEST REQUIRED |
| PHY-B3-003 | Ollama | Desconectar Gemini y verificar fallback a Ollama vision | PHYSICAL TEST REQUIRED |
| PHY-B3-004 | Ollama | Apagar Ollama y verificar error/timeout correcto | PHYSICAL TEST REQUIRED |
| PHY-B3-005 | Ollama | Verificar que Ollama rechaza URL remota en runtime | PHYSICAL TEST REQUIRED |
| PHY-B3-006 | Fallback | Desconectar internet y verificar que Ollama vision sigue funcionando | PHYSICAL TEST REQUIRED |
| PHY-B3-007 | Fallback | Verificar mensajes de error cuando LILITH no esta disponible | PHYSICAL TEST REQUIRED |
| PHY-B3-008 | Fallback | Reconectar internet y verificar que Gemini se recupera | PHYSICAL TEST REQUIRED |
| PHY-B3-009 | Router | Verificar que "enciende la luz" llega a Home Assistant via LILITH | PHYSICAL TEST REQUIRED |
| PHY-B3-010 | Router | Verificar que "recuerda que..." almacena en LILITH | PHYSICAL TEST REQUIRED |
| PHY-B3-011 | Router | Verificar clasificador con entradas ambiguas reales | PHYSICAL TEST REQUIRED |
| PHY-B3-012 | Router | Verificar passthrough a Gemini con "abre Chrome" | PHYSICAL TEST REQUIRED |

## 11. Riesgos o deuda tecnica

1. **Sin deteccion de Ollama** — el sistema no verifica si Ollama esta instalado/corriendo, causando timeouts silenciosos si no lo esta
2. **Sin modo offline completo** — no hay fallback para texto (solo vision tiene Ollama fallback), no hay deteccion de conectividad, no hay auto-recovery
3. **LOCAL_AI handler vacio** — el clasificador detecta peticiones pero el handler no hace nada; la funcionalidad real de Ollama vision esta en screen_processor, no en el router
4. **4 dominios sin clasificador** — Gmail, Multimedia, Reminders, Presentations dependen del fallback CONVERSATION → Gemini
5. **schedule_semantics solo en HOME** — asimetria en la proteccion contra peticiones programadas
6. **daily_time_from_text conservador** — "a las 5" sin contexto devuelve None, limitando la UX en espanol informal

## 12. Archivos modificados

- `tests/test_block3_ollama_router.py` (NUEVO — 59 tests)

Ningun archivo de produccion fue modificado.

## 13. Git

Pendiente de commit al finalizar todos los bloques.
