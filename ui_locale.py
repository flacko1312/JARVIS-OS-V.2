"""Capa de localización para la interfaz de AURORA/JARVIS.

Diccionario centralizado de textos visibles en la UI. Todos los
identificadores internos (estados, enums, tool names, protocolos)
permanecen en inglés; solo se traduce lo que el usuario ve.
"""
from __future__ import annotations

# ── Textos estáticos de la interfaz ────────────────────────────────────────

UI_TEXT: dict[str, str] = {
    # Header
    "HOLOGRAPHIC AI CORE": "NÚCLEO HOLOGRÁFICO DE IA",
    "ONLINE": "EN LÍNEA",
    "LISTENING": "ESCUCHANDO",

    # Left panel
    "OVERVIEW": "RESUMEN",
    "System": "Sistema",
    "Agents": "Agentes",
    "TELEMETRY": "TELEMETRÍA",
    "GPU ADAPTER": "ADAPTADOR GPU",
    "LOAD": "CARGA",
    "VRAM": "VRAM",
    "COGNITIVE LOAD": "CARGA COGNITIVA",
    "Detecting...": "Detectando...",

    # Agent grid
    "COGNITIVE NETWORK": "RED COGNITIVA",
    "AGENTS": "AGENTES",
    "LIVE TELEMETRY": "TELEMETRÍA EN VIVO",
    "EVENT LOG": "REGISTRO DE EVENTOS",

    # Agent names (visible labels — internal keys stay English)
    "CORE": "NÚCLEO",
    "RESEARCH": "INVESTIGACIÓN",
    "SECURITY": "SEGURIDAD",
    "AUTOMATION": "AUTOMATIZACIÓN",
    "MEMORY": "MEMORIA",
    "VISION": "VISIÓN",
    "DEV": "DESARROLLO",
    "SYSTEM": "SISTEMA",

    # Agent statuses
    "PRIMARY": "PRIMARIO",
    "ACTIVE": "ACTIVO",
    "IDLE": "INACTIVO",
    "PROCESSING": "PROCESANDO",
    "ANALYZING": "ANALIZANDO",

    # Agent status abbreviations
    "PRIM": "PRIM",
    "ONLN": "ENLN",
    "ACTV": "ACTV",
    "PROC": "PROC",
    "ANLZ": "ANLZ",

    # Agent objectives
    "Primary intelligence framework": "Marco de inteligencia principal",
    "Coordinating sub-systems": "Coordinando subsistemas",
    "Optimizing neural pathways": "Optimizando rutas neuronales",
    "Synchronizing agents": "Sincronizando agentes",
    "Scanning knowledge base": "Escaneando base de conocimiento",
    "Cross-referencing sources": "Contrastando fuentes",
    "Synthesizing findings": "Sintetizando hallazgos",
    "Validating hypotheses": "Validando hipótesis",
    "Monitoring threat vectors": "Supervisando amenazas",
    "Scanning network perimeter": "Escaneando perímetro de red",
    "Validating access tokens": "Validando tokens de acceso",
    "Auditing system logs": "Auditando registros del sistema",
    "Executing task pipeline": "Ejecutando tareas",
    "Scheduling workflows": "Programando flujos de trabajo",
    "Delegating subtasks": "Delegando subtareas",
    "Optimizing execution path": "Optimizando ruta de ejecución",
    "Indexing context graph": "Indexando grafo de contexto",
    "Retrieving episodic memory": "Recuperando memoria episódica",
    "Consolidating knowledge": "Consolidando conocimiento",
    "Pruning stale entries": "Limpiando entradas obsoletas",
    "Processing visual input": "Procesando entrada visual",
    "Analyzing screen state": "Analizando estado de pantalla",
    "Detecting UI elements": "Detectando elementos de la interfaz",
    "Mapping spatial context": "Mapeando contexto espacial",
    "Analyzing code structure": "Analizando estructura de código",
    "Tracing dependencies": "Analizando dependencias",
    "Reviewing logic flow": "Revisando flujo lógico",
    "Generating test cases": "Generando casos de prueba",
    "Monitoring diagnostics": "Monitorizando diagnósticos",
    "Tracking resource usage": "Supervisando recursos",
    "Optimizing memory": "Optimizando memoria",
    "Balancing load distribution": "Balanceando distribución de carga",

    # Activity stream log entries
    "Memory synchronized": "Memoria sincronizada",
    "Threat scan complete": "Escaneo de amenazas completado",
    "Vision detected alignment": "Visión detectó alineación",
    "Workflow optimized": "Flujo de trabajo optimizado",
    "Knowledge base updated": "Base de conocimiento actualizada",
    "Security token refreshed": "Token de seguridad renovado",
    "Core cycle completed": "Ciclo del núcleo completado",
    "Task pipeline flushed": "Pipeline de tareas vaciado",
    "Context graph pruned": "Grafo de contexto podado",
    "Neural pathway calibrated": "Ruta neuronal calibrada",

    # Right panel tabs
    "COMMS": "COMUN.",
    "TASKS": "TAREAS",
    "ASSETS": "RECURSOS",
    "TOOLS": "HERRAM.",
    "INTEL": "INTEL.",
    "FILES": "ARCHIVOS",

    # HUD overlay text
    "STANDBY": "EN ESPERA",
    "THINKING": "PENSANDO",
    "EXECUTING": "EJECUTANDO",
    "SPEAKING": "HABLANDO",
    "MIC OFF": "MICRO APAGADO",
    "ERROR": "ERROR",
    "MODE": "MODO",
    "IN": "ENTR",
    "OUT": "SAL",
    "LAYERS 03  NODES 24": "CAPAS 03  NODOS 24",

    # Command rail
    "COMMAND RAIL": "BARRA DE COMANDOS",
    "LOCAL  /  LISTENING": "LOCAL  /  ESCUCHANDO",
    "MIC  ·  ON": "MICRO  ·  ACTIVO",
    "MIC  ·  MUTED": "MICRO  ·  SILENCIADO",
    "VOICE": "VOZ",
    "NAME": "NOMBRE",
    "THEME": "TEMA",
    "FULLSCREEN": "PANT. COMPLETA",
    "COMPACT": "COMPACTO",
    "SHORTCUTS": "ATAJOS",
    "QUIT": "SALIR",

    # Conversation button
    "▶ INICIAR CONVERSACIÓN": "▶ INICIAR CONVERSACIÓN",
    "■ TERMINAR CONVERSACIÓN": "■ TERMINAR CONVERSACIÓN",

    # Tooltips
    "Toggle microphone (F4)": "Alternar micrófono (F4)",
    "Iniciar o terminar conversación (F8)": "Iniciar o terminar conversación (F8)",
    "Change AURORA voice": "Cambiar voz de AURORA",
    "Change operator name": "Cambiar nombre del operador",
    "Cycle AURORA theme": "Cambiar tema de AURORA",
    "Toggle fullscreen (F11)": "Alternar pantalla completa (F11)",
    "Compact Mode (Ctrl+M)": "Modo compacto (Ctrl+M)",
    "Keyboard Shortcuts (Ctrl+/)": "Atajos de teclado (Ctrl+/)",
    "Quit AURORA": "Cerrar AURORA",
    "AURORA interface by amd.creationz": "Interfaz de AURORA por amd.creationz",
    "Window and settings": "Ventana y ajustes",
    "Close live preview": "Cerrar vista previa en vivo",

    # Utility menu
    "Fullscreen": "Pantalla completa",
    "Settings": "Ajustes",
    "Compact Mode": "Modo compacto",
    "Keyboard Shortcuts": "Atajos de teclado",
    "Close Command Center": "Cerrar centro de comandos",

    # System tray
    "Show AURORA": "Mostrar AURORA",
    "Toggle Mute": "Alternar silencio",
    "Quit AURORA": "Cerrar AURORA",
    "Running in background. Click tray icon to restore.":
        "Ejecutándose en segundo plano. Haz clic en el icono de la bandeja para restaurar.",

    # Setup overlay
    "◈  INITIALISATION REQUIRED": "◈  INICIALIZACIÓN NECESARIA",
    "Configure AURORA before first boot.": "Configura AURORA antes del primer arranque.",
    "GEMINI API KEY": "CLAVE API DE GEMINI",
    "Paste Gemini API key": "Pega la clave API de Gemini",
    "Only a verified Gemini key will be accepted.":
        "Solo se aceptará una clave de Gemini verificada.",
    "☆  Remember API key on this machine":
        "☆  Recordar clave API en este equipo",
    "★  Remember API key on this machine":
        "★  Recordar clave API en este equipo",
    "OPERATING SYSTEM": "SISTEMA OPERATIVO",
    "Auto-detected:": "Detectado automáticamente:",
    "▸  INITIALISE SYSTEMS": "▸  INICIAR SISTEMAS",
    "VERIFYING WITH GEMINI…": "VERIFICANDO CON GEMINI…",
    "Contacting Gemini. The key will not be saved unless verification succeeds.":
        "Contactando con Gemini. La clave no se guardará a menos que la verificación tenga éxito.",
    "Gemini key verified.": "Clave de Gemini verificada.",

    # Identity overlay
    "◈  IDENTITY PROTOCOL": "◈  PROTOCOLO DE IDENTIDAD",
    "AURORA needs to know who it's talking to.":
        "AURORA necesita saber con quién habla.",
    "◈  UPDATE IDENTITY": "◈  ACTUALIZAR IDENTIDAD",
    "ENTER YOUR NAME": "INTRODUCE TU NOMBRE",
    "▸  CONFIRM IDENTITY": "▸  CONFIRMAR IDENTIDAD",
    "Skip — default to Sir": "Omitir — por defecto Sir",
    "Your name is stored locally and never sent to any server.":
        "Tu nombre se almacena localmente y nunca se envía a ningún servidor.",

    # Voice selection overlay
    "◈  VOICE SELECTION": "◈  SELECCIÓN DE VOZ",
    "Choose the voice AURORA will speak with.":
        "Elige la voz con la que AURORA hablará.",
    "▸  CONFIRM VOICE": "▸  CONFIRMAR VOZ",

    # Settings overlay
    "◈  SETTINGS": "◈  AJUSTES",
    "IDENTITY": "IDENTIDAD",
    "GRAPHICS": "GRÁFICOS",
    "◈  YOUR NAME": "◈  TU NOMBRE",
    "▸  UPDATE IDENTITY": "▸  ACTUALIZAR IDENTIDAD",

    # Key tutorial overlay
    "← BACK": "← ATRÁS",
    "▸  SAVE KEY & ACTIVATE": "▸  GUARDAR CLAVE Y ACTIVAR",
    "Paste your API key here…": "Pega tu clave API aquí…",

    # TTS provider overlay
    "▸  ACTIVATE VOICE": "▸  ACTIVAR VOZ",
    "◈  CHANGE VOICE": "◈  CAMBIAR VOZ",

    # Shortcuts overlay
    "◈  KEYBOARD SHORTCUTS": "◈  ATAJOS DE TECLADO",
    "Toggle Microphone Mute": "Alternar silencio del micrófono",
    "Minimize / Restore Window": "Minimizar / Restaurar ventana",
    "Toggle Fullscreen": "Alternar pantalla completa",
    "Show This Help Panel": "Mostrar este panel de ayuda",
    "Toggle Compact Mode": "Alternar modo compacto",
    "Cycle Color Theme": "Cambiar tema de color",
    "Send Command (in input)": "Enviar comando (en la entrada)",
    "Close Overlay / Dismiss": "Cerrar panel / Descartar",
    "Press Esc or Ctrl+/ to close": "Pulsa Esc o Ctrl+/ para cerrar",

    # Chat / input
    "Type a message to AURORA...": "Escribe un mensaje a AURORA...",
    "Give AURORA a command": "Escribe un comando para AURORA",
    "SEND": "ENVIAR",
    "Standing by.": "En espera.",
    "DIALOGUE LINK": "ENLACE DE DIÁLOGO",
    "●  LIVE": "●  EN VIVO",
    "No file loaded — drop or click above":
        "Sin archivo cargado — arrastra o haz clic arriba",
    "Tell AURORA what to do with it": "Dile a AURORA qué hacer con él",

    # Research/presentation progress
    "RUNNING IN THE BACKGROUND  ·  0%": "EJECUTANDO EN SEGUNDO PLANO  ·  0%",
    "Preparing research brief": "Preparando informe de investigación",
    "Queued": "En cola",
    "PRESENTATION": "PRESENTACIÓN",

    # Tool progress
    "EXECUTING...": "EJECUTANDO...",
    "Open Application": "Abrir aplicación",
    "Web Search": "Búsqueda web",
    "Deep Research": "Investigación profunda",
    "Weather Report": "Informe meteorológico",
    "Browser Control": "Control del navegador",
    "File Controller": "Control de archivos",
    "Send Message": "Enviar mensaje",
    "Set Reminder": "Crear recordatorio",
    "Vision Analysis": "Análisis visual",
    "System Settings": "Ajustes del sistema",
    "Desktop Control": "Control del escritorio",
    "Media Control": "Control multimedia",
    "Code Assistant": "Asistente de código",
    "Dev Agent": "Agente de desarrollo",
    "File Processor": "Procesador de archivos",
    "Computer Control": "Control del equipo",
    "Game Updater": "Actualizador de juegos",
    "Flight Finder": "Buscador de vuelos",
    "Tool error": "Error de herramienta",
    "Deep research": "Investigación profunda",
    "Researching": "Investigando",
    "Building presentation": "Creando presentación",
    "Preparing sources": "Preparando fuentes",
    "Collecting sources": "Recopilando fuentes",
    "Synthesizing report": "Sintetizando informe",
    "Finalizing report": "Finalizando informe",

    # Vision preview
    "VISION LINK": "ENLACE DE VISIÓN",
    "SCREEN FEED": "SEÑAL DE PANTALLA",
    "INITIALIZING VISION LINK": "INICIALIZANDO ENLACE DE VISIÓN",
    "LIVE // ANALYZING": "EN VIVO // ANALIZANDO",
    "ANALYSIS COMPLETE": "ANÁLISIS COMPLETADO",
    "VISION LINK UNAVAILABLE": "ENLACE DE VISIÓN NO DISPONIBLE",
    "FEED ERROR": "ERROR DE SEÑAL",
    "CAMERA FEED": "SEÑAL DE CÁMARA",
    "Drop file here  or  Click to Browse": "Arrastra un archivo aquí o haz clic para buscar",
    "Images · Video · Audio · PDF · Docs · Code · Data": "Imágenes · Vídeo · Audio · PDF · Documentos · Código · Datos",
    "Release to load": "Suelta para cargar",

    # Startup sequence
    "SYS: INITIATING SYSTEMS, SIR...": "SYS: INICIANDO SISTEMAS...",
    "SYS: CORE SYSTEMS ONLINE": "SYS: SISTEMAS PRINCIPALES EN LÍNEA",
    "SYS: NEURAL NETWORK ACTIVE  [OK]": "SYS: RED NEURONAL ACTIVA  [OK]",
    "SYS: PARALLAX UI COMPLETE   [OK]": "SYS: INTERFAZ PARALLAX COMPLETADA   [OK]",
    "SYS: VOICE SYSTEM STANDBY  [OK]": "SYS: SISTEMA DE VOZ EN ESPERA  [OK]",
    "SYS: AURORA standby. Press F8 to start a conversation.":
        "SYS: AURORA en espera. Pulsa F8 para iniciar una conversación.",

    # State display translations (for header & rail)
    "MUTED": "SILENCIADO",
    "CONNECTING": "CONECTANDO",
    "RECONNECTING": "RECONECTANDO",
    "STOPPING": "DETENIENDO",

    # Toast messages
    "AURORA is thinking...": "AURORA está pensando...",
    "Processing request...": "Procesando solicitud...",

    # Popup messages
    "RIGHT PANEL INFORMATION": "INFORMACIÓN DEL PANEL DERECHO",
    "Mission Control Panel": "Panel de control de misiones",
    "Chat Status: Active": "Estado del chat: Activo",
    "Chat Status: Inactive": "Estado del chat: Inactivo",
    "Press R again to refresh this information":
        "Pulsa R de nuevo para actualizar esta información",
    "JARVIS: Command Center is open.": "AURORA: El centro de comandos está abierto.",
    "JARVIS: Returning to focus view.": "AURORA: Volviendo a la vista principal.",

    # Log prefixes (visible to user)
    "SYS: Microphone muted.": "SYS: Micrófono silenciado.",
    "SYS: Microphone active.": "SYS: Micrófono activo.",

    # Uptime / session metrics
    "UP": "ACT",
    "PROC": "PROC",
    "SESSION": "SESIÓN",

    # Dynamic button labels
    "NAME": "NOMBRE",
    "NAME  ·  SET": "NOMBRE  ·  FIJADO",

    # Setup overlay additional
    "OPERATING SYSTEM": "SISTEMA OPERATIVO",
    "Auto-detected:": "Detectado automáticamente:",
    "Gemini key verified.": "Clave de Gemini verificada.",

    # JARVIS log messages
    "JARVIS: Command Center is open.": "AURORA: El centro de comandos está abierto.",
    "JARVIS: Returning to focus view.": "AURORA: Volviendo a la vista principal.",

    # AURORA toast
    "AURORA is thinking...": "AURORA está pensando...",
    "Processing request...": "Procesando solicitud...",

    # Right panel popup
    "RIGHT PANEL INFORMATION": "INFORMACIÓN DEL PANEL DERECHO",
    "Mission Control Panel": "Panel de control de misiones",
    "Chat Status: Active": "Estado del chat: Activo",
    "Chat Status: Inactive": "Estado del chat: Inactivo",
    "Press R again to refresh this information":
        "Pulsa R de nuevo para actualizar esta información",

    # Right panel tab names (for popup display)
    "INTEL": "INTEL.",
    "MEMORY": "MEMORIA",

    # Voice selector overlay
    "◈  SELECT VOICE": "◈  SELECCIONAR VOZ",

    # Graphics quality
    "LOW": "BAJO",
    "MEDIUM": "MEDIO",
    "HIGH": "ALTO",
    "graphics quality active": "Calidad gráfica activa",
    "CHANGE VOICE": "CAMBIAR VOZ",
    "e.g. Tony, Mirsab, Alex...": "p. ej. Tony, Mirsab, Alex...",
    "e.g.  Tony,  Mirsab,  Alex …": "p. ej. Tony, Mirsab, Alex…",

    # Startup / key validation log messages
    "ERR: Setup blocked because the Gemini API key was not verified.":
        "ERR: Configuración bloqueada porque la clave API de Gemini no fue verificada.",
    "SYS: Gemini API key saved to OS keychain.":
        "SYS: Clave API de Gemini guardada en el llavero del sistema.",
    "SYS: Gemini API key set for this session (not saved).":
        "SYS: Clave API de Gemini configurada para esta sesión (no guardada).",
    "JARVIS: All systems nominal. How may I assist you today?":
        "AURORA: Todos los sistemas operativos. ¿En qué puedo asistirte hoy?",
    "SYS: LILITH is configured but the integration could not be loaded.":
        "SYS: LILITH está configurada, pero no se pudo cargar la integración.",
    "SYS: AURORA online.": "SYS: AURORA en línea.",
}


# ── Mapa de estados internos → etiqueta visual ────────────────────────────

STATE_DISPLAY: dict[str, str] = {
    "IDLE": "EN ESPERA",
    "STANDBY": "EN ESPERA",
    "LISTENING": "ESCUCHANDO",
    "THINKING": "PENSANDO",
    "EXECUTING": "EJECUTANDO",
    "SPEAKING": "HABLANDO",
    "MUTED": "SILENCIADO",
    "ERROR": "ERROR",
    "CONNECTING": "CONECTANDO",
    "RECONNECTING": "RECONECTANDO",
    "STOPPING": "DETENIENDO",
    "PROCESSING": "PROCESANDO",
    "ONLINE": "EN LÍNEA",
    "OFFLINE": "DESCONECTADO",
}


# ── Mapa de estados abreviados ────────────────────────────────────────────

STATUS_ABBREV: dict[str, str] = {
    "PRIMARY": "PRIM",
    "ONLINE": "ENLN",
    "ACTIVE": "ACTV",
    "IDLE": "INAC",
    "PROCESSING": "PROC",
    "ANALYZING": "ANLZ",
}


# ── Función de traducción con fallback ─────────────────────────────────────

def t(key: str) -> str:
    """Devuelve la traducción al castellano de un texto visible.

    Si no existe traducción, devuelve el texto original (fallback seguro).
    """
    return UI_TEXT.get(key, key)


def state_display(internal_state: str) -> str:
    """Traduce un estado interno a su etiqueta visual en castellano."""
    return STATE_DISPLAY.get(internal_state, internal_state)


def status_abbrev(status: str) -> str:
    """Traduce una abreviatura de estado de agente."""
    return STATUS_ABBREV.get(status, status[:4])
