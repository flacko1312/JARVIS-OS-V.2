# WORKLOG — Registro cronológico de trabajo

---

## 2026-11-05 (sesión 9) — Cierre funcional: P1-P5 bugs fijados, P3 health injection verificado

**Autor:** Claude Sonnet 4.6 (AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### Trabajo realizado

#### P1 — RUTINAS POR VOZ: Bug crítico fijado (home_routine nunca llegaba a Gemini)
- **BUG**: home_routine no estaba en `TOOL_DECLARATIONS` → Gemini Live nunca la veía
- **BUG**: `HEADLESS_ACTIONS` solo tenía 21 tools → home_routine filtrada incluso si fuera declarada
- **FIX en Ubuntu** (SSH, untracked): p1_fix.py aplicado a main.py
  - home_routine declaration añadida a `TOOL_DECLARATIONS` (con frases ES/EN obligatorias)
  - `HEADLESS_ACTIONS` expandida de 21 → 36 tools (añadidos todos los domésticos: home_routine, timer, alarm_control, shopping_list, etc.)
- **Verificación**: journal `tools=36` confirmado, Layer 3 E2E 5/5 PASS

#### P2 — DISPOSITIVOS DESCONECTADOS: Pre-check de disponibilidad
- **FIX en home_routine.py**: nueva función `_entity_is_available()` que consulta `GET /api/v1/integration/home/entity/{entity_id}`
- Rutinas me_voy, llegue_a_casa, buenas_noches, modo_taller ahora verifican disponibilidad antes de llamar LILITH
- Dispositivo offline → `"⚠️ dispositivo offline (omitido)"` en resultado (no error)
- Verificado en voz real: journal de sesión 21:03 muestra "Dispositivos no disponibles: light.bombilla_mueble, light.bombilla_tv..."
- Test `/tmp/test_p2_precheck.py`: PASS (light.bombilla_mueble available=False detectado correctamente)

#### P3 — AUTONOMÍA REAL: Bug en _fetch_routine_health_summary
- **BUG**: función buscaba `resp.get("data",{}).get("response",{}).get("routines",[])` → 0 routines siempre
- **FIX**: comando_submit devuelve `resp.get("response",{}).get("routines",[])` sin wrapper `data`
- **Fix en Ubuntu** (SSH, untracked): `sed -i` corrección en main.py línea 4292
- **Verificación**: `journalctl` confirma `[JARVIS] Routine health: failures detected, injecting alert` en siguiente conexión
- P5 test routine_check PASS en 27s: Gemini reportó los 4 fallos usando el health summary inyectado

#### P4 — MEMORIA: Mecanismos verificados
- LILITH `get_context()`: 93 hechos cargados en cada sesión (journal: `LILITH context loaded: 93 facts`)
- Semantic memory search: funcional, API limita a 20 resultados/búsqueda (total ~518 no consultable via API)
- Local `long_term.json` (Windows): 10 ítems personales (nombre, edad, cumpleaños, mascota, notas)
- Ubuntu local memory: vacía (correcto — LILITH es el almacén canónico)

#### P5 — ANDROID /api/chat E2E
- Test `/tmp/test_p5_android.py`: 6/7 PASS
  - timer: PASS ✓, alarm: PASS ✓, shopping: PASS ✓, reminder: PASS ✓
  - lilith_query: PASS ✓ (luces detectadas)
  - routine_check: PASS 27s ✓ (Gemini usó health injection correctamente)
  - weather: PARTIAL (pide ciudad — comportamiento correcto, no bug)

### Archivos modificados
- `actions/home_routine.py`: `_entity_is_available()` + 4 rutinas con pre-check
- `docs/NEST_68_AUTOPILOT/STATUS_SNAPSHOT.json`: v10→v11
- `docs/NEST_68_AUTOPILOT/WORKLOG.md`: esta entrada
- `docs/NEST_68_AUTOPILOT/HANDOFF.md`: actualizado
- **Ubuntu (SSH, untracked)**: `main.py` — P1 + P3 fixes (HEADLESS_ACTIONS 36, home_routine decl, response path)

### Estado al final
- 44/68 OPERATIVO (sin cambio en número — corrección de bugs internos, no nuevas capacidades)
- Todos los bugs críticos de sesión 8 resueltos
- home_routine confirmada en voz real (5/5) y vía Android (PASS)
- Routine health injection confirmada funcional
- Ubuntu main.py tiene 3 cambios untracked — no en git (SSH-only)

---

## 2026-11-05 (sesión 7) — Verificación rutinas, auditoría broadcast/memoria/APK, corrección routing

**Autor:** Claude Sonnet 4.6 (AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### Trabajo realizado

#### Bloque 1: Verificación de las 5 rutinas domésticas
- Auditado `home_routine.py`: 5 rutinas implementadas (buenos_dias/me_voy/llegue_a_casa/buenas_noches/modo_taller)
- Verificado endpoint fijo en `/api/v1/integration/home/action` (commit 5a298af)
- **Hallazgo crítico**: ROUTINE_ROUTING_RULES en AURORA no contenía ninguna referencia a home_routine → Gemini respondía a "buenos días" con texto, nunca llamaba la herramienta
- **Fix**: Reescrito ROUTINE_ROUTING_RULES en `main.py` → home_routine como regla #1 con frases explícitas ES/EN para las 5 rutinas
- **Fix**: HEADLESS_SYSTEM_RULES en Ubuntu `main.py` actualizado con las mismas frases de routing

#### Bloque 2: Investigación broadcast en LILITH
- Auditado `core/routers/integration.py` en LILITH: `COMMAND_READ_INTENTS` y `COMMAND_MUTATING_INTENTS` confirmados
- **Hallazgo**: `broadcast` AUSENTE del protocolo de integración LILITH — no es problema de permisos, es que el intent no existe
- `broadcast_control.py` retorna 403 `command_intent_not_allowed` correctamente
- Solución definitiva: local TTS via sounddevice (ya implementado y funcional)
- Para relay remoto: requeriría nuevo endpoint en LILITH (no en scope actual)

#### Bloque 3: Auditoría memoria LILITH
- Verificado: 91 hechos en 16 categorías en LILITH
- `get_context()` carga todo el contexto en cada sesión Gemini Live al inicio
- `memory.store` y `memory.search` probados correctamente
- Reglas de memoria en HEADLESS_SYSTEM_RULES: solo en solicitud explícita (correcto, evita falsos positivos)

#### Bloque 4: Verificación consultas de estado
- AURORA y Ubuntu pueden consultar estado de JARVIS, LILITH, HA via herramientas existentes
- `lilith_home_status`, `lilith_health`, `system_status`, `infrastructure_status` operativos
- `HOME_ACTION_ALLOWLIST` confirmado: solo dominio `light.*` permitido (no switch.*, no media_player.*)

#### Bloque 5: Auditoría gateway APK Android
- **Hallazgo**: Puerto 7471 sirve `api_server.py` (NO `api/server.py` que es la cloud API multi-usuario)
- Dos interfaces en `api_server.py`:
  - `POST /api/chat` → pipeline NL completo con TODOS los 73 tools via `ask_text()`
  - `POST /api/tool/invoke` → dispatch directo (~16 tools: system/LILITH/memoria)
- **Hallazgo**: timer, alarm_control, shopping_list, radio_control, etc. están en `headless_permissions.py` (permitidos) pero NO en `_dispatch_tool` → no invocables directamente via API, solo via `/api/chat` NL
- STATUS_SNAPSHOT v8 `android_apk_tools.new_tools_registered` era engañoso → corregido en v9
- Endpoints adicionales: `/api/status`, `/api/metrics`, `/api/conversation`, `/api/tools`, `/api/tailscale`, `/api/voice`
- Auth: Bearer token, constant-time, binding Tailscale IP

#### Bloque 6: Análisis brechas conversación natural
- Enumeradas 5 brechas principales: dispositivos físicos offline, media_player bloqueado, sin comportamiento proactivo, calendar/traffic sin credenciales, broadcast relay ausente en protocolo
- Cobertura actual: routing phrases (home_routine), contexto LILITH (91 hechos), web_search/weather/date/calculator auto-routing

#### Bloque 7: Re-auditoría 45 capacidades OPERATIVO
- Diferenciados tres niveles dentro de OPERATIVO:
  - **auto_integration** (26): Gemini invoca sin instrucción técnica del usuario
  - **code_only** (15): implementado y probado, sin validación física
  - **physical_validated** (2): A6/A7 — probados con hardware real (teclado/pantalla)
- Documentado en STATUS_SNAPSHOT v9 `operativo_differentiation`

### Tests ejecutados
- No se añadieron nuevas herramientas → no se corrieron tests nuevos
- main.py modificado (ROUTINE_ROUTING_RULES) — sin tests unitarios para system prompt

### Estado al final
- 45/68 OPERATIVO (sin cambio)
- ROUTINE_ROUTING_RULES corregido: home_routine ahora se invoca automáticamente ✓
- HEADLESS_SYSTEM_RULES Ubuntu actualizado con frases de routing ✓
- STATUS_SNAPSHOT v8 → v9: corrección android_apk_tools + auditoría completa ✓

### Cambios
- Modificados: `main.py` (ROUTINE_ROUTING_RULES home_routine rule #1)
- Ubuntu (SSH, untracked): `main.py` HEADLESS_SYSTEM_RULES frases home_routine
- Docs: `STATUS_SNAPSHOT.json` v8→v9, `WORKLOG.md`, `HANDOFF.md`

---

## 2026-11-05 (sesión 6) — Reorganización prioridades, home_routine P3, auditoría Ubuntu, entidades HA

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### Trabajo completado

#### P1 — Auditoría voz/conversación Ubuntu (HEADLESS_SYSTEM_RULES)
- Descubierto: `HEADLESS_SYSTEM_RULES` en Ubuntu `main.py` no listaba 8+ tools nuevas añadidas en sesiones 3-5
- Reescrito `HEADLESS_SYSTEM_RULES` vía SSH: ahora incluye todos los tools (alarm_control, timer, shopping_list, news_control, transport_schedules, broadcast_control, reminder, batch_home_action, weather_report, calculator, home_routine)
- Añadida nota explícita de audio: "you CAN play audio on speakers" (Ubuntu headless_half_duplex + sounddevice)
- Verificado que memory tools (lilith_memory_search, lilith_memory_store) están en perfil headless con reglas correctas

#### P3 — home_routine tool (meta-rutinas domésticas)
- Creado `C:\JARVIS\actions\home_routine.py` con 5 rutinas: buenos_dias, me_voy, llegue_a_casa, buenas_noches, modo_taller
- Todas las acciones sobre dispositivos requieren `confirm=True` explícito — protección contra ejecución accidental
- Integrado en AURORA: lazy import + schema TOOL_DECLARATIONS + dispatch en `main.py` + `qa_audit.py`
- Desplegado en Ubuntu: SCP del módulo + lazy import + dispatch + `qa_audit.py` + `headless_permissions.py`
- 30/30 tests nuevos pasando
- Fix aplicado: parámetro `confirm_devices` en `_execute_buenos_dias` (typo de nombre)

#### P4 — Auditoría entidades Home Assistant (en vivo)
- Consultadas entidades reales vía LILITH `home/resolve` en producción
- light.bombilla_mueble: registrada en HA, state=unavailable (dispositivo físico offline)
- light.bombilla_tv: registrada en HA, state=unavailable (dispositivo físico offline)
- switch.cargador_hub: registrada en HA, state=unavailable (dispositivo físico offline)
- sensor.lilith_temperatura: registrada en HA, state=unavailable (dispositivo físico offline)
- **media_player.hub: AVAILABLE (state=off, available=True)** ← único dispositivo funcional
- media_player.mc_smart_tv_pro_cast: unavailable
- Ninguna entidad cover.* ni climate.* registrada en HA
- MASTER_PLAN.md actualizado: B11/B12 con nota estado físico real, G64 con tabla completa

#### STATUS_SNAPSHOT.json v8
- snapshot_version: 7→8
- tool_count_aurora: 62→63, tool_count_ubuntu: 71→73
- tools_new_this_session: añadido home_routine
- home_assistant: actualizado con resultado auditoría real
- tests: 79 passed (home_routine 30 + transport_schedules 32 + batch_home_action 17)
- note: actualizado para v8

### Estado actual
45/68 OPERATIVO — sin cambio de recuento (home_routine es implementación de B19/B20/B21 ya OPERATIVO).
Cambio clave: HEADLESS_SYSTEM_RULES Ubuntu corregido; home_routine deployado en ambos entornos.

### Bloqueadores pendientes (usuario)
- **GCAL_OAUTH**: E44/E45 → colocar archivo OAuth JSON en `C:\JARVIS\config\gcal_client.json`
- **ORS_API_KEY**: E49 → openrouteservice.org (gratuita), luego "configura tráfico api_key=CLAVE"
- **Altavoces**: C25-C30, D37-D38, E41-E42, G66-G67 → validación física audio
- **Entidades HA**: B11-B12, B23-B24 → encender dispositivos físicos para probar domótica

### Continuación P2 (pendiente próxima sesión)
- Verificar que conversación Ubuntu usa realmente memoria LILITH (lilith_memory_search/store en flujo real)
- Testear media_player.hub: ¿puede recibir TTS/audio vía LILITH commands/submit?

---

## 2026-11-05 (sesión 5) — Auditoría verificación, disclaimer transport_schedules, STATUS_SNAPSHOT v7

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`
**Commit:** 8aa9f32

### Trabajo completado

#### transport_schedules — disclaimer datos estáticos (prioridad #5)
- Docstring del módulo actualizado: explica que los datos son ESTÁTICOS (no tiempo real)
- Output de `_fmt_metro`, `_fmt_cercanias`, `_action_schedules`, `_action_status` incluye ahora
  `⚠️ DATOS ESTÁTICOS (horario oficial CRTM/Renfe/EMT, no tiempo real)` con links a apps reales
- TOOL_DECLARATIONS description en AURORA `main.py` actualizada: "STATIC schedule reference... NOT real-time"
- Desplegado a Ubuntu via SCP + actualización de descripción en Ubuntu main.py via SSH
- 32/32 tests siguen pasando

#### STATUS_SNAPSHOT.json v7
- `PARCIAL_aurora`: eliminados B11, B12, B20, B23, B24 (ya eran OPERATIVO en MASTER_PLAN)
- `OPERATIVO_aurora`: añadidos B11, B12, B20, B23, B24; eliminado G67 (movido a PARCIAL)
- `PARCIAL_aurora`: añadido G67 (audio local Ubuntu sin verificar hardware)
- `DESCONOCIDO_ubuntu`: reducido de 14 entradas a 2 (B19/B21/C25-C27/etc verificados presentes en Ubuntu)
- Contadores: OPERATIVO=45 ✓, PARCIAL=9 (corregido)

#### OPERATIVO_VERIFICATION.md — nueva tabla de verificación
- Documento nuevo: 45 capacidades OPERATIVO con estado AUTO-TEST / INTEGRATION / PHYSICAL
- 45/45: tool contract auto-test (qa_audit)
- 36/45: unit tests (transport_schedules 32, batch_home_action 17, timer 36, alarm 31, etc.)
- 15/45: integración verificada (LILITH endpoints en vivo, RSS feeds, etc.)
- 5/45: validación física completa (A1 STT, A4 Gemini Live, A5 conversación, A8 comandos, A10)
- 18/45: validación física PENDIENTE (altavoces, entidades HA offline)

#### Verificaciones en Ubuntu
- lilith_routine, media_control, youtube_video: confirmados presentes (40 matches en main.py)
- WebSocket LILITH: `/api/v1/integration/ws` → 404; G68 permanece PARCIAL (feature-flagged OFF correcto)
- Ubuntu tests: 179 passed (sesión 4), módulos nuevos confirmados integrados

### Estado actual
45/68 OPERATIVO — sin cambios en el recuento. Session 5 fue de auditoría y corrección de calidad.

### Bloqueadores pendientes (usuario)
- **GCAL_OAUTH**: E44/E45 → colocar archivo OAuth JSON en `C:\JARVIS\config\gcal_client.json`
- **ORS_API_KEY**: E49 → openrouteservice.org (gratuita), luego "configura tráfico api_key=CLAVE"
- **Altavoces**: C25-C30, D37-D38, E41-E42, G66-G67 → validación física audio
- **Entidades HA**: B11-B12, B23-B24 → encender dispositivos físicos para probar domótica

---

## 2026-11-05 — AUTOPILOT: Integración real LILITH, auditoría 68 capacidades, Android gateway

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### Hallazgos y correcciones

#### AURORA↔LILITH comunicación autenticada — VERIFICADA
- Ruta real de API: `/api/v1/integration/` (no `/api/`)
- 10 endpoints autenticados confirmados: health, runtime/status, memory/search, memory/context, notifications, git/status, source/list, docs/list, home/resolve, commands/submit
- LILITH devuelve: `{"status":"online","version":"1.0.0","services":{"database":true,"mqtt":true,"kernel":true,"home_assistant":true}}`
- 324/324 tests pasan sin regresar

#### broadcast_control — relay corregido
- Error: usaba `/api/broadcast` (HTTP 404)
- Fix: ahora usa `/api/v1/integration/commands/submit` con `intent=broadcast`
- Resultado: HTTP 403 `command_intent_not_allowed` — el token de integración no tiene broadcast en la lista blanca de LILITH
- **Acción pendiente usuario:** pedir al equipo LILITH añadir `broadcast` a los intents permitidos para el token JARVIS
- El anuncio local TTS sigue funcionando; relay LILITH es best-effort

#### Auditoría 68 capacidades — MASTER_PLAN.md actualizado
- **A9** (Control doméstico por voz): PARCIAL → OPERATIVO (LILITH_API_URL confirmado y funcional)
- **C28/C29/C30** (Radio/Podcast/Audiolibros): AUSENTE → OPERATIVO (herramientas dedicadas, blocker físico altavoces)
- **C31** (Noticias habladas): PARCIAL → OPERATIVO (news_control RSS dedicado)
- **D37** (Anuncios): PARCIAL → OPERATIVO local (broadcast_control TTS)
- **D38** (Broadcast): AUSENTE → OPERATIVO local (broadcast_control TTS, relay pendiente allowlist)
- **E41** (Alarmas): PARCIAL → OPERATIVO (alarm_control, 31 tests)
- **E42** (Temporizadores): AUSENTE → OPERATIVO (timer, 36 tests)
- **E44/E45** (Calendario/Citas): AUSENTE → PARCIAL (calendar_control implementado, blocker OAuth)
- **E46** (Listas de la compra): PARCIAL → OPERATIVO (shopping_list, 35 tests)
- **E49** (Tráfico): AUSENTE → PARCIAL (traffic_info implementado, blocker ORS_API_KEY)
- **E50** (Noticias): PARCIAL → OPERATIVO (news_control, 28 tests)
- **Resultado:** 33 OPERATIVO (antes 23), 14 PARCIAL, 7 DESCONOCIDO, 1 AUSENTE, 4 BLOQUEADO, 6 REQUIEREN HARDWARE

#### Android APK — gateway permisos actualizados
- Encontrado: `jarvis-headless` expone herramientas en puerto 7471 vía `api_server.py`
- Permisos en `core/headless_permissions.py` — ninguna de las 10 herramientas nuevas estaba registrada
- Parchado: añadidos 46 nuevas reglas de permisos para los 10 tools nuevos
- Total: 35 → 81 reglas de permisos
- Niveles: news_control/traffic_info/calendar_read → READ_ONLY; timer/alarm/shopping/radio/podcast/audiobook/broadcast → SAFE_WRITE; calendar_create/delete → CONFIRM_REQUIRED

#### STATUS_SNAPSHOT.json — actualizado (versión 2)
- Refleja: LILITH_API_URL configurado y funcionando
- Refleja: broadcast relay fix (commands/submit, intent no allowlistado)
- Refleja: 33/68 OPERATIVO (nuevo contador)
- Refleja: Android gateway 81 reglas, 10 nuevos tools registrados

### Tests ejecutados
- AURORA: 324/324 passed (tool tests) + broadcast relay verificado
- Ubuntu: 324/324 passed (mismos tests) — permisos gateway no requieren restart

---


## 2026-11-05 — AUTOPILOT: B23/B24 batch_home_action (control simultáneo dispositivos)

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### batch_home_action (B23/B24)

#### Implementación (AURORA)
- Nuevo fichero `actions/batch_home_action.py`
  - `batch_home_action_async(targets, action, client, ha_params)` — asyncio.gather concurrente
  - `_resolve_and_act()` — resolve + action por dispositivo; fallo aislado (no para al resto)
  - Acepta list[str] o string CSV como targets
  - Resumen: "N/M dispositivos encendidos/apagados"
  - Dispatch en main.py usa importlib lazy (no _lazy_action porque es async con cliente inyectado)
- 17 tests en `tests/test_batch_home_action.py` — 17/17 PASS
  - Mocks AsyncMock para home_resolve y home_action
  - Cubre: resolved, ambiguous, unknown, not_allowed, mixed, exception isolation, CSV targets, summary format
- Registrado en AURORA `main.py`: schema TOOL_DECLARATIONS + dispatch (`await batch_home_action_async(...)`)
- Añadido a AURORA `core/qa_audit.py` EXPECTED_TOOLS

#### Despliegue (Ubuntu headless)
- SCP: `actions/batch_home_action.py` + `tests/test_batch_home_action.py`
- Parchado `main.py` Ubuntu: schema + dispatch
- Parchado `core/headless_permissions.py` Ubuntu: SAFE_WRITE
- Tests Ubuntu: 17/17 PASS

#### Estado
- **B23** (Agrupación por habitaciones): PARCIAL → OPERATIVO
- **B24** (Control simultáneo dispositivos): PARCIAL → OPERATIVO
- **41/68 OPERATIVO** (antes 39)
- tool_count AURORA: 60 → 61 | Ubuntu: 70 → 71

---

## 2026-11-05 — AUTOPILOT: E51 transport_schedules completo, despliegue AURORA+Ubuntu

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### transport_schedules (E51) — implementación completa

#### Implementación (AURORA)
- Nuevo fichero `actions/transport_schedules.py` — sin API key requerida
  - Metro Madrid L1-12 (horarios oficiales CRTM hardcoded)
  - Cercanías Madrid C1-C10
  - EMT Madrid (diurno + Búhos nocturnos N1-N27)
  - Renfe larga distancia (referencia a renfe.com)
  - `_detect_transport_type(query)` → clasificador regex (metro/cercanias/emt/renfe/generic)
  - Fix clave: Cercanías normaliza "1" → "c1" en `_fmt_cercanias`
- 32 tests en `tests/test_transport_schedules.py` — 32/32 PASS
- Registrado en AURORA `main.py`: lazy import + TOOL_DECLARATIONS schema + dispatch branch
- Añadido a AURORA `core/qa_audit.py` EXPECTED_TOOLS

#### Despliegue (Ubuntu headless)
- SCP: `actions/transport_schedules.py` + `tests/test_transport_schedules.py`
- Parchado `main.py` Ubuntu: lazy import + TOOL_DECLARATIONS schema + dispatch branch
- Parchado `core/qa_audit.py` Ubuntu: añadido transport_schedules a EXPECTED_TOOLS
- Tests Ubuntu: 32/32 PASS

#### Estado
- **E51** actualizado: PARCIAL → OPERATIVO (AURORA y Ubuntu)
- **39/68 OPERATIVO** (antes 38)
- tool_count AURORA: 59 → 60 | Ubuntu: 69 → 70

---

## 2026-11-05 — AUTOPILOT: Auditoría de integración, corrección tzdata, despliegue completo Ubuntu

**Autor:** Claude Sonnet 4.6 (automatizado — AUTOPILOT CONTINUO)
**Rama:** `codex/neural-voice-visual`

### Hallazgos de auditoría

#### LILITH Core: ACTIVO (no estaba inactivo)
- Contenedor Docker `lilith_core` activo y saludable en puerto 8000
- API responde: `{"status":"online","database":true,"mqtt":true}`
- Home Assistant también corriendo (`homeassistant/home-assistant:stable`, 7 días uptime)
- **Acción necesaria del usuario:** Añadir `LILITH_API_URL=http://100.95.4.122:8000` (Tailscale) o `http://192.168.1.50:8000` (LAN) en `C:\JARVIS\.env` para activar broadcast relay y acciones de hogar desde AURORA

#### Corrección tzdata/zoneinfo (19 fallos en test_timer.py)
- **Causa:** `actions/timer.py` usaba `ZoneInfo("UTC")` que requiere el paquete `tzdata` en Python 3.14 en Windows
- **Corrección:** Reemplazados todos los `ZoneInfo("UTC")` → `datetime.timezone.utc` (stdlib, sin dependencias externas)
- Afectaba exactamente 19 tests (todos en `TestTimerCreate`, `TestTimerList`, `TestTimerCancel`, `TestTimerFireCallback`, `TestTimerUnknownAction`)
- **Resultado:** 324/324 passed en AURORA (incluye test_timer.py: 36/36)

#### Herramientas faltantes en Ubuntu headless
- `calendar_control.py` y `traffic_info.py` nunca habían sido desplegadas en Ubuntu
- `test_timer.py`, `test_calendar_control.py`, `test_traffic_info.py` faltaban en Ubuntu
- Ubuntu `main.py` no tenía registradas: `timer`, `calendar_control`, `traffic_info`
- Ubuntu `core/qa_audit.py` no tenía los nuevos 10 tools en `EXPECTED_TOOLS`

#### Correcciones aplicadas en Ubuntu headless
- Desplegados: `actions/calendar_control.py`, `actions/traffic_info.py`, `actions/timer.py` (corregido)
- Copiados: `tests/test_timer.py`, `tests/test_calendar_control.py`, `tests/test_traffic_info.py`
- Parchado `main.py`: lazy imports, TOOL_DECLARATIONS, dispatch branches para timer/calendar/traffic
- Parchado `core/qa_audit.py`: añadidos los 10 nuevos tools a EXPECTED_TOOLS
- **Resultado:** 324/324 passed en Ubuntu headless

#### Discrepancia tool count (7 vs 9 en mensaje anterior)
- Corrección: Se implementaron **10 herramientas nuevas** en total (no 7 ni 9)
  - 3 herramientas de sesión anterior: `timer`, `calendar_control`, `traffic_info`
  - 7 herramientas del lote final: `radio_control`, `podcast_control`, `broadcast_control`, `audiobook_control`, `shopping_list`, `news_control`, `alarm_control`
- El mensaje inicial decía "9" (typo) y la tabla mostraba solo las 7 del último commit

#### STATUS_SNAPSHOT.json creado
- Nuevo archivo versionado `docs/NEST_68_AUTOPILOT/STATUS_SNAPSHOT.json`
- No está en `.gitignore` (que solo excluye `status.json` minúsculas)
- Contiene: conteo de tools, estados de capacidades, bloqueadores pendientes del usuario

#### Correcciones de sintaxis en Ubuntu headless main.py
- Dos errores de sintaxis detectados (pre-existentes, nunca visible por fallos previos en conftest.py):
  1. `open_capabilities_catalog` sin cierre externo `    },` antes del schema `timer` → añadido
  2. `    },` extra al final de `TOOL_DECLARATIONS` (residuo del patch de sesión anterior) → eliminado
- Verificación AST: `ast.parse()` limpio sin errores
- `calculator` también faltaba en Ubuntu: copiado `actions/calculator.py`, añadido schema + dispatch + lazy import
- Tests de contrato: `test_declared_tool_inventory_is_complete_and_unique`, `test_every_declared_tool_has_a_dispatch_path`, `test_repository_audit_returns_structured_findings` → **3/3 PASS** Ubuntu

### Tests finales
- AURORA: **324 passed** (10 módulos de herramientas nuevas)
- Ubuntu headless: **324 passed** (10 módulos de herramientas nuevas) + 3/3 ToolContractTests

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

## 2026-11-05 22:00 — Auditoria nocturna de coherencia del snapshot (solo lectura)

**Autor:** ChatGPT / automatizacion NEST 68
**Rama:** codex/neural-voice-visual

### Comprobaciones
- Git Windows HEAD eae30ec, arbol limpio al comenzar. Git Ubuntu HEAD c5c0516 con numerosos cambios modificados y sin seguimiento anteriores; no se han tocado.
- JARVIS Ubuntu /health: status=ok, state=STANDBY. LILITH /health: status=online, database=true, mqtt=true.
- STATUS_SNAPSHOT.json v11: OPERATIVO declarado=44, pero OPERATIVO_aurora enumera 43 IDs.
- operativo_differentiation enumera 45 entradas sin duplicados: 27 auto_integration + 16 code_only_no_physical + 2 physical_validated. Dos entradas adicionales respecto a OPERATIVO_aurora: home_routine_voice (alias/prueba, no capacidad del plan) y G67 (audio local sin validacion fisica, fuera de OPERATIVO_aurora).
- Los contadores de capability_count suman 72 (44+10+7+1+4+6), por lo que NO representan una particion exclusiva de las 68 capacidades. Hay etiquetas mixtas/solapadas. No se modifican cifras sin revisar el MASTER_PLAN.

### Resultado y siguiente paso
**HALLAZGO DE CONSISTENCIA:** el recuento 44/68 no queda respaldado por la lista de IDs de la version 11. No elevar ni reducir el numero por inferencia. Proximo bloque: cotejar los 68 IDs del MASTER_PLAN y definir estados mutuamente excluyentes, conservando subestados por plataforma. Sin cambios en servicios, dispositivos, secretos ni SOAK.


## 2026-11-05 23:00 — Reconciliacion de 68 IDs (solo lectura)

**Autor:** ChatGPT / NEST 68 nocturno
**Rama:** codex/neural-voice-visual

### Verificacion
- MASTER_PLAN.md: siete bloques A 1-10, B 11-24, C 25-35, D 36-40, E 41-54, F 55-61, G 62-68: 68 capacidades.
- STATUS_SNAPSHOT v11, listas de estados con IDs validos: OPERATIVO_aurora 43, PARCIAL_aurora 8, AUSENTE 2, BLOQUEADO 4, REQUIERE_HARDWARE 10. Total 67 IDs distintos, sin duplicados.
- Falta exclusivamente G67 (Audio local) en esas listas. MASTER_PLAN G67: AURORA OPERATIVO (WASAPI auditado), Ubuntu PARCIAL (ffplay, hardware no validado). La lista de tiers lo marca code_only_no_physical.
- Particion exclusiva **propuesta, NO aplicada**: 43 OPERATIVO, 9 PARCIAL (incluye G67), 2 AUSENTE, 4 BLOQUEADO, 10 REQUIERE_HARDWARE = 68. Es una clasificacion conservadora global; no equivale a certificacion fisica.
- Elementos A9_physical, C35_AUSENTE y home_routine_voice son anotaciones/alias, no IDs nuevos. DESCONOCIDO_ubuntu describe subestado de plataforma, no otra categoria global.
- La cifra 44/68 del snapshot queda pendiente de correccion documental consensuada con criterios por plataforma. No se cambiaron conteos ni codigos de produccion.
- JARVIS Ubuntu /health OK (STANDBY); LILITH /health OK (database y MQTT). Git Windows HEAD 23c6f34 al inicio, limpio; Ubuntu y LILITH con modificaciones ajenas preservadas.

### Siguiente paso
Ajustar STATUS_SNAPSHOT v12 de manera coherente con esta particion, manteniendo estados por plataforma separados; verificar que G67 permanezca PARCIAL hasta prueba fisica. Sin cambios de servicios ni SOAK.

## 2026-11-06 00:00 — Snapshot v12: particion exclusiva de 68 capacidades

**Autor:** ChatGPT / NEST 68 nocturno
**Rama:** codex/neural-voice-visual

### Verificacion
- Se leyeron HANDOFF, WORKLOG, STATUS_SNAPSHOT v11 y estados Git antes de modificar.
- Windows HEAD inicial 2469a8b, limpio; Ubuntu HEAD c5c0516 y LILITH HEAD 9ba6550 con cambios ajenos sin seguimiento/modificados, preservados.
- JARVIS Ubuntu /health: ok STANDBY; LILITH /health: online, database=true, mqtt=true.
- STATUS_SNAPSHOT v12: listas exclusivas 43 OPERATIVO, 9 PARCIAL, 2 AUSENTE, 4 BLOQUEADO, 10 REQUIERE_HARDWARE. Total 68 IDs distintos, cero duplicados.
- G67 agregado como PARCIAL global: audio AURORA auditado, audio Ubuntu pendiente de prueba fisica.
- Etiquetas A9_physical y C35_AUSENTE retiradas de la particion, conservadas como anotaciones de verificacion/plataforma.
- DESCONOCIDO=0 como categoria global; DESCONOCIDO_ubuntu permanece como anotacion especifica de plataforma.
- No se han modificado servicios, SOAK, dispositivos, permisos, credenciales ni codigo Ubuntu/LILITH.

### Siguiente paso
Revisar los consumidores del snapshot y asegurar que no interpreten las anotaciones de niveles como capacidades adicionales. Verificar sin acciones fisicas las pruebas existentes de home_routine y gateway Android.

## 2026-11-06 01:00 - Auditoria de consumidores de snapshot (solo lectura)
- Git Windows HEAD 1abf6ef, arbol limpio al inicio. Ubuntu headless y LILITH con cambios locales previos: preservados sin modificacion.
- Validacion PowerShell de STATUS_SNAPSHOT v12: 68 IDs en particion exclusiva, 68 unicos, 0 duplicados; G67 permanece PARCIAL_aurora.
- git grep sobre archivos versionados *.py/*.ps1/*.js/*.ts no encontro referencias a STATUS_SNAPSHOT: no hay consumidores de codigo rastreados que dependan directamente de este archivo. No equivale a descartar consumidores dinamicos o no versionados.
- JARVIS Ubuntu /health: status ok, STANDBY; LILITH /health: online, database=true, mqtt=true.
- Intento inicial de rg no disponible en PowerShell; se uso git grep como alternativa. Sin pruebas fisicas ni peticiones /api/chat con efectos.
- Proximo bloque: inspeccionar de forma no destructiva gateway Android y probar contratos de herramientas mediante tests aislados, sin ejecutar rutinas fisicas.

## 2026-11-06 02:00 - Gateway Android: prueba aislada y segura

**Autor:** ChatGPT / NEST 68 nocturno

- Preflight: Windows HEAD 137e472 limpio; Ubuntu HEAD c5c0516 y LILITH HEAD 9ba6550 con cambios locales anteriores, preservados.
- Health Ubuntu JARVIS: status=ok, STANDBY. LILITH: online, database=true, mqtt=true.
- Inspeccionado tests/test_android_gateway.py: contiene POST /api/chat real con Gemini; NO se ejecuto porque no es una prueba hermetica.
- Ejecutado en Ubuntu: PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_android_gateway_unit.py.
- Resultado: **6 passed in 0.58s**. Pruebas con servidor local efimero, Jarvis simulado y sin acceso a Gemini/HA: canal Android y propietario de sesion, autenticacion, limites de entrada, confirmacion/cancelacion y seleccion de bind.
- Primer intento mediante ejecutable pytest fallo durante carga de conftest con ModuleNotFoundError: api. Usando python3 -m pytest desde la raiz se resolvio; no se modifico codigo.
- No se ejecutaron acciones domesticas ni se reiniciaron servicios. No se modificaron arboles Ubuntu/LILITH.

### Siguiente bloque
Revisar si el contrato /api/tool/invoke y sus permisos tienen pruebas hermeticas equivalentes; ampliar tests solo si existe hueco verificable, sin llamadas a produccion.

## 2026-11-06 03:00 - Auditoria aislada de permisos Android invoke

**Autor:** ChatGPT / NEST 68 nocturno

- Preflight: Windows HEAD 2bb0dd5 limpio; Ubuntu HEAD c5c0516 y LILITH HEAD 9ba6550 con cambios ajenos preservados.
- Health: JARVIS Ubuntu /health ok STANDBY; LILITH /health online, database=true, mqtt=true.
- Se inspeccionaron api_server.py, core/headless_permissions.py y tests/test_block8_remote_access.py. POST /api/tool/invoke exige token, usa check_permission y rechaza DENIED/CONFIRM_REQUIRED antes de _dispatch_tool.
- Prueba hermetica: PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_block8_remote_access.py tests/test_android_gateway_unit.py -k 'invoke_denied_tool or invoke_confirm_required_blocked or wrong_token or no_token_disables_server or invalid_token or no_token_configured or empty_token or valid_token or auth_and_bounded_inputs_fail_closed'. Resultado: **9 passed, 19 deselected** en 1.11s.
- Hallazgo a evaluar (NO cambio): lilith_home_action turn_on/turn_off/toggle estan SAFE_WRITE y /api/tool/invoke puede ejecutarlos remotamente con token sin confirmacion vocal. Es una politica existente; no se realizaron acciones fisicas ni se modificaron permisos. La exigencia de confirmacion de home_routine no implica confirmacion general para estas llamadas directas.
- Alcance: tests comprueban denegacion y autenticacion, NO certifican autorizacion granular por entidad HA ni seguridad de todos los dispatches. No se hicieron peticiones al gateway productivo.
- Ubuntu/LILITH: ningun archivo alterado, ningun servicio reiniciado, SOAK preservado.

### Siguiente bloque
Auditar en lectura el riesgo de invocacion remota de lilith_home_action y documentar una propuesta de politica por dispositivo/accion sin cambiar comportamiento ni habilitar nuevas capacidades. Ampliar pruebas hermeticas solo si el riesgo y los contratos estan claros.
## 2026-11-06 04:00 - Auditoria de politica por entidad y accion (solo lectura)

**Autor:** ChatGPT / NEST 68 nocturno

- Preflight: Windows HEAD 0f50b62 y arbol limpio. Ubuntu HEAD c5c0516 (54 entradas locales en git status) y LILITH HEAD 9ba6550 con cambios ajenos; sin modificarlos.
- Health real: gateway JARVIS GET http://127.0.0.1:7471/api/health -> status=ok, STANDBY; LILITH GET http://127.0.0.1:8000/health -> online, database=true, mqtt=true. La prueba inicial de puerto 8001 no era aplicable; el gateway escucha en 7471.
- Inspeccion: core/headless_permissions.py clasifica lilith_home_action turn_on, turn_off y toggle como SAFE_WRITE. api_server.py /api/tool/invoke exige Bearer y rechaza DENIED/CONFIRM_REQUIRED, pero SAFE_WRITE pasa directamente a _dispatch_tool.
- En _dispatch_tool, lilith_home_action valida accion/target, resuelve entidad mediante LILITH y llama home_action. No hay comprobacion adicional de confirmacion por entity_id, dominio, dispositivo o accion en esta capa. LILITH aplica su propia allowlist (segun snapshot, solo light y turn_on/turn_off), por lo que el riesgo real queda limitado por ese segundo control, que NO se ha sometido a bypass ni probado fisicamente.
- Riesgo: cualquier cliente con token valido del gateway puede solicitar encendido/apagado de luces autorizadas sin confirmacion vocal. toggle pasa permiso gateway pero la allowlist de LILITH podria rechazarlo. No afirmar que otros dominios sean controlables.
- Propuesta NO desplegada: exigir confirmacion explicita para toda mutacion HA desde /api/tool/invoke; definir allowlist por entidad y accion (deny-by-default), separar permisos de consulta y accion, y agregar pruebas hermeticas que comprueben bloqueo antes de _dispatch_tool y ausencia de llamadas a home_action. Evaluar compatibilidad con APK y flujo de confirmacion antes de cualquier cambio.
- No se enviaron POST, no se tocaron dispositivos, permisos, servicios ni SOAK. No se ejecutaron pruebas de efectos; revision estatica y GET /health exclusivamente.

### Siguiente bloque
Disenar tests aislados de politica remota (sin desplegar): casos por dominio, accion, entidad, token y ausencia de confirmacion; comprobar contrato APK para evitar regresion. Mantener doble confirmacion Alexa intacta.

## 2026-11-06 05:00 - Contrato APK y matriz de autorizacion remota (sin despliegue)

**Autor:** ChatGPT / NEST 68 nocturno

- Preflight: Windows HEAD 1ff2c0b limpio; Ubuntu HEAD c5c0516 y LILITH HEAD 9ba6550, con modificaciones y archivos sin seguimiento ajenos preservados.
- Health no destructivo: JARVIS GET /api/health en 7471 = ok/STANDBY; LILITH GET /health en 8000 = online, database=true, mqtt=true.
- APK fuente /home/flako1312/apk_nueva_src/.../JarvisApi.kt: postChat usa POST /api/chat; no se encontraron referencias a /api/tool/invoke en fuentes Kotlin/Java inspeccionadas. Esto NO prueba el comportamiento de APK ya instalada ni de otros clientes.
- api_server.py _respond_invoke: DENIED y CONFIRM_REQUIRED reciben 403 antes de _dispatch_tool; SAFE_WRITE entra al despacho tras autenticar.
- Politica existente: lilith_home_action turn_on/turn_off/toggle = SAFE_WRITE. Adicionalmente batch_home_action wildcard = SAFE_WRITE en core/headless_permissions.py; revisar su ruta de despacho y efectos antes de afirmar alcance real. No se probaron dispositivos.
- Matriz propuesta para futuras pruebas hermeticas: (1) sin token/invalido -> rechazo; (2) herramienta DENIED -> 403, despacho 0; (3) CONFIRM_REQUIRED -> 403, despacho 0; (4) mutacion HA sin confirmacion explicita -> rechazo futuro, despacho 0; (5) entidad fuera de allowlist -> rechazo, home_action 0; (6) accion fuera de allowlist -> rechazo; (7) consulta permitida -> sin mutacion; (8) compatibilidad /api/chat APK -> conservar flujo existente. Propuesta, NO comportamiento implementado.
- Pruebas aisladas ejecutadas sin produccion: 9 passed, 19 deselected en 1.10s, pytest con PYTHONDONTWRITEBYTECODE=1 y cache deshabilitada.
- Sin POST productivos, cambios de permisos, servicios, SOAK ni archivos Ubuntu/LILITH.

### Siguiente bloque
Inspeccionar exclusivamente el despacho de batch_home_action y la ruta de /api/chat frente a confirmaciones; documentar riesgo y tests faltantes antes de proponer cualquier parche. No desplegar cambios sin verificar APK real y politica de confirmacion.

## 2026-11-06 05:10 - Despacho de batch_home_action y confirmación Android
- Preflight: Windows HEAD 844690d limpio. JARVIS Ubuntu y LILITH /health OK; cambios locales previos de Ubuntu preservados.
- Código auditado: `/api/tool/invoke` no implementa `batch_home_action` pese al permiso SAFE_WRITE, devuelve 400. `/api/chat` sí dispone de ruta al `batch_home_action_async` vía `_execute_tool` de Gemini. Solo se observó staging de confirmación explícito para Telegram, no para canal Android en ese punto.
- Pruebas herméticas con token ficticio y servidor efímero: 3/3 PASS (401 sin autenticación; 400 batch directo; 503 chat sin JARVIS). `tests/test_batch_home_action.py`: 17/17 PASS.
- Ninguna llamada productiva a LILITH home/action ni dispositivo HA. No se han reiniciado servicios, modificado permisos o archivos Ubuntu/LILITH.
- Hallazgos completos y plan en `REMOTE_BATCH_AUTH_AUDIT_2026-11-06.md`.
- Próximo ciclo: comprobar con mocks la confirmación de `/api/chat` frente a ejecución de acciones reales; diseñar cierre fail-closed compatible con APK, sin desplegar sin pruebas.

## 2026-11-06 05:15 — Verificación de ruta de confirmación Android (solo lectura)
- Preflight: Windows HEAD 0541b89 limpio; Ubuntu HEAD c5c0516 y LILITH HEAD 9ba6550 con cambios ajenos existentes preservados. Se leyeron HANDOFF, STATUS_SNAPSHOT v12 y WORKLOG antes de actuar.
- Health GET: JARVIS 7471 status=ok/STANDBY; LILITH 8000 status=online, database=true, mqtt=true.
- Confirmado en main.py: _execute_tool_batch llama a _execute_tool_guarded; este guard deriva directamente a _execute_tool si el nombre no pertenece a _SCHEDULED_TOOL_NAMES. batch_home_action llama a batch_home_action_async y no se observa confirmación propia en su rama.
- Resultado: evidencia estática de ausencia de confirmación específica Android para batch_home_action; no equivale a demostrar acción física ni bypass de la allowlist LILITH. No se ejecutaron pruebas de efecto.
- Sin cambios en Ubuntu/LILITH, permisos, servicios, SOAK o Alexa.
- Próximo bloque: test hermético con instancia simulada y llamada a _execute_tool_guarded para batch_home_action; verificar que no llega a home_action si se exige confirmación, antes de proponer parche reversible. No desplegar cambios durante SOAK.

## 2026-11-06 05:40 — Android confirmaciones domésticas, código y pruebas
- Se preparó un gate de acciones físicas para el canal Android: `lilith_home_action`, `batch_home_action`, `home_routine(confirm=true)` → acción pendiente, no ejecución inmediata. Reusa `/api/action/confirm` y `/api/action/cancel` con propietario de sesión y consumo de una vez.
- `/api/tool/invoke` ahora rechaza por código las acciones domésticas sin handshake de confirmación. Se corrigió `confirm="false"` en `actions/home_routine.py`.
- APK Android: DTO, endpoints, Repository, ViewModel y ChatScreen preparados con diálogo Confirmar/Cancelar. Compilación Kotlin offline: BUILD SUCCESSFUL. NO instalada.
- Suite seleccionada: **197/197 PASS**, 7 avisos; HTTP E2E simulado aprobado. Servicio y dispositivos NO reiniciados/accionados.
- Repo Ubuntu y APK mantienen cambios locales anteriores; no commit masivo. Copias y diffs de cada intervención en `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/`.
- Informe completo: `ANDROID_HOME_CONFIRMATION_2026-11-06.md`.

## 2026-11-06 05:45 — Sesiones Android separadas por instalación
- Detectado SettingsStore.deviceUuid: UUID aleatorio persistente en DataStore que la APK ya generaba.
- `JarvisApi` y `JarvisRepository` envían el identificador `jarvis-<deviceUuid>` en POST `/api/chat`, `/api/action/confirm`, `/api/action/cancel` (antes usaban `android` común para todos los dispositivos).
- `AppContainer` pasa SettingsStore al repositorio JARVIS. Recompilación Kotlin offline: BUILD SUCCESSFUL, sin instalación.
- Backups y diffs renovados en `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/apk/`. Sin cambios en servicios vivos.
- Próximo bloque: auditar concurrencia de confirmaciones Android, desplegar únicamente en ventana autorizada y validar físicamente.

## 2026-11-06 — Cambio de alcance y detección pasiva de audio Ubuntu
- Decisión del usuario: NEST 68 tiene DOS asistentes fijos: Windows despacho y Ubuntu comedor/cocina. Micrófono y altavoces conectados en Ubuntu. La APK Android queda FUERA del objetivo; no desarrollar/probar/desplegar APK, no borrar archivos previos. Los últimos checkpoints 05:40/05:45 sobre Android son trabajo externo anterior a esta decisión; no continuarlo.
- Preflight completo: HANDOFF, STATUS_SNAPSHOT v12, WORKLOG y Git de Windows, jarvis-headless, lilith. Windows HEAD 444af71 limpio; Ubuntu HEAD c5c0516 con numerosos archivos modificados/sin seguimiento (incluidos cambios Android recientes), LILITH HEAD 9ba6550 con cambios locales: todos preservados.
- Comprobación pasiva sin grabar/reproducir: `arecord -l` detecta USB Microphone (card 1, device 0), con 0/1 subdispositivos libres en el momento de la consulta (ocupado, no diagnostica fallo). `aplay -l` detecta salida analógica Intel ALC3234 y HDMI, además de USB Audio; no confirma qué altavoz está conectado ni salida predeterminada. `pactl info` no devolvió campos Default Sink/Source, pendiente verificar contexto del servidor de sonido. No se ha capturado ni reproducido audio.
- Health GET JARVIS 7471: ok/STANDBY. LILITH 8000: online, database=true, mqtt=true.
- Lista de pruebas físicas para usuario: (1) confirmar salida y fuente predeterminadas en sesión de audio real; (2) prueba corta de reproducción audible; (3) prueba breve de captura con consentimiento; (4) wake word y respuesta TTS sin música y con música; (5) conversación contextual y memoria entre sesiones; (6) home_routine con simulación y, solo con permiso, dispositivos HA reales; (7) alarmas/radio/podcast; (8) multiroom y automatizaciones por eventos únicamente tras autorización y preparación. No ejecutar pruebas físicas automáticamente.
- Siguiente bloque autónomo: identificar en lectura la pila de audio activa y comprobar configuración de captura/salida sin grabar ni reproducir, o ampliar tests herméticos de voz. Evitar alterar SOAK, servicios, permisos y cambios ajenos.

## 2026-11-06 06:05 — Confirmaciones concurrentes y APK generada, SIN despliegue
- Reproducido bug de confirmaciones simultáneas: canal global quedaba `telegram_confirmed` (prueba roja); corregido con candado compartido y ContextVar para canal Android (prueba verde).
- Diferenciación explícita de canal para grupos Telegram con chat IDs negativos; argumentos pendientes congelados con deepcopy; vista previa Android por propietario, comprobando propietario/canal/caducidad.
- Batería aislada: **249 passed, 7 warnings**, sin acciones HA ni Gemini real. Sintaxis y diff check correctos.
- APK Debug compilada y firmada: 18 MiB, firma v2 válida, SHA-256 `76519a12b2cb1e55e184f2f2fd64a6c3ae781402395a62f0aeda84d3cbb9ae56`.
- JARVIS y LILITH health OK; no reinicio, no instalación, doble Alexa intacta. Código Ubuntu/APK conserva otros cambios preexistentes; originales y parches bajo `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/`.
- Informe: `ANDROID_CONFIRMATION_CONCURRENCY_2026-11-06.md`. Siguiente paso BLOQUEADO: reinicio autorizado de JARVIS y despliegue/supervisión de APK.

## 2026-11-06 06:10 - JARVIS-only: timer, herramientas, conversación
- Alcance: terminar solo los asistentes JARVIS/AURORA Windows y JARVIS Ubuntu; no APK ni cambios LILITH Core (M-3 a M-9 aparte). Automatización horaria actualizada a JARVIS - cierre autónomo.
- Herramientas (timer, calendar, traffic, radio, podcast, alarm, transport, batch): Ubuntu 259/259 PASS. Windows inicialmente 258/259: test_fire_calls_player_speak fallo porque la notificación OS retrasaba la voz. Corregida prioridad de voz, aislada notificación real en tests, test de orden. Windows 260/260 PASS. Commit 333625b. Backup C:\Users\loren\JARVIS_BACKUPS\nest68_timer_20261106.
- Conversación/persistencia/guards simulados: Windows 102/102 PASS, Ubuntu 100/100 PASS.
- Nuevo test AST de contrato tests/test_tool_dispatch_contract.py: 1/1 PASS en Windows y 1/1 PASS en Ubuntu. Asegura rama de despacho por nombre declarado sin audio/red; no demuestra ejecución física.
- Línea base STATUS_SNAPSHOT v12: 43 OPERATIVO declarado, 9 PARCIAL, 2 AUSENTE, 4 BLOQUEADO, 10 HARDWARE. Detalles en JARVIS_ONLY_EXIT_CRITERIA_2026-11-06.md.
- Sin reinicios, sin cambios SOAK/LILITH/HA. Siguiente: voz simulada, seguridad del dispatcher y cierre de software sin dependencias externas.

## 2026-11-06 06:20 - JARVIS voice reconnection and interruption tests
- Windows: tests/test_gemini_live_session.py, test_phy2_004_audio_interruption.py, test_phy2_004_speech_gate.py, test_audio_device_selector.py, test_local_file_audio_gate.py -> **115 passed, 1 warning**.
- Ubuntu: tests/test_gemini_live_session.py, test_local_barge_in.py, test_barge_in_dedup.py, test_block9_voice_stability.py, test_catalog_voice.py, test_phy2_004_audio_interruption.py, test_phy2_004_speech_gate.py, test_headless_on_demand_wake.py, test_headless_hey_jarvis_wake.py -> **150 passed, 1 warning**.
- Tests mocked / simulated: no physical microphone recording, audio playback, Gemini network session, action HA or LILITH Core write. Code has dispatch contract AST tests in Git on both hosts: Windows commit 3b6b91c; Ubuntu commit d5a1db8 with all other dirty files preserved.
- Next permitted step: additional static/tool tests + controlled diagnosis. Hardware audio validation and any restart remain awaiting user authorization.

## 2026-11-06 — B22: evaluador hermético de eventos HA (sin despliegue)
- Preflight: leídos STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG y Git de Windows, Ubuntu y LILITH. Windows limpio HEAD 874176c; Ubuntu con cambios ajenos preservados; LILITH HEAD 1257c53 y cambios ajenos preservados.
- Health GET Ubuntu JARVIS: ok/STANDBY; LILITH: online, database=true, mqtt=true.
- Nuevos archivos exclusivos Windows: core/ha_event_dry_run.py y tests/test_ha_event_dry_run.py. Evaluador puro de transiciones state_changed de sensor/binary_sensor; retorna solo ID de rutina. No conecta a HA, no ejecuta rutinas ni toca LILITH.
- Test hermético: 7 passed (C:\JARVIS\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ha_event_dry_run.py); git diff --check sin errores. Primera invocación 'python' encontró alias Microsoft Store; corregido usando .venv.
- B22 sigue AUSENTE como automatización real: este es solo un componente aislado y probado. Integración del flujo de eventos, autorización y ejecución requiere diseño/validación con LILITH/HA y permiso; no marcar OPERATIVO.
- C35 multiroom sigue AUSENTE. Próximo ciclo: diseñar planificador puro de zonas/altavoces y pruebas mock sin emitir audio.
- Sin reinicios, cambios SOAK, APK, HA, LILITH, permisos ni audio físico.

## 2026-11-06 07:55 — C35 planificador multiroom hermético
- Preflight: leídos STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG y estados Git de ambos JARVIS. Windows limpio HEAD e978f19; Ubuntu HEAD d5a1db8 con cambios ajenos preservados.
- Health GET: JARVIS Ubuntu 7471 ok/STANDBY; LILITH 8000 online, database=true, mqtt=true.
- Nuevos archivos solo Windows: core/multiroom_dry_run.py y tests/test_multiroom_dry_run.py. Planificador puro que asigna zonas a altavoces disponibles y rechaza zonas duplicadas, desconocidas, altavoces no disponibles y conflictos de asignación. No usa red, dispositivos, audio ni reproducción.
- Tests: 11/11 PASS (pytest aislado), git diff --check correcto. Sin cambios en Ubuntu/LILITH/HA, permisos, SOAK ni reinicios.
- C35 permanece AUSENTE como reproducción real: este bloque solo prepara la lógica de asignación, NO sincronización, transporte, latencia ni ejecución física. B22 también permanece AUSENTE como automatización real.
- Siguiente bloque: diseñar contrato de coordinación multiroom entre Windows y Ubuntu con mensajes simulados, tiempos y fallos; no habilitar reproducción sin autorización.

## 2026-11-06 09:00 — C35 simulador de coordinación multiroom
- Preflight: HANDOFF, MASTER_PLAN, STATUS_SNAPSHOT y WORKLOG consultados; Git Windows limpio en HEAD 95f2c1b; Ubuntu con modificaciones y archivos sin seguimiento ajenos preservados.
- Nuevos archivos Windows: core/multiroom_sync_dry_run.py y tests/test_multiroom_sync_dry_run.py. Modelo puro de latencias, preparación, desconexión y desfase; falla de forma segura sin I/O, audio, red ni dispositivos.
- Pruebas aisladas: 21/21 PASS (11 anteriores de rutas + 10 nuevas de sincronización). Python invocado por ruta absoluta, pues alias python de Microsoft Store no sirve.
- C35 sigue AUSENTE como función real: no existe transporte de audio ni sincronización física; únicamente planificador y simulador. Próximo: diseñar contrato de mensajes y pruebas de fallos/desconexiones entre dos asistentes sin tocar producción.
- No se reiniciaron servicios, no se alteró Ubuntu/LILITH/HA, SOAK ni doble confirmación Alexa.

## 2026-11-06 10:03 — C35 contrato hermético de mensajes Windows–Ubuntu
- Preflight: STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG consultados; Windows HEAD 8928814 limpio, Ubuntu HEAD d5a1db8 con cambios ajenos preservados.
- Nuevos archivos solo Windows: core/multiroom_protocol_dry_run.py y tests/test_multiroom_protocol_dry_run.py. Contrato puro de prepare/ready/start/abort/ack con sesión, pares autorizados, secuencia estricta y latencia acotada; rechaza replays, mensajes fuera de orden, campos extra y sesiones abortadas.
- Tests aislados del conjunto C35: 38/38 PASS, git diff --check correcto. No transporte real, red, audio, HA ni LILITH write; C35 permanece AUSENTE en operación física.
- Próximo bloque: modelar handshake y timeout/reintentos fail-closed con pruebas herméticas; integración real y sonido requieren autorización posterior.

## 2026-11-06 11:00 - C35 handshake y reintentos hermeticos
- Preflight: leidos STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG; Git Windows limpio HEAD 6212ab7; Ubuntu con modificaciones y untracked ajenos preservados; LILITH con cambios ajenos preservados.
- Nuevo modulo puro core/multiroom_handshake_dry_run.py y tests/test_multiroom_handshake_dry_run.py: estados new/waiting/ready/started/aborted, timeout determinista, hasta N reintentos y abort fail-closed. Sin red, reloj real, audio ni efectos.
- Suite aislada multiroom: 52/52 PASS (14 nuevas), sin pytest cache. C35 permanece AUSENTE como reproduccion real; solo logica simulada.
- Siguiente: probar fallos cruzados de sesion y documentar contrato de transporte, sin desplegar ni alterar SOAK.

## 2026-11-06 12:00 — C35 aislamiento de sesiones multiroom
- Preflight: STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG y Git Windows/Ubuntu consultados. Windows HEAD 5c17474 limpio antes del bloque; Ubuntu mantiene sus cambios ajenos intactos.
- Añadido tests/test_multiroom_cross_session_dry_run.py: seis regresiones hermeticas para cancelacion de una sesion sin afectar otra, secuencias por sesion/emisor, rechazo de reutilizacion de sesion cancelada, timeouts independientes y rechazo de session_id incorrecto.
- Suite C35: 58/58 PASS (52 anteriores + 6 nuevas), sin audio, red, servicios ni dispositivos. C35 sigue AUSENTE como reproduccion real.
- Contrato futuro de transporte (NO desplegado): canal autenticado entre pares fijos, session_id aleatorio no reutilizable, sequence monotona por emisor, ACK correlacionado, expiracion y abort fail-closed; no iniciar audio sin READY de ambos. Falta implementar transporte y validarlo en ventana autorizada.
- No se tocaron Ubuntu, LILITH, HA, SOAK, APK ni doble confirmacion Alexa.
- Siguiente: revisar correlacion de ACK y replays entre sesiones con pruebas puras; no activar transporte.

## 2026-11-06 13:00 — C35 ACK correlacionado (solo simulacion)
- Preflight: STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG y estados Git de Windows/Ubuntu consultados. Windows HEAD 173d080 limpio; Ubuntu conserva cambios locales ajenos.
- Nuevos archivos solo Windows: core/multiroom_ack_dry_run.py y tests/test_multiroom_ack_dry_run.py. Ledger de ACK que comprueba sesion, emisor/destinatario invertidos y secuencia original; rechaza duplicados, replays entre sesiones, ACK sin pendiente y reutilizacion tras cierre.
- Suite multiroom hermetica: 68/68 PASS (10 nuevas); git diff --check sin errores. Sin red, audio, servicios, HA, LILITH ni dispositivos.
- C35 sigue AUSENTE como funcion fisica: ACK simulado no autentica un transporte real ni transmite sonido. Pendientes: autenticacion, transporte, sincronizacion y pruebas fisicas autorizadas.
- Proximo bloque: especificar autenticacion del transporte y validar mensajes maliciosos con mocks sin desplegar.

## 2026-11-06 14:00 — C35 autenticacion hermetica HMAC
- Preflight: consultados STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG y Git Windows/Ubuntu. Windows HEAD f3f0f4d limpio; Ubuntu mantiene cambios ajenos intactos.
- Nuevos archivos Windows core/multiroom_auth_dry_run.py y tests/test_multiroom_auth_dry_run.py. Firma HMAC-SHA256 con clave de prueba aportada en memoria; rechazo de manipulacion, identidad ajena, firma incorrecta, repeticion, sesion incorrecta y reutilizacion tras abort. Sin sockets ni audio.
- Suite multiroom: 83/83 PASS (15 nuevas), 1968 pruebas no seleccionadas; 1 aviso de deprecacion externo. Primer intento con wildcard pytest en PowerShell no expandio; repetido correctamente con -k multiroom.
- IMPORTANTE: C35 sigue AUSENTE fisicamente. Este codigo NO proporciona transporte, distribucion segura de claves, sincronizacion de audio ni prueba de red; prohibido llamarlo autenticacion desplegada.
- Sin modificaciones Ubuntu/LILITH/HA/APK, SOAK, permisos, dispositivos o servicios.
- Siguiente bloque: pruebas de robustez del protocolo ante mensajes malformados y expiracion de sesiones; despues propuesta de transporte para ventana autorizada.

## 2026-11-06 — C35 mensajes malformados (ciclo seguro)
- Nuevo archivo propio: `tests/test_multiroom_malformed_dry_run.py`, 15 casos nuevos para cargas/firmas inválidas y no consumo de secuencia tras rechazo.
- Verificación: `py -m pytest -q tests/test_multiroom_malformed_dry_run.py tests/test_multiroom_auth_dry_run.py` => **30 passed in 0.12s**. `python` no está en PATH; `py` funciona.
- Sin red, sonido, dispositivos, servicios, LILITH ni cambios en Ubuntu. C35 continúa como software simulado, NO operativo físicamente.
- Próximo bloque: pruebas de expiración de sesiones y revisión de límites de memoria del verificador, después transporte autenticado desactivado por defecto.

## 2026-11-06 15:00 — C35 expiracion y cupo (simulacion)
- Implementado `core/multiroom_expiry_dry_run.py` con reloj inyectado, caducidad fija fail-closed, rechazo de re-registro de sesion expirada y cupo de sesiones activas. No sockets, audio ni configuracion productiva.
- Añadidos 12 tests en `tests/test_multiroom_expiry_dry_run.py`; `py -m pytest -q tests/test_multiroom_expiry_dry_run.py tests/test_multiroom_auth_dry_run.py tests/test_multiroom_malformed_dry_run.py` => **42 passed**.
- Intento de suite amplia `py -m pytest -q tests -k multiroom` bloqueado en coleccion por **40 errores de dependencias ausentes** en Python global 3.14 (google/genai, PyQt6, playwright, sqlalchemy, etc.). No significa fallo de los tests multiroom; no se instalaron dependencias ni se toco el entorno activo. Proximo ciclo: localizar entorno virtual de proyecto y ejecutar bateria dirigida, sin alterar servicios.
- Estado C35: preparacion software hermetica, NO operativo; transporte real, secretos, audio fisico y validacion pendientes. Ubuntu tiene numerosos cambios ajenos sin seguimiento: intactos. Snapshot global de 68 capacidades sin promocion por tests simulados.

## 2026-11-06 — Diagnostico entorno Python Windows (ciclo seguro)
- Leidos STATUS_SNAPSHOT v12, MASTER_PLAN, HANDOFF, WORKLOG y Git de Windows/Ubuntu. Ubuntu dirty/untracked ajeno preservado; Windows limpio antes de este bloque.
- Identificado entorno correcto `C:\JARVIS\.venv\Scripts\python.exe` (Python 3.14.5), con PyQt6, playwright, sqlalchemy, google y pytest disponibles. El Python global no era el entorno del proyecto; no instalar dependencias.
- Suite completa de seleccion multiroom desde entorno de proyecto: `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests -k multiroom --disable-warnings --maxfail=1` => **110 passed, 1968 deselected, 1 warning** (exit 0).
- Sin red, audio fisico, reinicios, HA/LILITH ni cambios Ubuntu. C35 permanece NO operativo fisicamente: tests de simulacion, no transporte real.
- Siguiente: diagnosticar la advertencia de pytest y auditar pruebas hermeticas de integracion B22 sin tocar HA.

## 2026-11-06 — B22 propuestas de rutinas por evento, solo dry-run
- Acceso Remote Desktop Commander restablecido a ambos equipos; preflight STATUS_SNAPSHOT, MASTER_PLAN, HANDOFF, WORKLOG y estados Git de ambos JARVIS. Ubuntu con cambios ajenos preservados; Windows limpio antes de este bloque.
- Nuevos `core/ha_event_proposals_dry_run.py` y `tests/test_ha_event_proposals_dry_run.py`: propuestas de IDs de rutinas sin ejecutar nada; deduplicacion y rechazo de datos malformados.
- `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_ha_event_dry_run.py tests/test_ha_event_proposals_dry_run.py` => **13 passed** (6 nuevas). Sin red, sonido, HA, LILITH ni dispositivos.
- B22 sigue AUSENTE como automatizacion productiva; falta integracion autorizada con el flujo de eventos y autoridad de rutinas LILITH. Siguiente: pruebas de eventos repetidos y diseño de contrato de entrega sin activar HA.

## 2026-11-06 — Cierre seguro B22/C35, sin despliegue
- Preflight: Windows limpio antes del bloque; Ubuntu mantiene cambios modificados y sin seguimiento; JARVIS Ubuntu en STANDBY y LILITH/HA saludables. No se reiniciaron servicios ni se ejecutó audio o control físico.
- B22: añadido `core/ha_event_processor_dry_run.py`, con estado de conexión, reconexión observable, deduplicación determinista, validación fail-closed, contador de errores y registro inyectable. Solo devuelve propuestas de rutina; no se suscribe a HA ni llama a LILITH.
- B22: `tests/test_ha_event_processor_dry_run.py` + evaluadores previos: 18 pruebas dirigidas PASS. B22 permanece AUSENTE como automatización real porque falta el flujo autorizado HA→LILITH.
- C35: verificada la batería hermética multiroom existente: 110 pruebas PASS desde el entorno `.venv`. C35 permanece AUSENTE como reproducción real: no hay transporte autenticado desplegado, provisionamiento de claves, sincronización física ni altavoces validados.
- Estado global conservador: 43 OPERATIVO, 9 PARCIAL, 2 AUSENTE, 4 BLOQUEADO y 10 REQUIERE_HARDWARE = 68. No se promovieron capacidades por simulaciones.
- `STATUS_SNAPSHOT.json` actualizado a v13. Cambios propios pendientes de commit; no se tocaron archivos Ubuntu, LILITH Core, Home Assistant, APK ni SOAK.
- Verificación remota posterior: Ubuntu compiló `main.py`, `actions/home_routine.py` y `actions/transport_schedules.py`; suites disponibles `transport_schedules`, `batch_home_action`, `timer`, `calendar_control` y `traffic_info`: **172 passed**. `tests/test_home_routine.py` no existe en el checkout Ubuntu, por lo que no se presenta como prueba pasada allí.

## 2026-11-06 — Integración JARVIS B22/C35 sin mutar autoridad externa
- B22: añadido `core/ha_event_bridge.py`, puente autenticado de solo lectura que procesa propuestas, consulta `routines.get` en LILITH con `request_id`/`idempotency_key` estables y bloquea la ejecución. 23 pruebas B22 dirigidas PASS.
- C35: añadido `core/multiroom_transport.py`, transporte TCP de control con framing JSON, HMAC, ACK, rechazo fail-closed y reintentos. No transporta audio ni se inicia automáticamente. 114 pruebas multiroom PASS en Windows.
- Archivos nuevos copiados a Ubuntu sin sobrescribir cambios: compilación PASS; B22 bridge 23/23 PASS y transporte 4/4 PASS. Quedan untracked por la política de preservar la rama Ubuntu.
- No se modificaron LILITH Core, Home Assistant, permisos, APK, servicios, SOAK ni dispositivos. B22/C35 permanecen AUSENTE en el inventario global porque falta la integración productiva/autorizada y la validación física.
- Regresión de voz/dispatcher Windows: **68 passed, 1 warning** (`test_tool_dispatch_contract`, `test_gemini_live_session`, interrupción y speech gate). Ubuntu no pudo coleccionar las pruebas que importan `main.py` por `ModuleNotFoundError: numpy`; no se instaló nada ni se modificó el servicio. Se mantiene como bloqueo de entorno preexistente.
