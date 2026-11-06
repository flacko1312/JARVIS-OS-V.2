# HANDOFF — Instrucciones para reanudar el trabajo

Última actualización: 2026-11-05 (sesión 9 — P1-P5 bugs fijados, P3 health injection verificado, STATUS_SNAPSHOT v11)
Checkpoint: 44/68 OPERATIVO. AURORA 63 tools, Ubuntu 74 tools (headless: 36 herramientas activas).

---

## Para reanudar al escribir «CONTINÚA»

1. Leer este archivo (HANDOFF.md).
2. Leer MASTER_PLAN.md para ver el estado actual de las 68 capacidades.
3. Leer STATUS_SNAPSHOT.json para el resumen ejecutivo.
4. Ejecutar `git -C C:\JARVIS log --oneline -5` para ver últimos commits.
5. Continuar con la siguiente tarea pendiente (sección abajo).

---

## Estado actual del ecosistema (2026-11-05)

### AURORA/JARVIS Windows — 63 tools, branch codex/neural-voice-visual
- 45/68 capacidades OPERATIVO
- 79/79 tests pasan (home_routine 30 + transport_schedules 32 + batch_home_action 17)
- LILITH_API_URL=http://192.168.1.50:8000 — configurado y verificado
- Todos los endpoints `/api/v1/integration/*` autenticados funcionando

### JARVIS Ubuntu Headless — `/home/flako1312/jarvis-headless` — 74 tools (headless: 36)
- 79/79 tests pasan + 3/3 ToolContractTests
- Puerto 7471: Android APK gateway — 87 reglas de permisos, /api/chat con 74 tools disponibles
- **SESIÓN 9 — CAMBIOS NO TRACKEADOS EN GIT (Ubuntu):**
  - main.py línea 4292: `resp.get("data",{}).get("response",{})...` → `resp.get("response",{})...` (bug P3)
  - main.py HEADLESS_ACTIONS: 21→36 tools (añadidos home_routine + 14 domésticos)
  - main.py TOOL_DECLARATIONS: home_routine declaration añadida (bug P1 — Gemini no podía llamarlo)
  - Verificado: journal confirma `tools=36` y `Routine health: failures detected, injecting alert`

### LILITH Core — Docker `lilith_core`, puerto 8000
- Estado: RUNNING, healthy, database+mqtt+kernel+home_assistant=true
- API de integración: `/api/v1/integration/*` — todos los endpoints respondiendo
- Broadcast intent NO en allowlist del token JARVIS (HTTP 403)

### Home Assistant — Auditado en vivo (sesión 6)
- light.bombilla_mueble: registrada, state=unavailable (física offline)
- light.bombilla_tv: registrada, state=unavailable (física offline)
- switch.cargador_hub: registrada, state=unavailable (física offline)
- sensor.lilith_temperatura: registrada, state=unavailable (física offline)
- **media_player.hub: AVAILABLE (state=off, available=True)** ← único dispositivo funcional
- media_player.mc_smart_tv_pro_cast: unavailable
- Ninguna entidad cover.* ni climate.* registrada

---

## Herramientas implementadas (sesiones 1-6 acumulado)

| Tool | Tests | Estado | Sesión |
|------|-------|--------|--------|
| timer | 36 | OPERATIVO | 4 |
| alarm_control | 31 | OPERATIVO | 4 |
| shopping_list | 35 | OPERATIVO | 4 |
| news_control | 28 | OPERATIVO | 4 |
| radio_control | 31 | OPERATIVO (código) | 4 |
| podcast_control | 26 | OPERATIVO (código) | 4 |
| audiobook_control | 31 | OPERATIVO (código) | 4 |
| broadcast_control | 20 | OPERATIVO (local) | 4 |
| calendar_control | 42 | PARCIAL | 4 |
| traffic_info | 45 | PARCIAL | 4 |
| transport_schedules | 32 | OPERATIVO | 5 |
| batch_home_action | 17 | OPERATIVO | 5 |
| lilith_home_status | — | OPERATIVO | 5 |
| home_routine | 30 | OPERATIVO | 6 |

---

## Tareas pendientes (en orden de prioridad)

### 0. Completado en sesiones 5-8
- transport_schedules: disclaimer DATOS ESTÁTICOS ✓
- STATUS_SNAPSHOT v7→v9: correcciones y auditorías ✓
- OPERATIVO_VERIFICATION.md: tabla auto-test/integration/physical ✓
- home_routine P3: 5 rutinas, 30 tests, AURORA+Ubuntu ✓
- HEADLESS_SYSTEM_RULES: reescrito con todos los tools ✓
- Auditoría HA en vivo: 6 entidades auditadas (1 AVAILABLE) ✓
- **Sesión 7**: ROUTINE_ROUTING_RULES corregido (home_routine como regla #1) ✓
- **Sesión 7**: HEADLESS_SYSTEM_RULES Ubuntu con frases routing home_routine ✓
- **Sesión 7**: Auditoría broadcast → absent del protocolo LILITH (no fix posible sin equipo LILITH) ✓
- **Sesión 7**: Auditoría memoria → 91 hechos, 16 categorías, funcional ✓
- **Sesión 7**: Auditoría APK gateway → api_server.py (puerto 7471), /api/chat NL path completo ✓
- **Sesión 7**: Re-auditoría 45 OPERATIVO → 3 niveles diferenciados (auto/code/physical) ✓
- **Sesión 8**: P1 E2E verificado (3 capas: system prompt 7/7, direct calls 6/6, live 1/5 pendiente reconnect) ✓
- **Sesión 8**: P2 memoria — 92 hechos perfil usuario vs 518 semánticos en BD, cross-session confirmado ✓
- **Sesión 8**: P3 APK dispatch — /api/chat NL (73 tools), /api/tool/invoke (16 directo) ✓
- **Sesión 8**: P4 conteo corregido — G67 → code_only_no_physical, OPERATIVO=44 (no 45) ✓
- **Sesión 8**: P5 routine health — 4 rutinas fallan por light.bombilla_mueble offline; inyectado en system prompt Gemini ✓
- **Sesión 9**: P1 BUG FIX — home_routine no estaba en TOOL_DECLARATIONS ni HEADLESS_ACTIONS (Gemini nunca podía llamarlo). HEADLESS_ACTIONS: 21→36. Voice routing: 5/5 PASS ✓
- **Sesión 9**: P2 BUG FIX — _entity_is_available() pre-check en home_routine.py. Dispositivos offline omitidos sin error. P2 test PASS ✓
- **Sesión 9**: P3 BUG FIX — _fetch_routine_health_summary usaba ruta incorrecta `data.response.routines` → `response.routines`. Ahora journal confirma inyección al conectar ✓
- **Sesión 9**: P4 — memoria 93 facts (LILITH get_context), local long_term.json 10 ítems, semantic search funcional ✓
- **Sesión 9**: P5 — Android /api/chat 6/7 PASS (timer, alarm, shopping, reminder, lilith_query, routine_check) ✓

### 1. P2 — Integración memoria LILITH en conversación (VERIFICADO ✓)
- 93 hechos en LILITH (get_context() total_facts=93), cargados en cada sesión (confirmado en journal)
- 518+ entradas semánticas en BD (API limita a 20 por búsqueda — total no accesible via API)
- memory.store y memory.search confirmados operativos, persistencia cross-session verificada
- Reglas en HEADLESS_SYSTEM_RULES: solo en solicitud explícita (correcto)

### 2. Validación física de audio (requiere altavoces)
- C28/C29/C30 (radio/podcast/audiobook): probar `ffplay` con altavoces conectados
- E41 (alarmas): probar sonido beep 880Hz
- D37/D38 (broadcast): probar TTS local

### 3. Desbloqueadores del usuario
- **GCAL_OAUTH**: Colocar archivo OAuth JSON en `C:\JARVIS\config\gcal_client.json` → E44/E45 pasan a OPERATIVO
- **ORS_API_KEY**: Registrar en openrouteservice.org (gratis) → decir "configura tráfico api_key=TU_CLAVE" → E49 OPERATIVO
- **LILITH broadcast allowlist**: Pedir al equipo LILITH añadir `broadcast` a allowed intents → D38 relay completo

### 3. Capacidades DESCONOCIDO en Ubuntu a verificar
- B19/B21 (rutinas LILITH): `lilith_routine` en HEADLESS_SYSTEM_RULES → probablemente operativo, no verificado con hardware
- C25-C27 (música/Spotify/YTMusic): media_control en Ubuntu headless — sin validación física
- E43 (recordatorios): `reminder` en HEADLESS_SYSTEM_RULES — operativo en código

### 4. Desbloqueadores del usuario (prioridad)
- **GCAL_OAUTH**: Colocar archivo OAuth JSON → E44/E45 OPERATIVO
- **ORS_API_KEY**: Registrar gratis en openrouteservice.org → E49 OPERATIVO
- **Encender dispositivos físicos**: light.bombilla_mueble/tv, switch.cargador_hub → validar rutinas domésticas con dispositivos reales

### 4. WebSocket adapter Phase 2 (G68)
- Verificar si LILITH soporta WebSocket en `/api/v1/integration/ws`
- Si sí: habilitar `ADAPTER_CONNECTION_ENABLED=true` en `.env`

### 5. Próximas capacidades AUSENTE a implementar
- **B22** (automatizaciones por eventos HA): triggers de sensores → requiere HA webhook o MQTT
- **C35** (multiroom): Music Assistant en Ubuntu → requiere setup HA addon

---

## Configuración de entorno

```
# C:\JARVIS\.env:
LILITH_API_URL=http://192.168.1.50:8000  ✓ configurado
LILITH_API_KEY=<token>                    ✓ configurado
ADAPTER_CONNECTION_ENABLED=false          Phase 2 OFF por defecto
GCAL_OAUTH_CLIENT_FILE=                   FALTA — usuario debe añadir
ORS_API_KEY=                              FALTA — usuario debe registrar
```

## Precauciones obligatorias

- NO interrumpir servicios SOAK activos en Ubuntu/LILITH
- NO modificar configuraciones de Tailscale/SSH sin vía de recuperación
- NO resetear memoria persistente de LILITH
- NO eliminar entidades HA sin auditar primero su estado
- Protección doble confirmación de Alexa: NO eliminar hasta tener alternativa probada
- WebSocket adapter: NO habilitar en producción sin verificar soporte LILITH
- LILITH token: solo integration-scoped Bearer (nunca admin token)

## Auditoria nocturna 2026-11-05 22:00
- JARVIS Ubuntu y LILITH: health OK; SOAK y servicios sin cambios.
- Inconsistencia STATUS_SNAPSHOT v11: OPERATIVO=44 declarado, lista OPERATIVO_aurora=43, tiers=45 (extras home_routine_voice y G67). Contadores de estados suman 72, no 68. Ver WORKLOG.
- Proxima tarea: reconciliar MASTER_PLAN 68 IDs con STATUS_SNAPSHOT sin inventar resultados ni tocar hardware.
- Preservar todos los cambios sin seguimiento y modificados de Ubuntu y LILITH.

## Auditoria nocturna 2026-11-05 23:00
- Se reconciliaron 67 IDs exclusivos del snapshot con los 68 del MASTER_PLAN: falta G67 (audio local) como estado global.
- Particion conservadora propuesta: 43 OPERATIVO, 9 PARCIAL (G67 incluido), 2 AUSENTE, 4 BLOQUEADO, 10 REQUIERE_HARDWARE = 68.
- A9_physical, C35_AUSENTE, home_routine_voice y DESCONOCIDO_ubuntu son etiquetas de subestado, no capacidades adicionales.
- Proximo bloque: corregir STATUS_SNAPSHOT v12 sin inflar operatividad y conservar estados de cada plataforma.
- JARVIS y LILITH health OK. Ningun servicio ni archivo Ubuntu/LILITH modificado.

## Cierre nocturno 2026-11-06 00:00 — STATUS_SNAPSHOT v12
- Aplicada particion exclusiva global: 43 OPERATIVO + 9 PARCIAL + 2 AUSENTE + 4 BLOQUEADO + 10 REQUIERE_HARDWARE = 68, sin IDs duplicados.
- G67 es PARCIAL global por audio Ubuntu no validado fisicamente. Estados por plataforma y tiers son anotaciones separadas.
- JARVIS Ubuntu y LILITH /health OK. Sin tocar servicios, SOAK ni arboles Ubuntu/LILITH.
- Proximo bloque: auditar consumidores del snapshot y pruebas no destructivas de home_routine/Android.

## Auditoria nocturna 2026-11-06 01:00
- STATUS_SNAPSHOT v12 validado: 68 IDs exclusivos y sin duplicados; G67 parcial.
- Sin consumidores directos de STATUS_SNAPSHOT en codigo versionado Python/PowerShell/JS/TS (git grep). No se afirma ausencia de consumidores dinamicos.
- Ubuntu JARVIS y LILITH health OK; cambios locales preservados.
- Proximo bloque: auditoria de gateway Android y tests aislados no destructivos.

## Auditoria nocturna 2026-11-06 02:00
- Gateway Android: tests hermeticos 6/6 PASS via python3 -m pytest; sin Gemini ni acciones fisicas.
- tests/test_android_gateway.py es prueba E2E real y se evito en horario nocturno.
- Health JARVIS/LILITH OK; archivos Ubuntu/LILITH sin modificar.
- Siguiente bloque: cobertura de permisos /api/tool/invoke sin produccion.

## Auditoria nocturna 2026-11-06 03:00
- Permisos Android /api/tool/invoke: 9 pruebas aisladas PASS (auth, denegacion, confirmacion).
- Observacion: lilith_home_action turn_on/turn_off/toggle SAFE_WRITE permite control directo autenticado sin confirmacion vocal; no se cambio politica ni se acciono HA.
- Health Ubuntu JARVIS y LILITH OK; cambios ajenos Ubuntu/LILITH preservados.
- Proximo bloque: revisar politica remota por entidad y accion; proponer mitigacion sin desplegar.

## Auditoria nocturna 2026-11-06 04:00
- JARVIS gateway /api/health en puerto 7471: OK STANDBY; LILITH /health puerto 8000: online, DB y MQTT OK.
- Confirmado en codigo: /api/tool/invoke permite lilith_home_action turn_on/turn_off/toggle como SAFE_WRITE tras autenticar, sin confirmacion adicional por entidad. LILITH conserva su propia allowlist, documentada como light/turn_on/turn_off; no se ha probado bypass.
- Propuesta documental: confirmacion explicita para mutaciones HA remotas y allowlist granular por entidad/accion, previa evaluacion del contrato APK; sin desplegar cambios.
- Ubuntu/LILITH sin modificar, SOAK intactos. Siguiente bloque: pruebas hermeticas de politica remota y compatibilidad APK.

## Auditoria nocturna 2026-11-06 05:00
- APK JarvisApi.kt fuente usa /api/chat; sin referencias Kotlin/Java a /api/tool/invoke en el arbol inspeccionado (no prueba APK instalada).
- /api/tool/invoke rechaza DENIED/CONFIRM_REQUIRED, pero SAFE_WRITE permite lilith_home_action y batch_home_action (este ultimo pendiente de inspeccion de despacho).
- Matriz de pruebas remotas propuesta y documentada en WORKLOG; 9 tests aislados PASS, 19 deselected. JARVIS/LILITH health OK.
- Sin modificar Ubuntu/LILITH, SOAK, permisos ni dispositivos. Proximo: auditar batch_home_action y confirmar compatibilidad /api/chat.

## Auditoría 2026-11-06 05:10 — control múltiple por Android
- Revisados ambos canales: `/api/tool/invoke` devuelve HTTP 400 para `batch_home_action` (no existe rama de despacho); `/api/chat` usa el sistema de conversación y puede llegar a `batch_home_action_async`.
- No se identifica un paso de confirmación obligatoria en `_execute_tool` específico del canal Android para `batch_home_action`; LILITH sigue aplicando su allowlist. No afirmar bypass ni efecto físico probado.
- 3 comprobaciones HTTP aisladas PASS y 17 pruebas unitarias de batch PASS. Sin tocar producción.
- Detalle: `REMOTE_BATCH_AUTH_AUDIT_2026-11-06.md`.
- PRÓXIMA TAREA: desarrollar/ejecutar prueba hermética sobre el canal Android y confirmar si existe barrera adicional de confirmación antes de `client.home_action`. Proponer un guard reversible y compatible con APK, pero no cambiar permisos/servicios durante SOAK.

## 2026-11-06 05:15 — Verificación de ruta de confirmación Android (solo lectura)
- Preflight: Windows HEAD 0541b89 limpio; Ubuntu HEAD c5c0516 y LILITH HEAD 9ba6550 con cambios ajenos existentes preservados. Se leyeron HANDOFF, STATUS_SNAPSHOT v12 y WORKLOG antes de actuar.
- Health GET: JARVIS 7471 status=ok/STANDBY; LILITH 8000 status=online, database=true, mqtt=true.
- Confirmado en main.py: _execute_tool_batch llama a _execute_tool_guarded; este guard deriva directamente a _execute_tool si el nombre no pertenece a _SCHEDULED_TOOL_NAMES. batch_home_action llama a batch_home_action_async y no se observa confirmación propia en su rama.
- Resultado: evidencia estática de ausencia de confirmación específica Android para batch_home_action; no equivale a demostrar acción física ni bypass de la allowlist LILITH. No se ejecutaron pruebas de efecto.
- Sin cambios en Ubuntu/LILITH, permisos, servicios, SOAK o Alexa.
- Próximo bloque: test hermético con instancia simulada y llamada a _execute_tool_guarded para batch_home_action; verificar que no llega a home_action si se exige confirmación, antes de proponer parche reversible. No desplegar cambios durante SOAK.

## 2026-11-06 05:40 — Trabajo Android preparado, NO desplegado
- Código Ubuntu actualizado pero servicio NO reiniciado: `main.py` / `api_server.py` / `actions/home_routine.py`; helper `core/android_home_confirmation.py`, tests de política y HTTP E2E simulados.
- Código Kotlin APK preparado con Confirmar/Cancelar, compilación offline satisfactoria; APK NO instalada.
- 197 pruebas unitarias/integración aislada PASS; JARVIS/LILITH online. No acciones físicas.
- Backups y parches individuales: `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/`.
- PENDIENTE: sesión única persistente por instalación Android; ahora JarvisChatRequest usa `session="android"`, compartida entre clientes. Luego validación de concurrentes, despliegue controlado y pruebas físicas.
- Informe: `ANDROID_HOME_CONFIRMATION_2026-11-06.md`.
