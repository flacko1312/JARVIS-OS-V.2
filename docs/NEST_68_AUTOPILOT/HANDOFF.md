# HANDOFF — Instrucciones para reanudar el trabajo

Última actualización: 2026-11-05 (sesión 6 — home_routine P3, auditoría Ubuntu HEADLESS_SYSTEM_RULES, entidades HA en vivo)
Checkpoint: 45/68 OPERATIVO. AURORA 63 tools, Ubuntu 73 tools.

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

### JARVIS Ubuntu Headless — `/home/flako1312/jarvis-headless` — 73 tools
- 79/79 tests pasan + 3/3 ToolContractTests
- Puerto 7471: Android APK gateway — 87 reglas de permisos para 13 tools (añadido home_routine)
- HEADLESS_SYSTEM_RULES reescrito sesión 6: lista completa de tools incluyendo todos los nuevos
- home_routine desplegado: SCP + lazy import + dispatch + qa_audit + headless_permissions

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

### 0. Completado en sesiones 5-6
- transport_schedules: disclaimer DATOS ESTÁTICOS ✓
- STATUS_SNAPSHOT v7→v8: contadores corregidos ✓
- OPERATIVO_VERIFICATION.md: tabla auto-test/integration/physical ✓
- home_routine P3: 5 rutinas, 30 tests, AURORA+Ubuntu ✓
- HEADLESS_SYSTEM_RULES: reescrito con todos los tools ✓
- Auditoría HA en vivo: 6 entidades auditadas (1 AVAILABLE) ✓

### 1. P2 — Integración memoria LILITH en conversación (PENDIENTE)
- Verificar que Ubuntu conversation loop llama lilith_memory_search/store
- Testear persistencia: guardar algo → reiniciar → recuperar
- Verificar que `memory_authority` en HEADLESS_SYSTEM_RULES guía el comportamiento real

### 2. Validación física de audio (requiere altavoces)
- C28/C29/C30 (radio/podcast/audiobook): probar `ffplay` con altavoces conectados
- E41 (alarmas): probar sonido beep 880Hz
- D37/D38 (broadcast): probar TTS local

### 3. Desbloqueadores del usuario
- **GCAL_OAUTH**: Colocar archivo OAuth JSON en `C:\JARVIS\config\gcal_client.json` → E44/E45 pasan a OPERATIVO
- **ORS_API_KEY**: Registrar en openrouteservice.org (gratis) → decir "configura tráfico api_key=TU_CLAVE" → E49 OPERATIVO
- **LILITH broadcast allowlist**: Pedir al equipo LILITH añadir `broadcast` a allowed intents → D38 relay completo

### 3. Capacidades DESCONOCIDO en Ubuntu a verificar
- B19/B21 (rutinas LILITH): verificar si jarvis-headless tiene `lilith_routine` tool
- C25-C27 (música/Spotify/YTMusic): media_control en Ubuntu headless
- E43 (recordatorios): reminder tool en Ubuntu

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
