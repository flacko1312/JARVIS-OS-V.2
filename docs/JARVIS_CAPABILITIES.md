# JARVIS — Capability Catalogue

Generated: 2026-10-16 15:28:35
JARVIS commit: `500b14d`

## Summary

- **Total registered tools**: 48
- **Available capabilities**: 35
- **Disabled**: 0
- **Pending physical validation**: 1
- **Require approval**: 5
- **LILITH delegated**: 5

---

## Windows

### Open applications / Abrir aplicaciones

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `open_app`

**Can**:
- Open supported Windows applications
- Launch programs by name

**Side effects**: Yes

**Example requests**:
- "Abre Chrome."
- "Abre Spotify."
- "Abre la calculadora."

*Search: open, abrir, launch, lanzar, app, aplicación, programa*

---

### Keyboard control / Control del teclado

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `computer_control`
- `computer_settings`

**Can**:
- Type text / Escribir texto
- Press keys / Presionar teclas
- Use keyboard shortcuts / Atajos de teclado
- Copy / Copiar
- Paste / Pegar

**Side effects**: Yes
**Physical validation**: ✅ Validated

**Example requests**:
- "Escribe 'Hola mundo'."
- "Presiona Ctrl+C."
- "Copia esto."

*Search: keyboard, teclado, type, escribir, tecla, key, copy, copiar, paste, pegar, shortcut, atajo, hotkey*

---

### Mouse control / Control del ratón

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `computer_control`

**Can**:
- Click / Hacer clic
- Double-click / Doble clic
- Right-click / Clic derecho
- Move cursor / Mover cursor
- Scroll / Desplazar

**Side effects**: Yes

**Example requests**:
- "Haz clic en el botón aceptar."
- "Desplázate hacia abajo."

*Search: mouse, ratón, click, clic, cursor, scroll, desplazar*

---

### Window management / Gestión de ventanas

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `computer_settings`
- `computer_control`

**Can**:
- Close windows / Cerrar ventanas
- Focus windows / Enfocar ventanas
- Fullscreen / Pantalla completa
- Minimize / Minimizar

**Side effects**: Yes
**Physical validation**: ✅ Validated

**Example requests**:
- "Cierra Spotify."
- "Pon Chrome en pantalla completa."

*Search: window, ventana, close, cerrar, focus, enfocar, fullscreen, pantalla completa, minimize, minimizar*

---

### System settings / Configuración del sistema

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `computer_settings`

**Can**:
- Adjust volume / Ajustar volumen
- Adjust brightness / Ajustar brillo
- Dark mode / Modo oscuro
- WiFi control
- Lock screen / Bloquear pantalla
- Restart / Reiniciar
- Shutdown / Apagar

**Side effects**: Yes
**Approval required**: Yes

**Example requests**:
- "Sube el volumen."
- "Activa el modo oscuro."
- "Bloquea la pantalla."

*Search: volume, volumen, brightness, brillo, dark mode, modo oscuro, wifi, lock, bloquear, restart, reiniciar, shutdown, apagar, settings, configuración*

---

### Date and time / Fecha y hora

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `date_time`

**Can**:
- Read current date / Leer fecha actual
- Read current time / Leer hora actual


**Example requests**:
- "¿Qué hora es?"
- "¿Qué día es hoy?"

*Search: date, fecha, time, hora, clock, reloj, today, hoy*

---

### Desktop control / Control del escritorio

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `desktop_control`

**Can**:
- Change wallpaper / Cambiar fondo
- Organize desktop / Organizar escritorio
- List desktop items / Listar elementos
- Desktop statistics / Estadísticas

**Side effects**: Yes

**Example requests**:
- "Cambia el fondo de pantalla."
- "Organiza mi escritorio."

*Search: desktop, escritorio, wallpaper, fondo, organize, organizar*

---

## Vision / Visión

### Screen capture and analysis / Captura y análisis de pantalla

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `screen_process`

**Can**:
- Capture the current screen / Capturar la pantalla
- Analyze visible content / Analizar contenido visible
- Help identify visible errors / Identificar errores visibles

**Physical validation**: ✅ Screen validated; Camera pending

**Example requests**:
- "Mira qué error tengo en pantalla."
- "Analiza lo que estoy viendo."
- "¿Qué se ve en mi pantalla?"

*Search: screen, pantalla, screenshot, captura, vision, visión, see, ver, look, mirar, analyze, analizar*

---

### Camera / Cámara

**Status**: 🟡 PENDING PHYSICAL VALIDATION
**Authority**: JARVIS

**Tools**:
- `screen_process`

**Can**:
- Capture webcam image / Capturar imagen de cámara
- Analyze what the camera sees / Analizar lo que ve la cámara

**Physical validation**: 🟡 Pending physical validation

**Example requests**:
- "Mira lo que hay en la cámara."
- "¿Qué ves por la cámara?"

*Search: camera, cámara, webcam, photo, foto*

---

## Files / Archivos

### File management / Gestión de archivos

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `file_controller`

**Can**:
- Open files / Abrir archivos
- List files / Listar archivos
- Create files and folders / Crear archivos y carpetas
- Delete / Eliminar
- Move / Mover
- Copy / Copiar
- Rename / Renombrar
- Read / Leer
- Write / Escribir
- Search files / Buscar archivos
- Disk usage / Uso de disco

**Side effects**: Yes

**Example requests**:
- "Abre el archivo en mi escritorio."
- "Lista los archivos en Documentos."
- "Busca archivos .pdf."
- "¿Cuánto espacio tengo en disco?"

*Search: file, archivo, folder, carpeta, open, abrir, create, crear, delete, eliminar, borrar, move, mover, copy, copiar, rename, renombrar, read, leer, write, escribir, search, buscar, disk, disco, find, encontrar*

---

### File processing / Procesamiento de archivos

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `file_processor`

**Can**:
- Process and transform files / Procesar y transformar archivos

**Side effects**: Yes

*Search: process, procesar, transform, transformar, convert, convertir*

---

## Browser / Navegador

### Web browsing / Navegación web

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `browser_control`

**Can**:
- Open websites / Abrir páginas web
- Search the web / Buscar en la web
- Click elements / Hacer clic en elementos
- Fill forms / Rellenar formularios
- Take screenshots / Tomar capturas
- Navigate / Navegar
- Support multiple browsers / Soporte multi-navegador

**Side effects**: Yes

**Example requests**:
- "Abre google.com."
- "Busca vuelos a Madrid en Chrome."
- "Abre YouTube en Edge."

*Search: browser, navegador, web, Chrome, Edge, Firefox, Opera, Brave, website, página, sitio, url, link, enlace*

---

## Web / Internet

### Web search / Búsqueda web

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `web_search`

**Can**:
- Search the internet / Buscar en internet
- Compare products / Comparar productos
- Find information / Encontrar información


**Example requests**:
- "Busca las noticias de hoy."
- "Compara iPhone vs Samsung."

*Search: search, buscar, internet, google, web, find, encontrar, compare, comparar, lookup, consultar*

---

### Weather / Clima

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `weather_report`

**Can**:
- Get weather reports / Obtener informes del clima


**Example requests**:
- "¿Qué clima hace en Madrid?"
- "¿Va a llover mañana?"

*Search: weather, clima, rain, lluvia, temperature, temperatura, forecast, pronóstico*

---

### Flight search / Búsqueda de vuelos

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `flight_finder`

**Can**:
- Search flights / Buscar vuelos
- Compare flight options / Comparar vuelos


**Example requests**:
- "Busca vuelos de Madrid a Londres."
- "¿Cuánto cuesta un vuelo a Roma?"

*Search: flight, vuelo, fly, volar, airline, aerolínea, travel, viajar*

---

## Multimedia

### Music and media / Música y medios

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `media_control`

**Can**:
- Play music / Reproducir música
- Pause / Pausar
- Stop / Detener
- Skip tracks / Saltar pistas
- Control volume / Controlar volumen
- Queue songs / Poner en cola

Supports Spotify, Apple Music, YouTube Music, and system media.

**Side effects**: Yes

**Example requests**:
- "Pon Bohemian Rhapsody."
- "Pausa la música."
- "Siguiente canción."

*Search: music, música, Spotify, play, reproducir, pause, pausar, song, canción, album, álbum, playlist, artist, artista, volume, volumen, media, audio*

---

### YouTube

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `youtube_video`

**Can**:
- Play videos / Reproducir videos
- Summarize videos / Resumir videos
- Get video info / Obtener información
- Show trending / Mostrar tendencias

**Side effects**: Yes

**Example requests**:
- "Pon un video de cocina."
- "Resúmeme este video de YouTube."

*Search: YouTube, video, watch, ver, trending, tendencias, summarize, resumir*

---

## Communication / Comunicación

### Messaging / Mensajería

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `send_message`
- `prepare_message_reply`
- `check_messages`

**Can**:
- Send messages / Enviar mensajes
- Read messages / Leer mensajes
- Draft replies / Redactar respuestas
- Search contacts / Buscar contactos

Supports iMessage, WhatsApp, Telegram, Instagram, Discord.

**Side effects**: Yes
**Approval required**: Yes

**Example requests**:
- "Manda un mensaje a Juan por WhatsApp."
- "Lee mis mensajes de Instagram."
- "Escríbele a María."

*Search: message, mensaje, WhatsApp, Telegram, Instagram, Discord, iMessage, send, enviar, read, leer, chat, contact, contacto*

---

### Email / Correo electrónico

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `email_control`

**Can**:
- Connect Gmail / Conectar Gmail
- Read inbox / Leer bandeja
- Search emails / Buscar correos
- Compose email / Redactar correo
- Manage drafts / Gestionar borradores
- Download attachments / Descargar adjuntos

Gmail is the default provider with OAuth authentication.

**Side effects**: Yes
**Approval required**: Yes

**Example requests**:
- "Lee mis correos."
- "Busca emails de Pedro."
- "Escribe un correo a trabajo@empresa.com."

*Search: email, correo, Gmail, inbox, bandeja, draft, borrador, attachment, adjunto, send email, enviar correo*

---

## Reminders / Recordatorios

### One-time reminders / Recordatorios únicos

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `reminder`

**Can**:
- Create reminders / Crear recordatorios
- List reminders / Listar recordatorios
- Cancel reminders / Cancelar recordatorios
- Modify reminders / Modificar

For one-time future events only. Recurring tasks use `lilith_routine`.

**Side effects**: Yes

**Example requests**:
- "Recuérdame comprar leche mañana."
- "Pon un recordatorio en 30 minutos."

*Search: reminder, recordatorio, remind, recordar, alarm, alarma, timer, temporizador, schedule, programar*

---

## Development / Desarrollo

### Code helper / Ayudante de código

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `code_helper`

**Can**:
- Write code / Escribir código
- Edit code / Editar código
- Explain code / Explicar código
- Run code / Ejecutar código
- Debug screen errors / Depurar errores en pantalla

**Side effects**: Yes

**Example requests**:
- "Escribe un script en Python."
- "Explícame este código."
- "Ejecuta mi script."

*Search: code, código, program, programa, script, Python, JavaScript, write, escribir, run, ejecutar, debug, depurar*

---

### Dev agent / Agente de desarrollo

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `dev_agent`

**Can**:
- Build multi-file projects / Construir proyectos
- Git status / diff / branch / commit

**Side effects**: Yes

**Example requests**:
- "Construye un proyecto web."
- "Haz un commit con mensaje 'fix: corregir bug'."

*Search: dev, desarrollo, build, construir, git, commit, branch, project, proyecto*

---

### Multi-step agent tasks / Tareas multi-paso

**Status**: ✅ AVAILABLE
**Authority**: JARVIS
**Agent**: Planner + Executor

**Tools**:
- `agent_task`
- `task_status`

**Can**:
- Execute complex multi-tool tasks / Ejecutar tareas complejas
- Research and save / Investigar y guardar
- Check task progress / Ver progreso de tareas

**Side effects**: Yes

**Example requests**:
- "Investiga sobre IA y guárdalo en un archivo."
- "¿Cómo va mi tarea?"

*Search: task, tarea, agent, agente, multi-step, complex, complejo*

---

### Deep research / Investigación profunda

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `deep_research`

**Can**:
- Multi-query web research / Investigación multi-consulta
- Source-backed reports / Informes con fuentes
- Background or visible research / Investigación en segundo plano o visible

**Side effects**: Yes

**Example requests**:
- "Investiga a fondo sobre energía solar."
- "Haz una investigación profunda sobre IA generativa."

*Search: research, investigación, deep, profundo, study, estudio, report, informe, sources, fuentes*

---

### Presentations / Presentaciones

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `create_presentation`

**Can**:
- Create PowerPoint presentations / Crear presentaciones PowerPoint
- Edit presentations / Editar presentaciones
- Multiple themes and styles / Múltiples temas y estilos

**Side effects**: Yes

**Example requests**:
- "Hazme una presentación sobre marketing digital."
- "Crea un pitch deck para inversores."

*Search: presentation, presentación, PowerPoint, slides, diapositivas, deck, pptx*

---

## Gaming / Juegos

### Game management / Gestión de juegos

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `game_updater`

**Can**:
- Update games / Actualizar juegos
- Install games / Instalar juegos
- List installed games / Listar juegos instalados
- Check download status / Ver estado de descarga
- Schedule updates / Programar actualizaciones

Supports Steam and Epic Games.

**Side effects**: Yes

**Example requests**:
- "Actualiza mis juegos de Steam."
- "Instala GTA V."
- "¿Qué juegos tengo instalados?"

*Search: game, juego, Steam, Epic, update, actualizar, install, instalar, download, descargar*

---

## Memory / Memoria

### Session memory / Memoria de sesión

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `save_memory`
- `local_memory_search`

**Can**:
- Save session notes / Guardar notas de sesión
- Search local memory / Buscar memoria local

Explicit local/session-only operational notes. Not persistent across restarts via LILITH.


**Example requests**:
- "Recuerda que mi reunión es a las 3."
- "¿Qué te dije antes?"

*Search: memory, memoria, remember, recordar, note, nota, save, guardar, session, sesión*

---

### Persistent memory / Memoria persistente

**Status**: ✅ AVAILABLE
**Authority**: LILITH

**Tools**:
- `lilith_memory_search`
- `lilith_memory_store`
- `lilith_memory_delete`

**Can**:
- Store persistent personal facts / Almacenar hechos personales permanentes
- Search long-term memory / Buscar memoria a largo plazo
- Delete memories / Eliminar memorias

Canonical personal memory owned by LILITH. Persists across sessions.


**Example requests**:
- "Recuerda que me gusta el café."
- "Busca qué sabes de mi trabajo."
- "Olvida mi dirección anterior."

*Search: persistent, persistente, long-term, largo plazo, LILITH, personal, fact, hecho, permanent, permanente*

---

## LILITH / Home Assistant

### Home control / Control del hogar

**Status**: ✅ AVAILABLE
**Authority**: LILITH

**Tools**:
- `lilith_home_action`

**Can**:
- Control home devices / Controlar dispositivos del hogar
- Turn on/off lights, switches / Encender/apagar luces, interruptores
- Resolve entities through LILITH / Resolver entidades

**Side effects**: Yes
**Approval required**: Yes

**Example requests**:
- "Enciende la luz del salón."
- "Apaga la lámpara del dormitorio."

*Search: home, hogar, casa, light, luz, switch, interruptor, Home Assistant, smart home, domótica, device, dispositivo, turn on, encender, turn off, apagar*

---

### Routines / Rutinas

**Status**: ✅ AVAILABLE
**Authority**: LILITH

**Tools**:
- `lilith_routine`

**Can**:
- Create recurring routines / Crear rutinas recurrentes
- List routines / Listar rutinas
- Delete routines / Eliminar rutinas

Persistent recurring tasks managed by LILITH. Not one-time reminders.

**Side effects**: Yes
**Physical validation**: ✅ JL-A10 validated

**Example requests**:
- "Enciende la luz todos los días a las 10 de la noche."
- "Lista mis rutinas."
- "Elimina la rutina de la luz."

*Search: routine, rutina, recurring, recurrente, daily, diario, weekly, semanal, automation, automatización, schedule, programar*

---

### Approvals / Aprobaciones

**Status**: ✅ AVAILABLE
**Authority**: LILITH

**Tools**:
- `lilith_request_approval`
- `lilith_resolve_approval`

**Can**:
- Request approval for sensitive actions / Solicitar aprobación
- Resolve pending approvals / Resolver aprobaciones pendientes

**Approval required**: Yes

*Search: approval, aprobación, permission, permiso, authorize, autorizar*

---

### LILITH system / Sistema LILITH

**Status**: ✅ AVAILABLE
**Authority**: LILITH

**Tools**:
- `lilith_health`
- `lilith_runtime_status`
- `lilith_docs_list`
- `lilith_docs_read`
- `lilith_docs_search`
- `lilith_source_list`
- `lilith_source_read`
- `lilith_source_search`
- `lilith_git_status`
- `lilith_command_submit`

**Can**:
- Check LILITH health / Verificar salud de LILITH
- Read LILITH documentation / Leer documentación de LILITH
- Search LILITH source / Buscar en código fuente de LILITH
- Submit LILITH commands / Enviar comandos a LILITH


*Search: LILITH, health, salud, status, estado, docs, documentación, source, código fuente, command, comando*

---

## JARVIS Interface / Interfaz de JARVIS

### UI control / Control de interfaz

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `jarvis_ui_control`
- `graphics_quality`

**Can**:
- Open/close Command Center / Abrir/cerrar Centro de Comando
- Change theme / Cambiar tema
- Change graphics quality / Cambiar calidad gráfica
- Open settings / Abrir configuración
- Compact mode / Modo compacto
- Fullscreen / Pantalla completa
- Show shortcuts / Mostrar atajos

Themes: Arc Reactor, Stealth Red, Vibranium Purple, Nanotech Gold, Platinum.

**Side effects**: Yes

**Example requests**:
- "Cambia el tema a Stealth Red."
- "Abre el centro de comando."
- "Pon la calidad gráfica en alta."

*Search: UI, interfaz, theme, tema, graphics, gráficos, quality, calidad, Command Center, centro de comando, settings, configuración, HUD, fullscreen, pantalla completa*

---

## GREEN Infrastructure / Infraestructura GREEN

### Skills framework / Marco de habilidades

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Can**:
- Define reusable procedures / Definir procedimientos reutilizables
- Validate skill schemas / Validar esquemas de habilidades

Local-only reusable workflows that execute through normal JARVIS authority.


*Search: skill, habilidad, workflow, flujo de trabajo, procedure, procedimiento*

---

### Documentary RAG / Búsqueda documental

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Can**:
- Search JARVIS documentation / Buscar documentación de JARVIS
- Retrieve technical information / Recuperar información técnica
- Source-attributed results / Resultados con atribución de fuente

Local document retrieval for technical documentation. Separate from personal memory.


*Search: RAG, document, documento, documentation, documentación, search docs, buscar docs, technical, técnico, manual*

---

### Capability catalog / Catálogo de capacidades

**Status**: ✅ AVAILABLE
**Authority**: JARVIS

**Tools**:
- `open_capabilities_catalog`

**Can**:
- Show capabilities / Mostrar capacidades
- Refresh catalog / Actualizar catálogo

This document. Auto-generated searchable reference of all JARVIS capabilities.


**Example requests**:
- "Abre tus habilidades."
- "Muéstrame qué puedes hacer."
- "Abre la lista de funciones."
- "Enséñame tus capacidades."

*Search: capabilities, capacidades, catalog, catálogo, functions, funciones, abilities, habilidades, features, características, what can you do, qué puedes hacer*

---

*This document is auto-generated from JARVIS capability metadata.*
*It is not manually maintained — refresh it to see current state.*
