# HANDOFF — Instrucciones para reanudar el trabajo

Última actualización: 2026-11-05
Checkpoint: Fase 0 (auditoría) completada en AURORA Windows. Resto del ecosistema pendiente de auditoría remota.

---

## Estado del repositorio al crear este checkpoint

- Rama activa: `codex/neural-voice-visual`
- Último commit: `37b3b35` — feat(adapter): add Phase 2 WebSocket connector client for AURORA Windows
- Tests: 1463 passed, 93 skipped, 0 failures
- Archivo sin seguimiento: `docs/ARQUITECTURA_ROLES_AURORA_JARVIS_UBUNTU_LILITH_2026-11-04.md`

## Para reanudar al escribir «CONTINÚA»

1. Leer este archivo (HANDOFF.md).
2. Leer MASTER_PLAN.md.
3. Leer STATUS.json.
4. Ejecutar `git -C C:\JARVIS status` y `git -C C:\JARVIS log --oneline -5`.
5. Comparar con el estado registrado aquí.
6. Identificar cambios realizados desde este checkpoint.
7. Continuar por la siguiente tarea pendiente de la lista de trabajo inmediato (sección 4 abajo).
8. No repetir la auditoría de AURORA — ya está completa.

---

## Resumen ejecutivo del estado actual

### AURORA/JARVIS Windows — auditado

**Capacidades OPERATIVAS confirmadas (con evidencia):**
- Voz/conversación: Gemini Live STT/TTS, continuidad persistente, VAD 2500ms (physical pass)
- 49 herramientas registradas, todas con dispatch path
- LILITH HTTP client: JL-W001 a JL-W006 completos
- Rutinas: `lilith_routine` JL-A10 physical pass
- Multimedia PC: media_control, Spotify AEC shadow_v4
- Visión: screen_process physical pass; cámara pendiente
- Comunicación: send_message (WhatsApp/Telegram/Discord/iMessage), email_control (Gmail OAuth)
- Recordatorios: reminder tool
- Domótica: lilith_home_action tool (UI operativa; HA entities requieren verificación)
- Organización: weather_report, calculator, web_search, deep_research, notas

**Capacidades AUSENTES en AURORA que deben implementarse:**
- Temporizador (E42) — no hay tool timer dedicado
- Calendario/Citas (E44, E45) — requiere integración Google Calendar o CalDAV
- Tráfico (E49) — requiere API externa

**Capacidades PARCIALES en AURORA:**
- WebSocket adapter Phase 2: implementado (`lilith_client/adapter_connector.py`) pero ADAPTER_CONNECTION_ENABLED=false. Listo para habilitar cuando LILITH lo soporte.

### Resto del ecosistema — NO AUDITADO

Ubuntu, LILITH y HA requieren acceso SSH para auditar. Los estados marcados como DESCONOCIDO en STATUS.json son reales desconocidos, no problemas conocidos.

---

## Lista de trabajo inmediato (prioridad)

### Tarea inmediata 1: Implementar tool `timer` en AURORA
- **Estado**: AUSENTE → por implementar
- **Archivo**: crear `actions/timer.py`, registrar en `main.py`
- **Especificación**: crear timer, listar timers activos, cancelar timer
- **Sin dependencias de Ubuntu/LILITH**: puede implementarse ahora
- **Tests**: crear `tests/test_timer.py`

### Tarea inmediata 2: Preparar integración calendario
- **Estado**: AUSENTE → preparar estructura
- **Opciones**: Google Calendar API (OAuth) o CalDAV local
- **Acción**: crear `actions/calendar_control.py` con OAuth flow, registrar tool
- **Blocker**: requiere Google Calendar OAuth credentials del usuario

### Tarea inmediata 3: Preparar integración tráfico
- **Estado**: AUSENTE → preparar
- **Opciones**: Google Maps API, HERE Maps, OpenRouteService (gratuito)
- **Acción**: crear `actions/traffic_info.py`
- **Blocker**: requiere API key

### Tarea inmediata 4: Habilitar WebSocket adapter_connector
- **Estado**: PARCIAL → Phase 2 implementado, feature-flagged
- **Acción**: verificar que LILITH soporta el protocolo WebSocket, luego cambiar ADAPTER_CONNECTION_ENABLED=true en .env
- **Blocker**: requiere acceso a LILITH para verificar servidor WS

### Tarea inmediata 5: Auditoría SSH Ubuntu/LILITH
- **Estado**: DESCONOCIDO → requiere conexión remota
- **Acción**: SSH a Ubuntu, leer estructura jarvis-headless y lilith, verificar servicios
- **Blocker**: requiere credenciales SSH / Tailscale activo

---

## Configuración de entorno conocida

```
# Variables .env activas en C:\JARVIS:
GEMINI_API_KEY=<set, never backup>
LILITH_API_URL=<LAN address>
LILITH_API_KEY=<token part only>
ADAPTER_CONNECTION_ENABLED=false  # Phase 2 WebSocket, OFF por defecto
JARVIS_LIVE_VAD_SILENCE_MS=2500   # Validado físicamente
JARVIS_SPOTIFY_FILTER_MODE=shadow_v4  # AEC activo
```

## Acceso a Ubuntu/LILITH

- Servidor Ubuntu: `server-lilith` (hostname conocido; verificar IP actual con Tailscale)
- Repositorios:
  - JARVIS Ubuntu: `/home/flako1312/jarvis-headless`
  - LILITH Core: `/home/flako1312/lilith`
- Acceso: SSH con clave `~/.ssh/id_ed25519` o Tailscale

## Precauciones obligatorias

- NO interrumpir servicios SOAK activos en Ubuntu/LILITH
- NO modificar configuraciones de Tailscale/SSH sin vía de recuperación
- NO resetear memoria persistente de LILITH
- NO eliminar entidades HA sin auditar primero su estado
- Protección doble confirmación de Alexa: NO eliminar hasta tener alternativa probada
- WebSocket adapter: NO habilitar en producción sin verificar soporte LILITH
