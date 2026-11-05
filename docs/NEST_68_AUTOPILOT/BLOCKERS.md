# BLOCKERS — Limitaciones de hardware, credenciales y autorizaciones

Última actualización: 2026-11-05

---

## Categoría: REQUIERE HARDWARE

| # | Capacidad | Hardware necesario | Estado |
|---|---|---|---|
| B16 | Matter | Matter Border Router (p.ej. Google Nest Hub 2nd gen, Apple TV 4K, Amazon Echo 4ª gen) | No detectado en auditoría |
| B17 | Thread | Thread Border Router (mismo hardware que Matter usualmente) | No detectado |
| C32 | Google Cast | Dispositivos Chromecast/Cast-enabled + HA Cast integration | Desconocido |
| C33 | Bluetooth audio | Adaptador BT en Ubuntu con sink compatible | Desconocido |
| C35 | Multiroom audio | Altavoces compatibles con Music Assistant o similar | Desconocido |
| F55-60 | WiFi/BT/Matter/Thread/Cast | Ver filas anteriores | — |

**Acción cuando el usuario regrese:** verificar qué hardware está disponible en la vivienda. HA puede listar dispositivos detectados.

---

## Categoría: REQUIERE CREDENCIALES / OAUTH

| # | Capacidad | Servicio | Acción necesaria |
|---|---|---|---|
| E44-45 | Calendario/Citas | Google Calendar API | Crear proyecto GCP, OAuth consent screen, credenciales OAuth2, compartir con .env |
| E49 | Tráfico | Google Maps API, HERE Maps, o OpenRouteService | API key (OpenRouteService es gratuito con límites) |
| C32 | Cast control | Google Cast SDK o HA Google Cast integration | Config HA + network discovery |
| D36 | Llamadas VoIP | Proveedor SIP (p.ej. VoIP.ms, Twilio, 3CX) | Cuenta + credenciales SIP |

**Código preparado / pendiente de credenciales:**
- Calendario: estructura `actions/calendar_control.py` (por crear) — OAuth flow listo para implementar
- Tráfico: estructura `actions/traffic_info.py` (por crear) — API key placeholder

---

## Categoría: BLOQUEADO (API PROPIETARIA)

| # | Capacidad | Razón | Alternativa viable |
|---|---|---|---|
| B18 | Google Home API | Sin acceso público gratuito oficial | Home Assistant como capa de integración (ya disponible) |
| G62 | Google Home API oficial | Ídem | Ídem |
| G63 | Google Script Editor | Ecosistema cerrado | Automatizaciones locales via LILITH + HA |
| A2 | Google Assistant | Sin SDK público para custom voice assistant | Gemini Live (ya implementado) como equivalente funcional |

---

## Categoría: REQUIERE ACCESO REMOTO (SSH/Tailscale)

| Componente | Acción necesaria | Impacto |
|---|---|---|
| JARVIS Ubuntu (`/home/flako1312/jarvis-headless`) | Auditar estado, servicios activos, capacidades Gemini Live en Ubuntu | Capacidades A1,A2,A3,A5 en Ubuntu desconocidas |
| LILITH Core (`/home/flako1312/lilith`) | Auditar API, memoria, rutinas, HA integration, WebSocket server | Capacidades B-E-G desconocidas |
| Home Assistant | Auditar entidades, integraciones, dispositivos | Bloque B casi completo desconocido |
| Ubuntu: jarvis-headless | Verificar alarmas, radio, multiroom, pódcasts | E41, C28-30, C35 desconocidos |

---

## Categoría: REQUIERE AUTORIZACIÓN EXPLÍCITA DEL USUARIO

| Acción | Razón |
|---|---|
| Habilitar WebSocket adapter (ADAPTER_CONNECTION_ENABLED=true) | Modifica comunicación con LILITH en producción |
| Ampliar permisos de entidades HA | Historial de entidades no disponibles; verificar antes de ampliar |
| Instalar Music Assistant en HA | Modifica instancia HA activa |
| Configurar TTS broadcast en altavoces domésticos | Requiere hardware y config de red |
| Desplegar cambios en Ubuntu/LILITH | Servicios 24/7 activos; backup obligatorio previo |

---

## Estado actual de SOAK

Según PROJECT_STATE.md:
- El soak final de 24h está **DIFERIDO** hasta que AURORA, Ubuntu Headless, Monitor y la baseline de integración estén congelados.
- **NO interrumpir servicios activos mientras el soak está pendiente.**
- Spotify AEC shadow_v4 en Windows: physical acceptance pendiente (no bloquea desarrollo).
