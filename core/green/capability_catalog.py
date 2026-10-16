"""Capability Catalog — generates a searchable Markdown document of JARVIS capabilities.

The catalog is an OUTPUT, not a source of truth. It is rendered from:
- Tool Registry metadata
- Capability definitions
- Agent metadata
- Validation status

The user says "muéstrame qué puedes hacer" and JARVIS generates/refreshes
the Markdown, then opens it in VS Code (preferred) or Notepad (fallback).
"""
from __future__ import annotations

import datetime
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.green.catalog")

_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "JARVIS_CAPABILITIES.md"


# ── Inventory model ─────────────────────────────────────────────────

class ValidationStatus:
    AVAILABLE = "✅ AVAILABLE"
    PENDING_PHYSICAL = "🟡 PENDING PHYSICAL VALIDATION"
    DISABLED = "⛔ DISABLED"
    UNAVAILABLE = "❌ UNAVAILABLE"
    REQUIRES_APPROVAL = "⚠️ REQUIRES APPROVAL"
    DELEGATED = "🔒 DELEGATED TO LILITH"


@dataclass
class CapabilityEntry:
    """A single capability in the inventory."""

    name: str
    description: str = ""
    status: str = ValidationStatus.AVAILABLE
    category: str = ""
    tools: list[str] = field(default_factory=list)
    agent: str | None = None
    authority: str = "JARVIS"
    side_effects: bool = False
    requires_approval: bool = False
    physical_validation: str | None = None
    dependencies: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    can: list[str] = field(default_factory=list)


@dataclass
class CapabilityCategory:
    """A group of related capabilities."""

    name: str
    entries: list[CapabilityEntry] = field(default_factory=list)


@dataclass
class CapabilityInventory:
    """Complete capability inventory."""

    categories: list[CapabilityCategory] = field(default_factory=list)
    total_tools: int = 0
    available_count: int = 0
    disabled_count: int = 0
    pending_validation_count: int = 0
    high_risk_count: int = 0
    lilith_delegated_count: int = 0
    generated_at: str = ""
    commit: str = ""

    def add_category(self, category: CapabilityCategory) -> None:
        self.categories.append(category)

    def compute_summary(self) -> None:
        self.available_count = 0
        self.disabled_count = 0
        self.pending_validation_count = 0
        self.high_risk_count = 0
        self.lilith_delegated_count = 0
        tools_seen: set[str] = set()
        for cat in self.categories:
            for entry in cat.entries:
                tools_seen.update(entry.tools)
                if entry.status == ValidationStatus.AVAILABLE:
                    self.available_count += 1
                elif entry.status == ValidationStatus.DISABLED:
                    self.disabled_count += 1
                elif entry.status == ValidationStatus.PENDING_PHYSICAL:
                    self.pending_validation_count += 1
                if entry.requires_approval:
                    self.high_risk_count += 1
                if entry.authority == "LILITH":
                    self.lilith_delegated_count += 1
        self.total_tools = len(tools_seen)


# ── Markdown renderer ───────────────────────────────────────────────

class CapabilityMarkdownRenderer:
    """Renders a CapabilityInventory to searchable Markdown."""

    def render(self, inventory: CapabilityInventory) -> str:
        lines: list[str] = []
        lines.append("# JARVIS — Capability Catalogue")
        lines.append("")
        lines.append(f"Generated: {inventory.generated_at}")
        if inventory.commit:
            lines.append(f"JARVIS commit: `{inventory.commit}`")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total registered tools**: {inventory.total_tools}")
        lines.append(f"- **Available capabilities**: {inventory.available_count}")
        lines.append(f"- **Disabled**: {inventory.disabled_count}")
        lines.append(f"- **Pending physical validation**: {inventory.pending_validation_count}")
        lines.append(f"- **Require approval**: {inventory.high_risk_count}")
        lines.append(f"- **LILITH delegated**: {inventory.lilith_delegated_count}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for cat in inventory.categories:
            lines.append(f"## {cat.name}")
            lines.append("")
            for entry in cat.entries:
                lines.append(f"### {entry.name}")
                lines.append("")
                lines.append(f"**Status**: {entry.status}")
                lines.append(f"**Authority**: {entry.authority}")
                if entry.agent:
                    lines.append(f"**Agent**: {entry.agent}")
                lines.append("")

                if entry.tools:
                    lines.append("**Tools**:")
                    for tool in entry.tools:
                        lines.append(f"- `{tool}`")
                    lines.append("")

                if entry.can:
                    lines.append("**Can**:")
                    for item in entry.can:
                        lines.append(f"- {item}")
                    lines.append("")

                if entry.description:
                    lines.append(entry.description)
                    lines.append("")

                if entry.side_effects:
                    lines.append("**Side effects**: Yes")
                if entry.requires_approval:
                    lines.append("**Approval required**: Yes")
                if entry.physical_validation:
                    lines.append(f"**Physical validation**: {entry.physical_validation}")
                if entry.dependencies:
                    lines.append(f"**Dependencies**: {', '.join(entry.dependencies)}")

                if entry.examples:
                    lines.append("")
                    lines.append("**Example requests**:")
                    for ex in entry.examples:
                        lines.append(f'- "{ex}"')

                if entry.search_terms:
                    lines.append("")
                    lines.append(f"*Search: {', '.join(entry.search_terms)}*")

                lines.append("")
                lines.append("---")
                lines.append("")

        lines.append("*This document is auto-generated from JARVIS capability metadata.*")
        lines.append("*It is not manually maintained — refresh it to see current state.*")
        lines.append("")
        return "\n".join(lines)


# ── Reference inventory builder ─────────────────────────────────────

def build_inventory() -> CapabilityInventory:
    """Build the capability inventory from real JARVIS architecture metadata."""
    inv = CapabilityInventory()
    inv.generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        if result.returncode == 0:
            inv.commit = result.stdout.strip()
    except Exception:
        pass

    # ── Windows ──
    windows = CapabilityCategory(name="Windows")
    windows.entries.append(CapabilityEntry(
        name="Open applications / Abrir aplicaciones",
        status=ValidationStatus.AVAILABLE,
        tools=["open_app"],
        can=["Open supported Windows applications", "Launch programs by name"],
        examples=["Abre Chrome.", "Abre Spotify.", "Abre la calculadora."],
        search_terms=["open", "abrir", "launch", "lanzar", "app", "aplicación", "programa"],
        side_effects=True,
    ))
    windows.entries.append(CapabilityEntry(
        name="Keyboard control / Control del teclado",
        status=ValidationStatus.AVAILABLE,
        tools=["computer_control", "computer_settings"],
        can=["Type text / Escribir texto", "Press keys / Presionar teclas",
             "Use keyboard shortcuts / Atajos de teclado", "Copy / Copiar", "Paste / Pegar"],
        examples=["Escribe 'Hola mundo'.", "Presiona Ctrl+C.", "Copia esto."],
        search_terms=["keyboard", "teclado", "type", "escribir", "tecla", "key",
                      "copy", "copiar", "paste", "pegar", "shortcut", "atajo", "hotkey"],
        side_effects=True,
        physical_validation="✅ Validated",
    ))
    windows.entries.append(CapabilityEntry(
        name="Mouse control / Control del ratón",
        status=ValidationStatus.AVAILABLE,
        tools=["computer_control"],
        can=["Click / Hacer clic", "Double-click / Doble clic", "Right-click / Clic derecho",
             "Move cursor / Mover cursor", "Scroll / Desplazar"],
        examples=["Haz clic en el botón aceptar.", "Desplázate hacia abajo."],
        search_terms=["mouse", "ratón", "click", "clic", "cursor", "scroll", "desplazar"],
        side_effects=True,
    ))
    windows.entries.append(CapabilityEntry(
        name="Window management / Gestión de ventanas",
        status=ValidationStatus.AVAILABLE,
        tools=["computer_settings", "computer_control"],
        can=["Close windows / Cerrar ventanas", "Focus windows / Enfocar ventanas",
             "Fullscreen / Pantalla completa", "Minimize / Minimizar"],
        examples=["Cierra Spotify.", "Pon Chrome en pantalla completa."],
        search_terms=["window", "ventana", "close", "cerrar", "focus", "enfocar",
                      "fullscreen", "pantalla completa", "minimize", "minimizar"],
        side_effects=True,
        physical_validation="✅ Validated",
    ))
    windows.entries.append(CapabilityEntry(
        name="System settings / Configuración del sistema",
        status=ValidationStatus.AVAILABLE,
        tools=["computer_settings"],
        can=["Adjust volume / Ajustar volumen", "Adjust brightness / Ajustar brillo",
             "Dark mode / Modo oscuro", "WiFi control", "Lock screen / Bloquear pantalla",
             "Restart / Reiniciar", "Shutdown / Apagar"],
        examples=["Sube el volumen.", "Activa el modo oscuro.", "Bloquea la pantalla."],
        search_terms=["volume", "volumen", "brightness", "brillo", "dark mode",
                      "modo oscuro", "wifi", "lock", "bloquear", "restart", "reiniciar",
                      "shutdown", "apagar", "settings", "configuración"],
        side_effects=True,
        requires_approval=True,
    ))
    windows.entries.append(CapabilityEntry(
        name="Date and time / Fecha y hora",
        status=ValidationStatus.AVAILABLE,
        tools=["date_time"],
        can=["Read current date / Leer fecha actual", "Read current time / Leer hora actual"],
        examples=["¿Qué hora es?", "¿Qué día es hoy?"],
        search_terms=["date", "fecha", "time", "hora", "clock", "reloj", "today", "hoy"],
    ))
    windows.entries.append(CapabilityEntry(
        name="Desktop control / Control del escritorio",
        status=ValidationStatus.AVAILABLE,
        tools=["desktop_control"],
        can=["Change wallpaper / Cambiar fondo", "Organize desktop / Organizar escritorio",
             "List desktop items / Listar elementos", "Desktop statistics / Estadísticas"],
        examples=["Cambia el fondo de pantalla.", "Organiza mi escritorio."],
        search_terms=["desktop", "escritorio", "wallpaper", "fondo", "organize", "organizar"],
        side_effects=True,
    ))
    inv.add_category(windows)

    # ── Vision ──
    vision = CapabilityCategory(name="Vision / Visión")
    vision.entries.append(CapabilityEntry(
        name="Screen capture and analysis / Captura y análisis de pantalla",
        status=ValidationStatus.AVAILABLE,
        tools=["screen_process"],
        can=["Capture the current screen / Capturar la pantalla",
             "Analyze visible content / Analizar contenido visible",
             "Help identify visible errors / Identificar errores visibles"],
        examples=["Mira qué error tengo en pantalla.", "Analiza lo que estoy viendo.",
                   "¿Qué se ve en mi pantalla?"],
        search_terms=["screen", "pantalla", "screenshot", "captura", "vision", "visión",
                      "see", "ver", "look", "mirar", "analyze", "analizar"],
        physical_validation="✅ Screen validated; Camera pending",
    ))
    vision.entries.append(CapabilityEntry(
        name="Camera / Cámara",
        status=ValidationStatus.PENDING_PHYSICAL,
        tools=["screen_process"],
        can=["Capture webcam image / Capturar imagen de cámara",
             "Analyze what the camera sees / Analizar lo que ve la cámara"],
        examples=["Mira lo que hay en la cámara.", "¿Qué ves por la cámara?"],
        search_terms=["camera", "cámara", "webcam", "photo", "foto"],
        physical_validation="🟡 Pending physical validation",
    ))
    inv.add_category(vision)

    # ── Files ──
    files = CapabilityCategory(name="Files / Archivos")
    files.entries.append(CapabilityEntry(
        name="File management / Gestión de archivos",
        status=ValidationStatus.AVAILABLE,
        tools=["file_controller"],
        can=["Open files / Abrir archivos", "List files / Listar archivos",
             "Create files and folders / Crear archivos y carpetas",
             "Delete / Eliminar", "Move / Mover", "Copy / Copiar",
             "Rename / Renombrar", "Read / Leer", "Write / Escribir",
             "Search files / Buscar archivos", "Disk usage / Uso de disco"],
        examples=["Abre el archivo en mi escritorio.", "Lista los archivos en Documentos.",
                   "Busca archivos .pdf.", "¿Cuánto espacio tengo en disco?"],
        search_terms=["file", "archivo", "folder", "carpeta", "open", "abrir", "create",
                      "crear", "delete", "eliminar", "borrar", "move", "mover", "copy",
                      "copiar", "rename", "renombrar", "read", "leer", "write", "escribir",
                      "search", "buscar", "disk", "disco", "find", "encontrar"],
        side_effects=True,
    ))
    files.entries.append(CapabilityEntry(
        name="File processing / Procesamiento de archivos",
        status=ValidationStatus.AVAILABLE,
        tools=["file_processor"],
        can=["Process and transform files / Procesar y transformar archivos"],
        search_terms=["process", "procesar", "transform", "transformar", "convert", "convertir"],
        side_effects=True,
    ))
    inv.add_category(files)

    # ── Browser ──
    browser = CapabilityCategory(name="Browser / Navegador")
    browser.entries.append(CapabilityEntry(
        name="Web browsing / Navegación web",
        status=ValidationStatus.AVAILABLE,
        tools=["browser_control"],
        can=["Open websites / Abrir páginas web", "Search the web / Buscar en la web",
             "Click elements / Hacer clic en elementos", "Fill forms / Rellenar formularios",
             "Take screenshots / Tomar capturas", "Navigate / Navegar",
             "Support multiple browsers / Soporte multi-navegador"],
        examples=["Abre google.com.", "Busca vuelos a Madrid en Chrome.",
                   "Abre YouTube en Edge."],
        search_terms=["browser", "navegador", "web", "Chrome", "Edge", "Firefox",
                      "Opera", "Brave", "website", "página", "sitio", "url", "link", "enlace"],
        side_effects=True,
    ))
    inv.add_category(browser)

    # ── Web search ──
    web = CapabilityCategory(name="Web / Internet")
    web.entries.append(CapabilityEntry(
        name="Web search / Búsqueda web",
        status=ValidationStatus.AVAILABLE,
        tools=["web_search"],
        can=["Search the internet / Buscar en internet",
             "Compare products / Comparar productos",
             "Find information / Encontrar información"],
        examples=["Busca las noticias de hoy.", "Compara iPhone vs Samsung."],
        search_terms=["search", "buscar", "internet", "google", "web", "find", "encontrar",
                      "compare", "comparar", "lookup", "consultar"],
    ))
    web.entries.append(CapabilityEntry(
        name="Weather / Clima",
        status=ValidationStatus.AVAILABLE,
        tools=["weather_report"],
        can=["Get weather reports / Obtener informes del clima"],
        examples=["¿Qué clima hace en Madrid?", "¿Va a llover mañana?"],
        search_terms=["weather", "clima", "rain", "lluvia", "temperature", "temperatura",
                      "forecast", "pronóstico"],
    ))
    web.entries.append(CapabilityEntry(
        name="Flight search / Búsqueda de vuelos",
        status=ValidationStatus.AVAILABLE,
        tools=["flight_finder"],
        can=["Search flights / Buscar vuelos", "Compare flight options / Comparar vuelos"],
        examples=["Busca vuelos de Madrid a Londres.", "¿Cuánto cuesta un vuelo a Roma?"],
        search_terms=["flight", "vuelo", "fly", "volar", "airline", "aerolínea", "travel", "viajar"],
    ))
    inv.add_category(web)

    # ── Multimedia ──
    multimedia = CapabilityCategory(name="Multimedia")
    multimedia.entries.append(CapabilityEntry(
        name="Music and media / Música y medios",
        status=ValidationStatus.AVAILABLE,
        tools=["media_control"],
        can=["Play music / Reproducir música", "Pause / Pausar", "Stop / Detener",
             "Skip tracks / Saltar pistas", "Control volume / Controlar volumen",
             "Queue songs / Poner en cola"],
        description="Supports Spotify, Apple Music, YouTube Music, and system media.",
        examples=["Pon Bohemian Rhapsody.", "Pausa la música.", "Siguiente canción."],
        search_terms=["music", "música", "Spotify", "play", "reproducir", "pause", "pausar",
                      "song", "canción", "album", "álbum", "playlist", "artist", "artista",
                      "volume", "volumen", "media", "audio"],
        side_effects=True,
    ))
    multimedia.entries.append(CapabilityEntry(
        name="YouTube",
        status=ValidationStatus.AVAILABLE,
        tools=["youtube_video"],
        can=["Play videos / Reproducir videos", "Summarize videos / Resumir videos",
             "Get video info / Obtener información", "Show trending / Mostrar tendencias"],
        examples=["Pon un video de cocina.", "Resúmeme este video de YouTube."],
        search_terms=["YouTube", "video", "watch", "ver", "trending", "tendencias",
                      "summarize", "resumir"],
        side_effects=True,
    ))
    inv.add_category(multimedia)

    # ── Communication ──
    comms = CapabilityCategory(name="Communication / Comunicación")
    comms.entries.append(CapabilityEntry(
        name="Messaging / Mensajería",
        status=ValidationStatus.AVAILABLE,
        tools=["send_message", "prepare_message_reply", "check_messages"],
        can=["Send messages / Enviar mensajes", "Read messages / Leer mensajes",
             "Draft replies / Redactar respuestas", "Search contacts / Buscar contactos"],
        description="Supports iMessage, WhatsApp, Telegram, Instagram, Discord.",
        examples=["Manda un mensaje a Juan por WhatsApp.",
                   "Lee mis mensajes de Instagram.", "Escríbele a María."],
        search_terms=["message", "mensaje", "WhatsApp", "Telegram", "Instagram", "Discord",
                      "iMessage", "send", "enviar", "read", "leer", "chat", "contact", "contacto"],
        side_effects=True,
        requires_approval=True,
    ))
    comms.entries.append(CapabilityEntry(
        name="Email / Correo electrónico",
        status=ValidationStatus.AVAILABLE,
        tools=["email_control"],
        can=["Connect Gmail / Conectar Gmail", "Read inbox / Leer bandeja",
             "Search emails / Buscar correos", "Compose email / Redactar correo",
             "Manage drafts / Gestionar borradores", "Download attachments / Descargar adjuntos"],
        description="Gmail is the default provider with OAuth authentication.",
        examples=["Lee mis correos.", "Busca emails de Pedro.",
                   "Escribe un correo a trabajo@empresa.com."],
        search_terms=["email", "correo", "Gmail", "inbox", "bandeja", "draft", "borrador",
                      "attachment", "adjunto", "send email", "enviar correo"],
        side_effects=True,
        requires_approval=True,
    ))
    inv.add_category(comms)

    # ── Reminders ──
    reminders = CapabilityCategory(name="Reminders / Recordatorios")
    reminders.entries.append(CapabilityEntry(
        name="One-time reminders / Recordatorios únicos",
        status=ValidationStatus.AVAILABLE,
        tools=["reminder"],
        can=["Create reminders / Crear recordatorios", "List reminders / Listar recordatorios",
             "Cancel reminders / Cancelar recordatorios", "Modify reminders / Modificar"],
        description="For one-time future events only. Recurring tasks use `lilith_routine`.",
        examples=["Recuérdame comprar leche mañana.", "Pon un recordatorio en 30 minutos."],
        search_terms=["reminder", "recordatorio", "remind", "recordar", "alarm", "alarma",
                      "timer", "temporizador", "schedule", "programar"],
        side_effects=True,
    ))
    inv.add_category(reminders)

    # ── Development ──
    dev = CapabilityCategory(name="Development / Desarrollo")
    dev.entries.append(CapabilityEntry(
        name="Code helper / Ayudante de código",
        status=ValidationStatus.AVAILABLE,
        tools=["code_helper"],
        can=["Write code / Escribir código", "Edit code / Editar código",
             "Explain code / Explicar código", "Run code / Ejecutar código",
             "Debug screen errors / Depurar errores en pantalla"],
        examples=["Escribe un script en Python.", "Explícame este código.",
                   "Ejecuta mi script."],
        search_terms=["code", "código", "program", "programa", "script", "Python",
                      "JavaScript", "write", "escribir", "run", "ejecutar", "debug", "depurar"],
        side_effects=True,
    ))
    dev.entries.append(CapabilityEntry(
        name="Dev agent / Agente de desarrollo",
        status=ValidationStatus.AVAILABLE,
        tools=["dev_agent"],
        can=["Build multi-file projects / Construir proyectos",
             "Git status / diff / branch / commit"],
        examples=["Construye un proyecto web.", "Haz un commit con mensaje 'fix: corregir bug'."],
        search_terms=["dev", "desarrollo", "build", "construir", "git", "commit", "branch",
                      "project", "proyecto"],
        side_effects=True,
    ))
    dev.entries.append(CapabilityEntry(
        name="Multi-step agent tasks / Tareas multi-paso",
        status=ValidationStatus.AVAILABLE,
        tools=["agent_task", "task_status"],
        agent="Planner + Executor",
        can=["Execute complex multi-tool tasks / Ejecutar tareas complejas",
             "Research and save / Investigar y guardar",
             "Check task progress / Ver progreso de tareas"],
        examples=["Investiga sobre IA y guárdalo en un archivo.",
                   "¿Cómo va mi tarea?"],
        search_terms=["task", "tarea", "agent", "agente", "multi-step", "complex", "complejo"],
        side_effects=True,
    ))
    dev.entries.append(CapabilityEntry(
        name="Deep research / Investigación profunda",
        status=ValidationStatus.AVAILABLE,
        tools=["deep_research"],
        can=["Multi-query web research / Investigación multi-consulta",
             "Source-backed reports / Informes con fuentes",
             "Background or visible research / Investigación en segundo plano o visible"],
        examples=["Investiga a fondo sobre energía solar.",
                   "Haz una investigación profunda sobre IA generativa."],
        search_terms=["research", "investigación", "deep", "profundo", "study", "estudio",
                      "report", "informe", "sources", "fuentes"],
        side_effects=True,
    ))
    dev.entries.append(CapabilityEntry(
        name="Presentations / Presentaciones",
        status=ValidationStatus.AVAILABLE,
        tools=["create_presentation"],
        can=["Create PowerPoint presentations / Crear presentaciones PowerPoint",
             "Edit presentations / Editar presentaciones",
             "Multiple themes and styles / Múltiples temas y estilos"],
        examples=["Hazme una presentación sobre marketing digital.",
                   "Crea un pitch deck para inversores."],
        search_terms=["presentation", "presentación", "PowerPoint", "slides", "diapositivas",
                      "deck", "pptx"],
        side_effects=True,
    ))
    inv.add_category(dev)

    # ── Games ──
    games = CapabilityCategory(name="Gaming / Juegos")
    games.entries.append(CapabilityEntry(
        name="Game management / Gestión de juegos",
        status=ValidationStatus.AVAILABLE,
        tools=["game_updater"],
        can=["Update games / Actualizar juegos", "Install games / Instalar juegos",
             "List installed games / Listar juegos instalados",
             "Check download status / Ver estado de descarga",
             "Schedule updates / Programar actualizaciones"],
        description="Supports Steam and Epic Games.",
        examples=["Actualiza mis juegos de Steam.", "Instala GTA V.",
                   "¿Qué juegos tengo instalados?"],
        search_terms=["game", "juego", "Steam", "Epic", "update", "actualizar",
                      "install", "instalar", "download", "descargar"],
        side_effects=True,
    ))
    inv.add_category(games)

    # ── Memory ──
    memory = CapabilityCategory(name="Memory / Memoria")
    memory.entries.append(CapabilityEntry(
        name="Session memory / Memoria de sesión",
        status=ValidationStatus.AVAILABLE,
        authority="JARVIS",
        tools=["save_memory", "local_memory_search"],
        can=["Save session notes / Guardar notas de sesión",
             "Search local memory / Buscar memoria local"],
        description="Explicit local/session-only operational notes. Not persistent across restarts via LILITH.",
        examples=["Recuerda que mi reunión es a las 3.", "¿Qué te dije antes?"],
        search_terms=["memory", "memoria", "remember", "recordar", "note", "nota",
                      "save", "guardar", "session", "sesión"],
    ))
    memory.entries.append(CapabilityEntry(
        name="Persistent memory / Memoria persistente",
        status=ValidationStatus.AVAILABLE,
        authority="LILITH",
        tools=["lilith_memory_search", "lilith_memory_store", "lilith_memory_delete"],
        can=["Store persistent personal facts / Almacenar hechos personales permanentes",
             "Search long-term memory / Buscar memoria a largo plazo",
             "Delete memories / Eliminar memorias"],
        description="Canonical personal memory owned by LILITH. Persists across sessions.",
        examples=["Recuerda que me gusta el café.", "Busca qué sabes de mi trabajo.",
                   "Olvida mi dirección anterior."],
        search_terms=["persistent", "persistente", "long-term", "largo plazo", "LILITH",
                      "personal", "fact", "hecho", "permanent", "permanente"],
    ))
    inv.add_category(memory)

    # ── LILITH / Home ──
    lilith = CapabilityCategory(name="LILITH / Home Assistant")
    lilith.entries.append(CapabilityEntry(
        name="Home control / Control del hogar",
        status=ValidationStatus.AVAILABLE,
        authority="LILITH",
        tools=["lilith_home_action"],
        can=["Control home devices / Controlar dispositivos del hogar",
             "Turn on/off lights, switches / Encender/apagar luces, interruptores",
             "Resolve entities through LILITH / Resolver entidades"],
        examples=["Enciende la luz del salón.", "Apaga la lámpara del dormitorio."],
        search_terms=["home", "hogar", "casa", "light", "luz", "switch", "interruptor",
                      "Home Assistant", "smart home", "domótica", "device", "dispositivo",
                      "turn on", "encender", "turn off", "apagar"],
        side_effects=True,
        requires_approval=True,
    ))
    lilith.entries.append(CapabilityEntry(
        name="Routines / Rutinas",
        status=ValidationStatus.AVAILABLE,
        authority="LILITH",
        tools=["lilith_routine"],
        can=["Create recurring routines / Crear rutinas recurrentes",
             "List routines / Listar rutinas", "Delete routines / Eliminar rutinas"],
        description="Persistent recurring tasks managed by LILITH. Not one-time reminders.",
        examples=["Enciende la luz todos los días a las 10 de la noche.",
                   "Lista mis rutinas.", "Elimina la rutina de la luz."],
        search_terms=["routine", "rutina", "recurring", "recurrente", "daily", "diario",
                      "weekly", "semanal", "automation", "automatización", "schedule", "programar"],
        side_effects=True,
        physical_validation="✅ JL-A10 validated",
    ))
    lilith.entries.append(CapabilityEntry(
        name="Approvals / Aprobaciones",
        status=ValidationStatus.AVAILABLE,
        authority="LILITH",
        tools=["lilith_request_approval", "lilith_resolve_approval"],
        can=["Request approval for sensitive actions / Solicitar aprobación",
             "Resolve pending approvals / Resolver aprobaciones pendientes"],
        search_terms=["approval", "aprobación", "permission", "permiso", "authorize", "autorizar"],
        requires_approval=True,
    ))
    lilith.entries.append(CapabilityEntry(
        name="LILITH system / Sistema LILITH",
        status=ValidationStatus.AVAILABLE,
        authority="LILITH",
        tools=["lilith_health", "lilith_runtime_status", "lilith_docs_list",
               "lilith_docs_read", "lilith_docs_search", "lilith_source_list",
               "lilith_source_read", "lilith_source_search", "lilith_git_status",
               "lilith_command_submit"],
        can=["Check LILITH health / Verificar salud de LILITH",
             "Read LILITH documentation / Leer documentación de LILITH",
             "Search LILITH source / Buscar en código fuente de LILITH",
             "Submit LILITH commands / Enviar comandos a LILITH"],
        search_terms=["LILITH", "health", "salud", "status", "estado", "docs", "documentación",
                      "source", "código fuente", "command", "comando"],
    ))
    inv.add_category(lilith)

    # ── JARVIS UI ──
    ui = CapabilityCategory(name="JARVIS Interface / Interfaz de JARVIS")
    ui.entries.append(CapabilityEntry(
        name="UI control / Control de interfaz",
        status=ValidationStatus.AVAILABLE,
        tools=["jarvis_ui_control", "graphics_quality"],
        can=["Open/close Command Center / Abrir/cerrar Centro de Comando",
             "Change theme / Cambiar tema", "Change graphics quality / Cambiar calidad gráfica",
             "Open settings / Abrir configuración", "Compact mode / Modo compacto",
             "Fullscreen / Pantalla completa", "Show shortcuts / Mostrar atajos"],
        description="Themes: Arc Reactor, Stealth Red, Vibranium Purple, Nanotech Gold, Platinum.",
        examples=["Cambia el tema a Stealth Red.", "Abre el centro de comando.",
                   "Pon la calidad gráfica en alta."],
        search_terms=["UI", "interfaz", "theme", "tema", "graphics", "gráficos", "quality",
                      "calidad", "Command Center", "centro de comando", "settings", "configuración",
                      "HUD", "fullscreen", "pantalla completa"],
        side_effects=True,
    ))
    inv.add_category(ui)

    # ── GREEN Foundation ──
    green = CapabilityCategory(name="GREEN Infrastructure / Infraestructura GREEN")
    green.entries.append(CapabilityEntry(
        name="Skills framework / Marco de habilidades",
        status=ValidationStatus.AVAILABLE,
        description="Local-only reusable workflows that execute through normal JARVIS authority.",
        can=["Define reusable procedures / Definir procedimientos reutilizables",
             "Validate skill schemas / Validar esquemas de habilidades"],
        search_terms=["skill", "habilidad", "workflow", "flujo de trabajo", "procedure", "procedimiento"],
    ))
    green.entries.append(CapabilityEntry(
        name="Documentary RAG / Búsqueda documental",
        status=ValidationStatus.AVAILABLE,
        description="Local document retrieval for technical documentation. Separate from personal memory.",
        can=["Search JARVIS documentation / Buscar documentación de JARVIS",
             "Retrieve technical information / Recuperar información técnica",
             "Source-attributed results / Resultados con atribución de fuente"],
        search_terms=["RAG", "document", "documento", "documentation", "documentación",
                      "search docs", "buscar docs", "technical", "técnico", "manual"],
    ))
    green.entries.append(CapabilityEntry(
        name="Capability catalog / Catálogo de capacidades",
        status=ValidationStatus.AVAILABLE,
        tools=["open_capabilities_catalog"],
        description="This document. Auto-generated searchable reference of all JARVIS capabilities.",
        can=["Show capabilities / Mostrar capacidades",
             "Refresh catalog / Actualizar catálogo"],
        examples=["Abre tus habilidades.", "Muéstrame qué puedes hacer.",
                   "Abre la lista de funciones.", "Enséñame tus capacidades."],
        search_terms=["capabilities", "capacidades", "catalog", "catálogo", "functions",
                      "funciones", "abilities", "habilidades", "features", "características",
                      "what can you do", "qué puedes hacer"],
    ))
    inv.add_category(green)

    inv.compute_summary()
    return inv


# ── File operations ─────────────────────────────────────────────────

def render_markdown(inventory: CapabilityInventory | None = None) -> str:
    """Build inventory and render to Markdown string."""
    if inventory is None:
        inventory = build_inventory()
    renderer = CapabilityMarkdownRenderer()
    return renderer.render(inventory)


def write_catalog(path: Path | None = None) -> Path:
    """Generate and write the capability catalog. Returns the path."""
    target = path or _CATALOG_PATH
    content = render_markdown()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    logger.info("capability catalog written to %s", target)
    return target


def refresh_catalog() -> Path:
    """Alias for write_catalog — regenerates from current metadata."""
    return write_catalog()


def open_catalog(path: Path | None = None) -> str:
    """Open the catalog file, preferring VS Code, falling back to Notepad.

    Returns a human-readable status message.
    """
    target = path or _CATALOG_PATH
    if not target.exists():
        write_catalog(target)

    # Try VS Code first
    vscode = shutil.which("code")
    if vscode:
        try:
            subprocess.Popen([vscode, str(target)])
            return f"Catalog opened in VS Code: {target}"
        except OSError:
            pass

    # Fallback to Notepad on Windows
    notepad = shutil.which("notepad")
    if notepad:
        try:
            subprocess.Popen([notepad, str(target)])
            return f"Catalog opened in Notepad: {target}"
        except OSError:
            pass

    # Final fallback: os.startfile on Windows
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return f"Catalog opened with default handler: {target}"
    except (OSError, AttributeError):
        return f"Catalog written to {target} — could not open automatically."
