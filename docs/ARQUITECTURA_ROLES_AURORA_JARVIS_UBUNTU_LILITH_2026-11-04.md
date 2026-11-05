# Distribución de responsabilidades — AURORA / JARVIS Ubuntu / LILITH
Fecha de referencia: 2026-11-04
Estado: diseño funcional acordado. No equivale a implementación ni a pruebas físicas de todas las funciones.

## Principio
No duplicar capacidades ni memorias persistentes. Cada subsistema conserva su responsabilidad. AURORA Windows y JARVIS Ubuntu son dos interfaces del ecosistema; LILITH es la autoridad del estado doméstico, memoria y rutinas. Coordinar por APIs/puentes, con permisos y resultados verificables.

## 1. AURORA — Windows (C:\JARVIS)
- Interacción de voz y conversación mediante Gemini Live.
- Micrófono, altavoces e interfaz visual local (HUD/avatar).
- Control de teclado, ratón, ventanas, aplicaciones y archivos de Windows.
- Visión/análisis de la pantalla de Windows.
- Música del PC (Spotify, YouTube Music, volumen).
- Integración de agentes de programación y desarrollo del PC, con permisos y confirmaciones.
- Acceso a domótica y memoria persistente mediante las interfaces autorizadas de JARVIS Ubuntu/LILITH.
- No asumir responsabilidad de ejecución 24/7 ni duplicar el núcleo de memoria.

## 2. JARVIS Ubuntu — servicio 24/7 (/home/flako1312/jarvis-headless)
- Conversación y órdenes de voz en Ubuntu, más canal de la APK Android.
- Coordinación/encaminamiento de órdenes hacia LILITH y otros servicios.
- Consultas de información (tiempo, noticias, tráfico, horarios) mediante servicios habilitados.
- Alarmas, temporizadores, avisos, recordatorios, citas, calendario y listas como servicios persistentes donde se implementen.
- Coordinación de música/radio/pódcasts y salida a altavoces domésticos, sin asumir soporte de hardware aún no probado.
- Anuncios de voz e intercomunicación entre habitaciones como función futura.
- Supervisión de recursos, salud y servicios de Ubuntu.
- Activación por palabra «Jarvis» como capacidad por desarrollar/validar en los dispositivos relevantes.
- No crear segundo núcleo de memoria o autoridad domótica independiente de LILITH.

## 3. LILITH Core — memoria, domótica y automatización
- Memoria persistente, preferencias, hechos y contexto autorizado.
- Automatizaciones y rutinas persistentes, con políticas de aprobación y seguridad.
- Estado doméstico y órdenes por Home Assistant.
- Control de dispositivos compatibles: luces, enchufes, persianas, climatización; capacidad individual depende de las entidades realmente integradas.
- Habitaciones, grupos y escenas a través de las entidades compatibles de Home Assistant.
- Eventos de sensores y ejecución programada.
- Registro y verificación de acciones ejecutadas.

## 4. Home Assistant
Capa de integración física. Ejecuta órdenes compatibles sobre dispositivos reales. Matter/Thread/Cast/Google Home requieren integración y, en su caso, hardware o servicios compatibles; no considerarlos ya operativos sin prueba.

## 5. Flujo
Usuario -> AURORA Windows (PC) o JARVIS Ubuntu (voz/Android) -> LILITH cuando es memoria/rutinas/domótica -> Home Assistant para acciones en dispositivos -> resultado verificado -> interfaz originaria.

## 6. Reparto breve
| Capacidad | Responsable |
|---|---|
| Voz y conversación local Windows | AURORA |
| Voz/Android/servicios 24/7 | JARVIS Ubuntu |
| Control del PC, HUD, avatar y visión de pantalla | AURORA |
| Multimedia en PC | AURORA |
| Multimedia en habitaciones | JARVIS Ubuntu |
| Alarmas, calendario, listas y avisos personales | JARVIS Ubuntu, con persistencia y autoridad bien definidas |
| Memoria persistente y preferencias | LILITH |
| Rutinas y automatizaciones de la casa | LILITH |
| Dispositivos físicos | LILITH -> Home Assistant |
| Intercomunicador doméstico | JARVIS Ubuntu |
| Supervisión y logs Ubuntu | JARVIS Ubuntu |

## 7. Política de implementación
- Separar desarrollo, pruebas y despliegue.
- Durante SOAK no modificar ni reiniciar servicios activos sin necesidad y autorización explícita.
- Confirmar cada función con test de software y prueba física cuando corresponda.
- No confundir módulo existente con función operativa.
- Preferir funciones locales y seguras; credenciales y acciones sensibles bajo autorización.
- Esta nota no autoriza por sí misma modificaciones ni despliegues.
