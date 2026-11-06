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
- Sesión Android por instalación implementada en el código: JarvisRepository toma el UUID persistente de SettingsStore y usa el mismo session para chat/confirm/cancel; compilación Kotlin offline PASS. Pendiente validar en la APK instalada. Próximo: pruebas de concurrencia, despliegue seguro y pruebas físicas.
- Informe: `ANDROID_HOME_CONFIRMATION_2026-11-06.md`.

## 2026-11-06 — Cambio de alcance y detección pasiva de audio Ubuntu
- Decisión del usuario: NEST 68 tiene DOS asistentes fijos: Windows despacho y Ubuntu comedor/cocina. Micrófono y altavoces conectados en Ubuntu. La APK Android queda FUERA del objetivo; no desarrollar/probar/desplegar APK, no borrar archivos previos. Los últimos checkpoints 05:40/05:45 sobre Android son trabajo externo anterior a esta decisión; no continuarlo.
- Preflight completo: HANDOFF, STATUS_SNAPSHOT v12, WORKLOG y Git de Windows, jarvis-headless, lilith. Windows HEAD 444af71 limpio; Ubuntu HEAD c5c0516 con numerosos archivos modificados/sin seguimiento (incluidos cambios Android recientes), LILITH HEAD 9ba6550 con cambios locales: todos preservados.
- Comprobación pasiva sin grabar/reproducir: `arecord -l` detecta USB Microphone (card 1, device 0), con 0/1 subdispositivos libres en el momento de la consulta (ocupado, no diagnostica fallo). `aplay -l` detecta salida analógica Intel ALC3234 y HDMI, además de USB Audio; no confirma qué altavoz está conectado ni salida predeterminada. `pactl info` no devolvió campos Default Sink/Source, pendiente verificar contexto del servidor de sonido. No se ha capturado ni reproducido audio.
- Health GET JARVIS 7471: ok/STANDBY. LILITH 8000: online, database=true, mqtt=true.
- Lista de pruebas físicas para usuario: (1) confirmar salida y fuente predeterminadas en sesión de audio real; (2) prueba corta de reproducción audible; (3) prueba breve de captura con consentimiento; (4) wake word y respuesta TTS sin música y con música; (5) conversación contextual y memoria entre sesiones; (6) home_routine con simulación y, solo con permiso, dispositivos HA reales; (7) alarmas/radio/podcast; (8) multiroom y automatizaciones por eventos únicamente tras autorización y preparación. No ejecutar pruebas físicas automáticamente.
- Siguiente bloque autónomo: identificar en lectura la pila de audio activa y comprobar configuración de captura/salida sin grabar ni reproducir, o ampliar tests herméticos de voz. Evitar alterar SOAK, servicios, permisos y cambios ajenos.

## 2026-11-06 06:05 — Listo para ventana de despliegue autorizada
- **NO reiniciar ni instalar hasta que el usuario lo indique.** Los servicios siguen vivos; toda la protección de confirmaciones nueva existe solo en código en disco.
- Corregida carrera simultánea que filtraba estado `telegram_confirmed`; ahora aprobación Android aislada por tarea, serializada con chat, origen de canal explícito. Android pendiente por propietario; snapshot profundo de argumentos.
- **249 pruebas PASS** (7 warnings) y APK Debug de 18 MiB generada, firma v2 verificada. APK: `/home/flako1312/apk_nueva_src/app/build/outputs/apk/debug/app-debug.apk`. SHA-256 `76519a12b2cb1e55e184f2f2fd64a6c3ae781402395a62f0aeda84d3cbb9ae56`.
- Backups originales + parches: `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/`. Ubuntu/APK siguen con modificaciones anteriores; no comprometerlas con commits masivos, reset o clean.
- Informe de estado para reanudación: `ANDROID_CONFIRMATION_CONCURRENCY_2026-11-06.md`. Próximo bloque: SOLO lectura de condiciones SOAK, planificar reinicio controlado cuando el usuario lo autorice y pruebas APK bajo supervisión.

## 2026-11-06 06:05 — Artefacto APK preservado
- Copia independiente de la APK debug firmada (18 MiB) junto con checksum SHA-256 en `/home/flako1312/jarvis-headless-backups/android_home_confirm_20261106_0535/apk/jarvis-confirmation-debug-20261106.apk` y `.sha256`.
- Copiados los helpers y tests nuevos al directorio de resguardo. Hash coincide con la APK generada. Sin reinicio ni instalación.

## 2026-11-06 06:10 - JARVIS exclusivo: prioridad del usuario
- Trabajar SOLAMENTE en JARVIS Windows (C:\JARVIS) y JARVIS Ubuntu (/home/flako1312/jarvis-headless). No APK, no LILITH Core, no hitos M-3 a M-9, no cambios Home Assistant; el usuario dirá cuándo reiniciar.
- Documento de cierre honesto: docs/NEST_68_AUTOPILOT/JARVIS_ONLY_EXIT_CRITERIA_2026-11-06.md. No copiar conteos más antiguos de MASTER_PLAN sin revisión.
- Test de herramientas: Ubuntu 259/259 PASS y Windows 260/260 PASS (Windows timer TTS corregido, commit 333625b). Conversación: Windows 102 PASS, Ubuntu 100 PASS. Test AST de despacho Gemini PASS en ambos.
- Ubuntu tiene modificaciones previas sin seguimiento; no reiniciar, resetear, limpiar, hacer git add masivo ni tocar LILITH.
- Próximo: pruebas simuladas de voz y reconexión, comparación de herramientas declaradas y errores reales de software.

## 2026-11-06 06:20 - JARVIS software voice tests PASSED
- Windows voice/reconnection/audio-routing unit suite 115/115 PASS. Ubuntu wakeword/barge-in/voice-stability/live-session unit suite 150/150 PASS. No hardware tests performed; these results do not mark G67 as physical PASS.
- Windows Git latest for JARVIS-only closeout: 3b6b91c (criteria + AST dispatch test), preceded by 333625b (timer speech first). Ubuntu isolated static dispatch test committed d5a1db8, preserving ~60 unrelated modified/untracked entries.
- Authoritative JARVIS-only closure document: docs/NEST_68_AUTOPILOT/JARVIS_ONLY_EXIT_CRITERIA_2026-11-06.md.
- Do not restart production or modify APK, LILITH, HA. Prioritize software validation and prepare only supervised physical tests as final blockers.

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

## 2026-11-06 12:00 — C35 sesion cruzada
- Seis pruebas hermeticas nuevas para aislamiento de sesiones; 58/58 PASS total C35.
- C35 NO operativo: sin transporte ni audio fisico.
- Proximo bloque: correlacion de ACK/replays y especificacion de transporte seguro sin despliegue.

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

## Checkpoint 2026-11-06 — cierre B22/C35 seguro
- Windows: nuevo `core/ha_event_processor_dry_run.py` y `tests/test_ha_event_processor_dry_run.py`; 18 pruebas B22 dirigidas PASS junto con los evaluadores previos.
- B22 queda AUSENTE: el procesador solo valida, deduplica, registra y propone IDs. No hay suscripción HA, ejecución de rutinas ni llamadas mutantes a LILITH.
- C35: batería multiroom hermética 110 PASS en `C:\JARVIS\.venv`; sigue AUSENTE físicamente. Los módulos cubren planificación, handshake, ACK, HMAC de prueba, expiración y sincronización simulada, pero no transporte real ni audio.
- Snapshot v13: 43 OPERATIVO, 9 PARCIAL, 2 AUSENTE, 4 BLOQUEADO, 10 REQUIERE_HARDWARE. Esta partición es la clasificación conservadora y exclusiva de 68 IDs.
- Ubuntu: no sobrescribir, no resetear, no limpiar; conserva sus modificaciones/untracked. Servicios observados en STANDBY/healthy, sin reinicios en este bloque.
- Siguiente bloque seguro: revisión estática de voz/dispatcher y pruebas dirigidas restantes en `.venv`; cualquier integración HA, transporte multiroom, audio físico o cambio de permisos requiere ventana/autorización separada.
- Verificación Ubuntu adicional: `py_compile` de `main.py`, `actions/home_routine.py` y `actions/transport_schedules.py` PASS; batería disponible 172/172 PASS. No existe `tests/test_home_routine.py` en Ubuntu, por lo que la rutina no se declara probada automáticamente allí.
- B22 bridge: `core/ha_event_bridge.py` y sus dependencias fueron copiados como archivos nuevos a Ubuntu; 23/23 pruebas PASS en ambos lados. Solo verifica `routines.get`; no ejecuta rutinas porque LILITH no expone un intent de ejecución por eventos.
- C35 transport: `core/multiroom_transport.py` fue copiado como archivo nuevo a Ubuntu; 4/4 pruebas TCP loopback PASS allí y 114/114 multiroom PASS en Windows. El transporte no está arrancado por ningún servicio, no lleva audio y requiere provisión coordinada de claves antes de cualquier despliegue real.
- Regresión Windows de voz/dispatcher: 68/68 PASS. Ubuntu: las pruebas que importan `main.py` siguen bloqueadas en colección por `numpy` ausente; no instalar dependencias durante SOAK ni declarar voz Ubuntu certificada por ese motivo.
- Corrección del diagnóstico: el `.venv` de Ubuntu sí contiene `numpy 2.5.4`; con `/home/flako1312/jarvis-headless/.venv/bin/python`, las pruebas de voz/sesión/wake/transcripción pasan 82/82. El fallo solo afecta al Python global y no al entorno del servicio validado.

## 2026-11-06 15:55 — B22 idempotencia por evento (automatización)
- Detectado defecto: `HAEventBridge.inspect_event` reutilizaba `request_id` e `idempotency_key` por `routine_id`, incluso para eventos HA distintos; podía confundir lecturas de verificación en el servicio remoto.
- Corregido: identificador determinista basado en hash del ID del evento (o contenido cuando falta) + ID de rutina. No ejecuta rutinas ni acciona dispositivos.
- Nueva regresión `tests/test_ha_event_request_identity.py`: IDs distintos para eventos distintos y deduplicación de reenvíos.
- Suite dirigida Windows: 16/16 PASS (bridge, identidad, procesador, transporte). Ubuntu inspeccionado sin cambios; modificaciones ajenas preservadas. SOAK y servicios sin reiniciar.
- B22 sigue AUSENTE como automatización real: LILITH no expone intent autorizado de ejecución. C35 sigue AUSENTE como audio multiroom físico.
- Próximo: validar manejo de errores de `command_submit` en bridge sin ejecutar rutinas y endurecer transporte TCP frente a frames incompletos.

## 2026-11-06 16:59 — C35 TCP: rechazo de frames incompletos
- Preflight: consultados STATUS_SNAPSHOT, MASTER_PLAN, HANDOFF, WORKLOG y Git Windows/Ubuntu. Windows HEAD c409a03 con backup ajeno untracked preservado; Ubuntu HEAD f61f9ec con modificaciones/untracked ajenos preservados.
- Detectado defecto real en core/multiroom_transport.py: readline() aceptaba un JSON firmado terminado por EOF sin delimitador de nueva línea. Ahora servidor y cliente exigen frame completo (newline) y longitud máxima de 16384 bytes; fallan cerrado ante truncamiento.
- Nueva regresión tests/test_multiroom_incomplete_frames.py: EOF sin newline en solicitud y respuesta, ambas rechazadas. Pruebas dirigidas 6/6 PASS; git diff --check exit 0 (aviso no bloqueante de conversión LF/CRLF).
- No se inició transporte productivo, audio, HA, LILITH, servicios ni SOAK. Ubuntu no se modificó. C35 continúa AUSENTE como multiroom físico; este cambio solo endurece transporte de control Windows.
- Próximo bloque: revisar excepciones de callback y lectura de frames sobredimensionados; verificar compatibilidad y preparar despliegue coordinado cuando se autorice.

## 2026-11-06 17:57 — C35 TCP: errores de callback aislados
- Preflight: leidos STATUS_SNAPSHOT v13, MASTER_PLAN, HANDOFF, WORKLOG y estados Git de Windows y Ubuntu. Backup Windows sin seguimiento y todos los cambios Ubuntu preservados.
- Defecto: excepciones del callback TCP y respuestas no serializables podian cerrar la conexion sin ACK de rechazo; corregido en core/multiroom_transport.py para responder fail-closed y mantener servidor disponible. Cancelaciones no capturadas (asyncio.CancelledError).
- Nuevas pruebas tests/test_multiroom_callback_failures.py: excepcion del callback y respuesta no serializable; junto con TCP e incomplete frames: 8/8 PASS en venv Windows; git diff --check OK (aviso LF/CRLF).
- No se toco Ubuntu, LILITH, HA, APK, SOAK, servicios ni audio fisico. C35 sigue AUSENTE en produccion por falta de despliegue/audio/sincronizacion y autorizacion. Siguiente: limitar lectura de frames sobredimensionados y verificar compatibilidad Windows-Ubuntu sin modificar archivos ajenos.
