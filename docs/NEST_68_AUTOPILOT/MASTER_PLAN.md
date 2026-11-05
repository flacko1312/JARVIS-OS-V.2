# NEST 68 — Master Plan
Fecha: 2026-11-05 | Proyecto: AURORA/JARVIS Windows + JARVIS Ubuntu + LILITH Core + Home Assistant
Estado: FASE 0 en curso — auditoría inicial completada en AURORA Windows.

---

## Arquitectura de responsabilidades

| Componente | Rol principal | Repositorio |
|---|---|---|
| AURORA/JARVIS Windows | Voz, conversación, PC, multimedia | `C:\JARVIS` (esta máquina) |
| JARVIS Ubuntu Headless | Servicios 24/7, Android APK, música doméstica | `/home/flako1312/jarvis-headless` |
| LILITH Core | Memoria persistente, domótica, rutinas, autoridad | `/home/flako1312/lilith` |
| Home Assistant | Inventario y control físico de dispositivos | Servicio en red local |

Flujo canónico: Usuario → AURORA/JARVIS → LILITH (autorización/memoria/rutinas) → Home Assistant (física) → resultado verificado → respuesta hablada.

---

## Mapa de las 68 capacidades

### BLOQUE A — Voz e inteligencia artificial (1–10)

| # | Capacidad | Responsable | Estado AURORA | Estado Ubuntu | Estado LILITH | Notas |
|---|---|---|---|---|---|---|
| 1 | Reconocimiento de voz | AURORA / Ubuntu | OPERATIVO | DESCONOCIDO | — | Gemini Live STT en Windows; Ubuntu pendiente de verificar |
| 2 | Activación por palabra clave | Ubuntu | PARCIAL (clap gate en Windows) | DESCONOCIDO | — | Protección doble confirmación activa en Alexa; no eliminar |
| 3 | Funciones tipo asistente doméstico | Todos | OPERATIVO (Windows) | DESCONOCIDO | OPERATIVO (via tools) | 49 tools en AURORA; Ubuntu no auditado |
| 4 | Integración Gemini | AURORA | OPERATIVO | DESCONOCIDO | — | google-genai 2.25.0; Gemini Live en Windows |
| 5 | Conversaciones naturales | AURORA / Ubuntu | OPERATIVO | DESCONOCIDO | — | Physical pass en Windows; Ubuntu desconocido |
| 6 | Respuestas a preguntas | AURORA | OPERATIVO | DESCONOCIDO | — | web_search, weather_report, date_time, calculator |
| 7 | Búsquedas de información | AURORA | OPERATIVO | DESCONOCIDO | — | web_search tool, deep_research tool |
| 8 | Ejecución de órdenes habladas | AURORA | OPERATIVO | DESCONOCIDO | — | 49 tools, physical pass JL-A10 |
| 9 | Control doméstico por voz | AURORA→LILITH | OPERATIVO | DESCONOCIDO | DESCONOCIDO | lilith_home_action + LILITH_API_URL confirmado; HA entities accesibles vía LILITH |
| 10 | Conversación Gemini Live | AURORA | OPERATIVO | DESCONOCIDO | — | Physical pass, continuidad persistente validada |

### BLOQUE B — Domótica y automatizaciones (11–24)

| # | Capacidad | Responsable | Estado AURORA | Estado Ubuntu | Estado LILITH/HA | Notas |
|---|---|---|---|---|---|---|
| 11 | Luces inteligentes | LILITH→HA | PARCIAL (tool) | DESCONOCIDO | DESCONOCIDO | lilith_home_action tool; entidades HA sin auditar desde aquí |
| 12 | Enchufes | LILITH→HA | PARCIAL (tool) | DESCONOCIDO | DESCONOCIDO | Misma vía que luces |
| 13 | Persianas/cortinas | LILITH→HA | PARCIAL (tool) | DESCONOCIDO | DESCONOCIDO | Requiere entidades cover.* en HA |
| 14 | Termostatos | LILITH→HA | PARCIAL (tool) | DESCONOCIDO | DESCONOCIDO | Requiere entidades climate.* |
| 15 | Climatización | LILITH→HA | PARCIAL (tool) | DESCONOCIDO | DESCONOCIDO | Misma vía que termostatos |
| 16 | Matter | HA | AUSENTE | AUSENTE | AUSENTE | REQUIERE HARDWARE (Matter Border Router) |
| 17 | Thread | HA | AUSENTE | AUSENTE | AUSENTE | REQUIERE HARDWARE (Thread Border Router) |
| 18 | Integración Google Home | — | BLOQUEADO | BLOQUEADO | BLOQUEADO | API propietaria; no acceso público oficial |
| 19 | Creación y ejecución rutinas | LILITH | OPERATIVO | DESCONOCIDO | DESCONOCIDO | lilith_routine tool, JL-A10 physical pass |
| 20 | Automatizaciones por horarios | LILITH | PARCIAL (tool) | DESCONOCIDO | DESCONOCIDO | Rutinas recurrentes en LILITH; HA automations desconocido |
| 21 | Automatizaciones por voz | AURORA→LILITH | OPERATIVO | DESCONOCIDO | DESCONOCIDO | Vía lilith_routine, physical pass |
| 22 | Automatizaciones por eventos | LILITH→HA | AUSENTE | DESCONOCIDO | DESCONOCIDO | Requiere triggers de sensores HA |
| 23 | Agrupación por habitaciones | LILITH→HA | PARCIAL | DESCONOCIDO | DESCONOCIDO | LILITH puede consultar grupos; sin auditar |
| 24 | Control simultáneo dispositivos | LILITH→HA | PARCIAL | DESCONOCIDO | DESCONOCIDO | Requiere multi-entity support en LILITH |

### BLOQUE C — Audio y multimedia (25–35)

| # | Capacidad | Responsable | Estado AURORA | Estado Ubuntu | Estado global | Notas |
|---|---|---|---|---|---|---|
| 25 | Reproducción de música | AURORA (PC) / Ubuntu (hogar) | OPERATIVO | DESCONOCIDO | PARCIAL | media_control en Windows; Ubuntu sin auditar |
| 26 | Spotify | AURORA | OPERATIVO | DESCONOCIDO | PARCIAL | AEC shadow_v4 activo; physical acceptance pendiente |
| 27 | YouTube Music | AURORA | OPERATIVO | DESCONOCIDO | PARCIAL | media_control, youtube_video tools |
| 28 | Radio por internet | Ubuntu | OPERATIVO | OPERATIVO | PARCIAL | radio_control tool (ffplay, 10 emisoras builtin); validación física altavoces pendiente |
| 29 | Pódcasts | Ubuntu | OPERATIVO | OPERATIVO | PARCIAL | podcast_control tool (iTunes+RSS+ffplay); validación física altavoces pendiente |
| 30 | Audiolibros | Ubuntu | OPERATIVO | OPERATIVO | PARCIAL | audiobook_control tool (LibriVox+ffplay); validación física altavoces pendiente |
| 31 | Noticias habladas | AURORA / Ubuntu | OPERATIVO | OPERATIVO | OPERATIVO | news_control tool (9 feeds RSS curados); no requiere API key |
| 32 | Google Cast | HA | AUSENTE | DESCONOCIDO | DESCONOCIDO | REQUIERE hardware Cast-compatible + HA integration |
| 33 | Audio Bluetooth | Hardware | REQUIERE HARDWARE | REQUIERE HARDWARE | — | Depende de adaptadores físicos |
| 34 | Control volumen y reproducción | AURORA | OPERATIVO | DESCONOCIDO | PARCIAL | computer_settings + media_control en Windows |
| 35 | Reproducción multiroom | Ubuntu / HA | AUSENTE en Aurora | DESCONOCIDO | DESCONOCIDO | Requiere Music Assistant u similar |

### BLOQUE D — Comunicación y avisos (36–40)

| # | Capacidad | Responsable | Estado AURORA | Estado Ubuntu | Notas |
|---|---|---|---|---|---|
| 36 | Llamadas | REQUIERE PROVIDER | BLOQUEADO | DESCONOCIDO | Requiere cuenta SIP/VoIP; no implementar sin provider |
| 37 | Anuncios por altavoces | Ubuntu / AURORA | OPERATIVO (local) | OPERATIVO (local) | broadcast_control TTS local; multiroom HA pendiente validación física |
| 38 | Mensajes Broadcast | Ubuntu | OPERATIVO (local) | OPERATIVO (local) | broadcast_control tool; LILITH relay (command_submit) requiere intent=broadcast en allowlist LILITH |
| 39 | Avisos y notificaciones | AURORA | OPERATIVO | DESCONOCIDO | reminder tool, lilith_routine |
| 40 | Mensajería | AURORA | OPERATIVO | DESCONOCIDO | send_message (WhatsApp, Telegram, etc.) con approval |

### BLOQUE E — Organización personal (41–54)

| # | Capacidad | Responsable | Estado AURORA | Estado Ubuntu | Notas |
|---|---|---|---|---|---|
| 41 | Alarmas | Ubuntu / AURORA | OPERATIVO | OPERATIVO | alarm_control tool (HH:MM, threading.Timer, beep 880Hz, TTS, persistencia JSON); 31 tests |
| 42 | Temporizadores | Ubuntu / AURORA | OPERATIVO | OPERATIVO | timer tool (countdown, threading.Timer, formato HH:MM:SS, registry JSON, TTS); 36 tests |
| 43 | Recordatorios | AURORA | OPERATIVO | DESCONOCIDO | reminder tool |
| 44 | Calendario | AURORA / Ubuntu | PARCIAL | PARCIAL | calendar_control tool (Google Calendar OAuth2); blocker: GCAL_OAUTH_CLIENT_FILE |
| 45 | Citas | AURORA / Ubuntu | PARCIAL | PARCIAL | Cubierto por calendar_control create/search; misma blocker OAuth |
| 46 | Listas de la compra | AURORA / Ubuntu | OPERATIVO | OPERATIVO | shopping_list tool (JSON local, multi-lista, CRUD); sin dependencias externas; 35 tests |
| 47 | Notas | AURORA+LILITH | OPERATIVO | DESCONOCIDO | save_memory + lilith_memory_store |
| 48 | Información meteorológica | AURORA | OPERATIVO | DESCONOCIDO | weather_report tool |
| 49 | Tráfico | AURORA / Ubuntu | PARCIAL | PARCIAL | traffic_info tool (ORS+Nominatim); geocodificación libre; blocker: ORS_API_KEY (gratuita) |
| 50 | Noticias | AURORA / Ubuntu | OPERATIVO | OPERATIVO | news_control tool (9 feeds RSS: RTVE, BBC, Reuters, Xataka...); sin API key; 28 tests |
| 51 | Horarios | AURORA | PARCIAL | DESCONOCIDO | web_search + Gemini; sin integración transporte local |
| 52 | Cálculos | AURORA | OPERATIVO | — | calculator tool |
| 53 | Conversiones de unidades | AURORA | OPERATIVO | — | calculator + Gemini |
| 54 | Traducciones | AURORA | OPERATIVO | — | Gemini Live (nativo multilingüe) |

### BLOQUE F — Conectividad (55–61)

| # | Capacidad | Responsable | Estado | Notas |
|---|---|---|---|---|
| 55 | Wi-Fi 2.4 GHz | Hardware/Router | REQUIERE HARDWARE | Software no controla la banda; HA puede detectar |
| 56 | Wi-Fi 5 GHz | Hardware/Router | REQUIERE HARDWARE | Ídem |
| 57 | Bluetooth | Hardware | REQUIERE HARDWARE | Adaptador Windows detectado pero no integrado con JARVIS |
| 58 | Compatibilidad Cast | Hardware/HA | REQUIERE HARDWARE | Requiere dispositivos Cast y HA integration |
| 59 | Matter | Hardware | REQUIERE HARDWARE | Thread/Matter Border Router necesario |
| 60 | Thread | Hardware | REQUIERE HARDWARE | Ídem |
| 61 | Comunicación red local | AURORA↔LILITH | OPERATIVO | HTTP (LILITH client) + WebSocket (adapter_connector, feature-flagged) |

### BLOQUE G — Herramientas e integraciones (62–68)

| # | Capacidad | Responsable | Estado | Notas |
|---|---|---|---|---|
| 62 | API Google Home oficial | — | BLOQUEADO | No hay API pública gratuita; requiere acceso propietario |
| 63 | Google Script Editor / Automations | — | BLOQUEADO | Ecosistema propietario; sin alternativa directa |
| 64 | Home Assistant | LILITH→HA | OPERATIVO en AURORA | lilith_home_action, aprobaciones; HA sin auditar remotamente |
| 65 | API servicios externos | AURORA | OPERATIVO | web_search, weather, flight_finder, email, Gemini |
| 66 | TTS (síntesis de voz) | AURORA | OPERATIVO | Gemini Live TTS, 24kHz, physical pass |
| 67 | Audio local | AURORA | OPERATIVO | sounddevice WASAPI, estabilidad de dispositivo auditada |
| 68 | Puentes aplicaciones/dispositivos | AURORA↔LILITH | PARCIAL | HTTP LILITH bridge operativo; WebSocket adapter Phase 2 (feature-flagged OFF) |

---

## Resumen de estados por bloque

| Bloque | Total | OPERATIVO | PARCIAL | DESCONOCIDO | AUSENTE | BLOQUEADO | REQUIERE HARDWARE |
|---|---|---|---|---|---|---|---|
| A — Voz/IA | 10 | 7 | 1 | 2 | 0 | 0 | 0 |
| B — Domótica | 14 | 1 | 7 | 4 | 1 | 1 | 0* |
| C — Multimedia | 11 | 6 | 1 | 1 | 0 | 0 | 1 (BT) |
| D — Comunicación | 5 | 4 | 0 | 0 | 0 | 1 | 0 |
| E — Organización | 14 | 10 | 4 | 0 | 0 | 0 | 0 |
| F — Conectividad | 7 | 1 | 0 | 0 | 0 | 0 | 5 |
| G — Herramientas | 7 | 4 | 1 | 0 | 0 | 2 | 0 |
| **Total** | **68** | **33** | **14** | **7** | **1** | **4** | **6** |

*Actualizado 2026-11-05 tras implementación de 10 herramientas nuevas (timer, alarm, radio, podcast, audiobook, broadcast, shopping_list, news, calendar, traffic).*

*Matter/Thread están en AUSENTE (bloque B, filas 16-17) por hardware.

**Nota:** "OPERATIVO" en AURORA no implica operativo en el ecosistema completo. Muchas capacidades requieren LILITH y Ubuntu para ser completas.

---

## Fases de trabajo

| Fase | Nombre | Estado |
|---|---|---|
| 0 | Auditoría | EN CURSO — AURORA auditada; Ubuntu/LILITH requieren acceso SSH |
| 1 | Base común / comunicaciones | PENDIENTE |
| 2 | Voz y conversación | PARCIAL en AURORA; Ubuntu pendiente |
| 3 | Inventario y domótica | PENDIENTE (requiere LILITH/HA) |
| 4 | Multimedia | PARCIAL en AURORA; doméstica pendiente |
| 5 | Organización personal | PARCIAL en AURORA; faltan timer/calendario/tráfico |
| 6 | Comunicación | PARCIAL en AURORA; broadcast/llamadas pendientes |
| 7 | Conectividad e integraciones | BLOQUEADO hardware/propietario excepto LAN |
| 8 | Integración completa | PENDIENTE |
| 9 | Auditoría general | PENDIENTE |
| 10 | Pruebas finales | PENDIENTE |

---

## Próxima acción recomendada

**Fase 0 continua:** Acceso SSH a Ubuntu y LILITH para completar auditoría remota.
Mientras Ubuntu/LILITH no estén accesibles, trabajar en:
- Implementar timer tool en AURORA (Bloque E, #42 — AUSENTE)
- Preparar integración calendario (Google Calendar OAuth, Bloque E, #44-45)
- Preparar integración tráfico (Bloque E, #49)
- Habilitar WebSocket adapter_connector (Phase 2, feature flag)
- Implementar radio/pódcasts en Ubuntu (cuando accesible)
