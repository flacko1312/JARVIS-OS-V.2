# WORKLOG — Registro cronológico de trabajo

---

## 2026-11-05 — AUTOPILOT: E41 alarmas de reloj

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### E41 — alarm_control (Alarmas de reloj)
- `actions/alarm_control.py`: scheduling por hora de reloj (HH:MM, mañana, AM/PM), threading.Timer, beep via ffplay (3 pitidos 880Hz), TTS al disparar, persistencia JSON, cancelación por ID
- Upgrade de PARCIAL (reminder) + añade herramienta dedicada con sonido
- `tests/test_alarm_control.py`: 31 tests → **31/31 PASS** (AURORA + Ubuntu headless)
- Desplegado en ambos entornos

---

## 2026-11-05 — AUTOPILOT: E50 noticias

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### E50 — news_control (Noticias RSS)
- `actions/news_control.py`: 9 feeds RSS curados (RTVE, El País, El Mundo, BBC, Reuters, Xataka, Marca, Hacker News), RSS 2.0 parser, headlines numerados + resumen de voz, sin clave API
- Upgrade de PARCIAL (web_search genérico) a OPERATIVO con herramienta dedicada
- `tests/test_news_control.py`: 28 tests → **28/28 PASS** (AURORA + Ubuntu headless)
- Desplegado en ambos entornos

---

## 2026-11-05 — AUTOPILOT: E46 listas de la compra

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### E46 — shopping_list (Listas de la compra)
- `actions/shopping_list.py`: JSON persistence local (`~/.jarvis/lists/`), multi-lista, CRUD completo (add/remove/check/uncheck/list/clear/lists), sin dependencias externas
- Upgrade de PARCIAL (lilith_memory_store) a OPERATIVO con herramienta dedicada
- `tests/test_shopping_list.py`: 35 tests → **35/35 PASS** (AURORA + Ubuntu headless)
- Desplegado en ambos entornos

---

## 2026-11-05 — AUTOPILOT: C30 audiolibros

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### C30 — audiobook_control (Audiolibros LibriVox)
- `actions/audiobook_control.py`: LibriVox API pública (sin clave), búsqueda por título/autor con fallback, listado de capítulos, streaming ffplay, fallback os.startfile/xdg-open
- `tests/test_audiobook_control.py`: 31 tests → **31/31 PASS** (AURORA + Ubuntu headless)
- Desplegado y registrado en AURORA (`main.py` + `core/qa_audit.py`) y Ubuntu headless
- **Blocker:** validación física (altavoces)

---

## 2026-11-05 — AUTOPILOT: C28 radio, C29 podcasts, D38 broadcast

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### C28 — radio_control (Internet Radio)
- `actions/radio_control.py`: 10 emisoras builtin (RTVE R1/R2/R3, SER, COPE, Onda Cero, Los40, Rock FM, BBC R1/R6), registry JSON en `~/.jarvis/radio/`, streaming via ffplay, fallback os.startfile/xdg-open
- `tests/test_radio_control.py`: 31 tests → **76/76 PASS** (AURORA + Ubuntu headless)
- Desplegado y registrado en AURORA (`main.py` + `core/qa_audit.py`) y Ubuntu headless
- **Blocker:** validación física (altavoces)

### C29 — podcast_control (Podcasts)
- `actions/podcast_control.py`: iTunes Search API (sin clave), RSS parser con namespace `itunes:`, ffplay streaming, episodios recientes
- `tests/test_podcast_control.py`: 26 tests → **76/76 PASS** (AURORA + Ubuntu headless)
- Desplegado en ambos entornos

### D38 — broadcast_control (TTS Broadcast)
- `actions/broadcast_control.py`: player.speak → tts_engine.speak → espeak-ng subprocess; relay LILITH best-effort POST `/api/broadcast`
- `tests/test_broadcast_control.py`: 19 tests → **76/76 PASS** (AURORA + Ubuntu headless)
- LILITH relay silencia errores (LILITH actualmente inactive); no bloquea anuncio local

### Fix cross-plataforma
- `tests/test_radio_control.py` + `tests/test_podcast_control.py`: `patch("os.startfile", create=True)` + mock `subprocess.Popen` para compatibilidad Linux (os.startfile no existe en Ubuntu)

---

## 2026-11-05 — Sesión inicial: Auditoría AURORA + creación sistema de seguimiento

**Autor:** Claude Sonnet 4.6 (automatizado)
**Duración:** Sesión completa
**Rama:** `codex/neural-voice-visual`

### Trabajo realizado

#### Auditoría AURORA/JARVIS Windows
- Leídos y analizados: `docs/ARQUITECTURA_ROLES_AURORA_JARVIS_UBUNTU_LILITH_2026-11-04.md`, `docs/PROJECT_STATE.md`, `docs/JARVIS_CAPABILITIES.md`, `docs/AURORA_CLOSURE_AUDIT.md`, `docs/TASKS.md`, `docs/LILITH_INTEGRATION.md`
- Verificada estructura de directorios completa de `C:\JARVIS`
- Auditado commit más reciente: `37b3b35` (WebSocket adapter Phase 2)
- Inventariados 49 tools, 28 action modules, estado de subsistemas
- Estado AURORA confirmado: 1463 passed, 93 skipped, 0 failures
- Estado LILITH HTTP client: JL-W001–W006 completos
- Identificadas capacidades AUSENTES: timer (E42), calendario (E44-45), tráfico (E49)
- Identificadas capacidades PARCIALES: WebSocket adapter (G68, feature-flagged)

#### Creación de docs/NEST_68_AUTOPILOT/
- Creada carpeta: `docs/NEST_68_AUTOPILOT/`
- Creado: `MASTER_PLAN.md` — mapa completo de 68 capacidades con estados por componente
- Creado: `STATUS.json` — estado estructurado JSON de todas las capacidades
- Creado: `HANDOFF.md` — instrucciones exactas de reanudación
- Creado: `BLOCKERS.md` — hardware, credenciales y bloqueos
- Creado: `WORKLOG.md` (este archivo)
- Pendiente: `TEST_RESULTS.md`, `PHYSICAL_TESTS.md` (crear en siguiente sesión)

### Estado al final de sesión
- Fase 0 (auditoría AURORA): **COMPLETA**
- Fase 0 (Ubuntu/LILITH/HA): **PENDIENTE** — requiere SSH
- Próxima tarea: implementar tool `timer` (tarea inmediata más segura sin dependencias remotas)

### Implementación: timer tool (E42)
- Creado: `actions/timer.py` — temporizador in-process con threading.Timer, registry JSON persistente
- Modificado: `main.py` — añadido _lazy_action, schema, dispatch para tool "timer"
- Modificado: `core/qa_audit.py` — añadido "timer" a EXPECTED_TOOLS
- Creado: `tests/test_timer.py` — 36 tests (parseo, formato, create/list/cancel, callback, registry)
- Corregido: `tests/test_conversation_persistence.py` — mock LilithBridge.from_env para evitar timeout flaky cuando LILITH está disponible
- Suite completa: **1499 passed, 0 failures, 93 skipped**

### Cambios en repositorio
- Nuevos archivos en `docs/NEST_68_AUTOPILOT/` 
- Nuevos archivos: `actions/timer.py`, `tests/test_timer.py`
- Modificados: `main.py`, `core/qa_audit.py`, `tests/test_conversation_persistence.py`
- Pendiente de commit

---

## 2026-11-05 — Integración Google Calendar (E44/E45)

**Autor:** Claude Sonnet 4.6 (automatizado)
**Rama:** `codex/neural-voice-visual`

### Trabajo realizado

#### Implementación: calendar_control tool (E44, E45)
- Creado: `actions/calendar_control.py` — integración Google Calendar API v3 con OAuth2
  - Acciones: connect, disconnect, status, list, today, search, create, delete
  - Patrón OAuth idéntico a `email_control.py`: credenciales en OS keychain via `core.secret_store`
  - Búsqueda de archivo de credenciales en env GCAL_OAUTH_CLIENT_FILE, keychain, config/, Downloads/
  - Fallback gracioso si OAuth no configurado (mensaje instructivo, no excepción)
  - Formato de eventos en español con hora local (Europe/Madrid por defecto)
  - Acciones create con validación de fecha/hora, duration_minutes, location, description
- Modificado: `main.py` — añadido _lazy_action, schema (13 parámetros), dispatch para "calendar_control"
- Modificado: `main.py` — añadido "calendar_control" a _MUTATING_TOOL_NAMES
- Modificado: `core/qa_audit.py` — añadido "calendar_control" a EXPECTED_TOOLS
- Creado: `tests/test_calendar_control.py` — 42 tests (5 clases: ValidClientFile, FmtEvent, Status, List, Today, Search, Create, Delete, EntryPoint)

### Tests ejecutados
- `test_calendar_control.py`: **42/42 passed**
- Regresiones: ninguna en módulos que cargan sin google-api (pre-existing failures sin cambio)

### Estado al final
- E44 (calendario): **PARCIAL** — código funcional, blocker OAuth credenciales del usuario
- E45 (citas): **PARCIAL** — cubierto por calendar_control create/search

### Cambios
- Nuevos archivos: `actions/calendar_control.py`, `tests/test_calendar_control.py`
- Modificados: `main.py`, `core/qa_audit.py`, `docs/NEST_68_AUTOPILOT/STATUS.json`, `docs/NEST_68_AUTOPILOT/WORKLOG.md`

---

## 2026-11-05 — Integración tráfico (E49)

**Autor:** Claude Sonnet 4.6 (automatizado)
**Rama:** `codex/neural-voice-visual`

### Trabajo realizado

#### Implementación: traffic_info tool (E49)
- Creado: `actions/traffic_info.py` — routing e info de tráfico via OpenRouteService + Nominatim
  - Geocodificación libre con Nominatim (OSM) — sin API key
  - Routing con OpenRouteService v2 (free tier, requiere ORS_API_KEY)
  - Acciones: route (origen→destino), commute (casa↔trabajo), setup, addresses, status
  - Fallback gracioso con instrucciones de setup si no hay API key
  - Alias: "from"/"to" como "origin"/"destination", "trayecto" como "commute"
  - Guardado de casa/trabajo en keychain via secret_store
- Modificado: `main.py` — añadido _lazy_action, schema (7 parámetros), dispatch para "traffic_info"
- Modificado: `main.py` — añadido "traffic_info" a _MUTATING_TOOL_NAMES
- Modificado: `core/qa_audit.py` — añadido "traffic_info" a EXPECTED_TOOLS
- Creado: `tests/test_traffic_info.py` — 45 tests (FmtDuration, FmtDistance, Geocode, OrsRoute, Status, Setup, Addresses, Route, Commute, EntryPoint)

### Tests ejecutados
- `test_traffic_info.py`: **45/45 passed**
- `test_calendar_control.py`: **42/42 passed** (sin regresiones)

### Estado al final
- E49 (tráfico): **PARCIAL** — código funcional, blocker ORS_API_KEY del usuario (gratuita en openrouteservice.org)

### Cambios
- Nuevos archivos: `actions/traffic_info.py`, `tests/test_traffic_info.py`
- Modificados: `main.py`, `core/qa_audit.py`, `docs/NEST_68_AUTOPILOT/STATUS.json`, `docs/NEST_68_AUTOPILOT/WORKLOG.md`

---

## Plantilla para próximas entradas

```
## YYYY-MM-DD — Descripción breve

**Autor:** Claude Sonnet 4.6 / [nombre]
**Rama:** [rama]

### Trabajo realizado
- ...

### Tests ejecutados
- ...

### Estado al final
- ...

### Cambios
- ...
```
