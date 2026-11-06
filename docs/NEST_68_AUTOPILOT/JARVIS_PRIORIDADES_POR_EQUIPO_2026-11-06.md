# JARVIS — prioridades separadas por equipo
**Decisión del usuario:** 6 noviembre 2026. **Alcance:** solo JARVIS/AURORA Windows (`C:\JARVIS`) y JARVIS Ubuntu headless (`/home/flako1312/jarvis-headless`).

## Regla principal
Estas funciones se **descartan de prioridades**, NO se desinstalan, inhabilitan ni eliminan. Conservar el resto de la lista donde sea aplicable. No borrar código, no reiniciar servicios, no instalar APK, no tocar LILITH Core, HA ni SOAK. No interpretar «presente en código» como «probado físicamente». La configuración existente de wakeword/voz no debe alterarse automáticamente.

## JARVIS Windows — despacho
### NO desarrollar ni cerrar como prioridad (13)
1. Consultar manuales y documentación (RAG)
2. Buscar vuelos y precios
3. Tráfico de coches y carreteras
4. Horarios de transporte público
5. Radio por internet
6. Pódcasts
7. Audiolibros
8. Activación por palabra clave
9. WhatsApp, Telegram y mensajes
10. Crear y gestionar citas
11. Listas de la compra
12. Llamadas telefónicas por internet
13. Instalar y actualizar juegos

### PRIORIDADES QUE SE CONSERVAN
**P0 — núcleo y uso inmediato:** conversación Gemini Live por voz (sin nuevos trabajos de wakeword Windows), interrupción/reconexión, análisis de pantalla y cámara si está disponible, teclado, ratón, ventanas, aplicaciones, navegador, archivos, seguridad y recuperación.

**P1 — productividad:** programación y agente de desarrollo de proyectos, tareas multi-paso, Git, búsquedas e investigación profunda, correo Gmail, recordatorios, calendario/agenda (pero NO el módulo específico de crear o gestionar citas), alarmas/temporizadores, notas, memoria de sesión y memoria persistente delegada en LILITH.

**P2 — multimedia y hogar:** Spotify y música local Windows, YouTube, noticias habladas, interfaz visual, volumen, TTS, autorización de acciones, control doméstico y rutinas vía LILITH, estado de LILITH, automatizaciones por eventos preparadas solo desde JARVIS con pruebas simuladas.

## JARVIS Ubuntu — comedor/cocina (24/7)
### NO desarrollar ni cerrar como prioridad (14)
1. Consultar manuales y documentación (RAG)
2. Buscar vuelos y precios
3. Tráfico de coches y carreteras
4. Horarios de transporte público
5. Spotify
6. YouTube y vídeos
7. Radio por internet
8. Pódcasts
9. Audiolibros
10. WhatsApp, Telegram y mensajes
11. Listas de la compra
12. Llamadas telefónicas por internet
13. Escribir, explicar y corregir código
14. Desarrollar proyectos completos

### PRIORIDADES QUE SE CONSERVAN
**P0 — asistente doméstico fijo:** escuchar palabra clave (conservar protecciones existentes, incluida la doble confirmación Alexa), micrófono y altavoces, conversación continua en castellano, barge-in/interrupción, reconexión y estabilidad, TTS, alarmas, temporizadores y recordatorios.

**P1 — hogar y comunicación:** memoria canónica y rutinas **delegadas a LILITH**, autorizaciones domésticas, eventos HA solo en pruebas simuladas hasta integración permitida, mensajes por altavoces/broadcast, noticias habladas, consultas generales y meteorología, correo Gmail, calendario/agenda y creación/gestión de citas si se configura OAuth.

**P2 — apoyo sin duplicar Windows:** música local/volumen (NO Spotify), controles de sistema y salud de Ubuntu, archivos, navegador donde pueda funcionar headless, cámaras si existen, notas, UI/panel si aplica, tareas generales de varios pasos y herramientas auxiliares. No ampliar `code_helper` ni `dev_agent` de Ubuntu por programación o desarrollo de proyectos.

## Distinciones obligatorias
- **Spotify:** SÍ Windows / NO prioridad Ubuntu. Música local y control de volumen siguen en ambos.
- **Palabra clave:** NO prioridad de nuevo desarrollo Windows / SÍ prioridad Ubuntu. No desactivar lo que ya exista.
- **Citas:** NO prioridad Windows / SÍ Ubuntu si dispone de OAuth. **Calendario/agenda** se conserva en ambos.
- **Programación/proyectos:** SÍ Windows / NO prioridad Ubuntu. Las tareas generales multi-paso no se eliminan.
- **RAG de manuales:** fuera de prioridades en ambos; **consultar el estado/documentación del sistema LILITH** se mantiene como función distinta y de solo lectura donde corresponda.
- **Radio, pódcasts, audiolibros, tráfico, vuelos, transporte público, mensajería y compras:** fuera de prioridades en ambos.
- **Audio multiroom (C35):** un HANDOFF anterior decía «descartado por usuario»; la última selección dice «conservar el resto» y NO lo excluye expresamente. **Dejar EN REVISIÓN / sin trabajo autónomo hasta aclaración**, sin borrar código ni desplegar audio.
- **B22/eventos y alarmas entre equipos:** conservar como preparación JARVIS pero no modificar protocolo ni autoridad LILITH sin permiso.
- **Hardware y credenciales:** funciones no utilizables sin dispositivo, OAuth u otra autorización se marcan bloqueadas, no completadas.

## Operación y seguimiento
1. Cada tarea nueva debe seleccionar el **sistema** y comprobar si la función está en su lista «NO prioridad».
2. Si está excluida en ese sistema, no crear nuevas implementaciones, pruebas de cierre ni instalaciones por ella; conservar código existente. Solo corregir un defecto crítico de seguridad/estabilidad si es indispensable para funciones conservadas.
3. Si está conservada, trabajar por pruebas aisladas y checkpoints. Mantener Windows y Ubuntu como dos asistentes fijos, LILITH como única autoridad de memoria persistente y domótica.
4. Preservar cambios locales de otros agentes; no `git clean`, `git reset --hard`, commits indiscriminados ni reescritura de archivos ajenos.
5. Para cualquier reinicio, prueba física de micrófono/altavoz, uso de dispositivos HA, instalación APK o cambio en LILITH Core: esperar autorización explícita del usuario.
6. Este documento regula **prioridades**; `STATUS_SNAPSHOT.json` y tests regulan **estado técnico**, no hay que cambiar porcentajes por preferencias.

*Esta versión sustituye cualquier preferencia por defecto de «tener las mismas herramientas en ambos sistemas».*
