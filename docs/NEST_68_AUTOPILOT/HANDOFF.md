# HANDOFF — Instrucciones para reanudar el trabajo

Última actualización: 2026-11-05 (sesión 3 — integración real + auditoría 68)
Checkpoint: Integración AURORA↔LILITH verificada. 10 herramientas desplegadas. 33/68 OPERATIVO.

---

## Para reanudar al escribir «CONTINÚA»

1. Leer este archivo (HANDOFF.md).
2. Leer MASTER_PLAN.md para ver el estado actual de las 68 capacidades.
3. Leer STATUS_SNAPSHOT.json para el resumen ejecutivo.
4. Ejecutar `git -C C:\JARVIS log --oneline -5` para ver últimos commits.
5. Continuar con la siguiente tarea pendiente (sección abajo).

---

## Estado actual del ecosistema (2026-11-05)

### AURORA/JARVIS Windows — 59 tools, branch codex/neural-voice-visual
- 33/68 capacidades OPERATIVO
- 324/324 tests pasan en tools nuevos
- LILITH_API_URL=http://192.168.1.50:8000 — configurado y verificado
- Todos los endpoints `/api/v1/integration/*` autenticados funcionando

### JARVIS Ubuntu Headless — `/home/flako1312/jarvis-headless`
- 324/324 tests pasan en tools nuevos + 3/3 ToolContractTests
- Puerto 8000: API principal (Gemini Live headless)
- Puerto 7471: Android APK gateway — ahora con 81 reglas de permisos para 10 tools nuevos
- `core/headless_permissions.py` — actualizado con permisos para todos los tools nuevos

### LILITH Core — Docker `lilith_core`, puerto 8000
- Estado: RUNNING, healthy, database+mqtt+kernel+home_assistant=true
- API de integración: `/api/v1/integration/*` — todos los endpoints respondiendo
- Broadcast intent NO en allowlist del token JARVIS (HTTP 403)

### Home Assistant — Docker `homeassistant/home-assistant:stable`
- Accesible vía LILITH `/api/v1/integration/home/*`
- Entidades físicas sin auditar desde JARVIS

---

## Herramientas implementadas esta sesión

| Tool | Tests | Estado | Notas |
|------|-------|--------|-------|
| timer | 36 | OPERATIVO | countdown, registry JSON, TTS |
| alarm_control | 31 | OPERATIVO | HH:MM, beep 880Hz, TTS |
| shopping_list | 35 | OPERATIVO | JSON local, multi-lista, CRUD |
| news_control | 28 | OPERATIVO | 9 feeds RSS, sin API key |
| radio_control | 31 | OPERATIVO (código) | ffplay, 10 emisoras; pendiente altavoces |
| podcast_control | 26 | OPERATIVO (código) | iTunes+RSS+ffplay; pendiente altavoces |
| audiobook_control | 31 | OPERATIVO (código) | LibriVox+ffplay; pendiente altavoces |
| broadcast_control | 20 | OPERATIVO (local) | TTS local OK; relay LILITH bloqueado |
| calendar_control | 42 | PARCIAL | código OK; blocker GCAL_OAUTH |
| traffic_info | 45 | PARCIAL | código OK; blocker ORS_API_KEY |

---

## Tareas pendientes (en orden de prioridad)

### 1. Validación física de audio (requiere altavoces)
- C28/C29/C30 (radio/podcast/audiobook): probar `ffplay` con altavoces conectados
- E41 (alarmas): probar sonido beep 880Hz
- D37/D38 (broadcast): probar TTS local

### 2. Desbloqueadores del usuario
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
