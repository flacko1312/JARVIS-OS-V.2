"""Clasificador de intención por reglas (Fase 1 de P5)."""
from __future__ import annotations

import re

from router.models import Domain, RouteResult

_RULES: list[tuple[re.Pattern[str], Domain, str, float]] = [
    # Specific task intents precede generic app/entity words.  Confidence,
    # rather than list order, remains the authoritative winner.
    (re.compile(
        r"\b(arregla|repara|depura|debuggea|modifica)\b.*\b("
        r"aplicaci[oó]n|app|programa|c[oó]digo|proyecto|repositorio|bug|error)\b", re.I),
     Domain.DEVELOPMENT, "development", 0.98),

    (re.compile(
        r"\b(lee|lista|muestra|busca|revisa|escribe|redacta|prepara|env[ií]a|"
        r"responde|contesta|abre)\b.*\b(correo|correos|email|emails|gmail|"
        r"bandeja de entrada|mensaje de correo)\b|"
        r"\b(correo|email)\b.*\b(a|para|de|no le[ií]do|pendiente)\b", re.I),
     Domain.GMAIL, "gmail", 0.94),

    (re.compile(
        r"\b(pon|reproduce|pausa|reanuda|contin[uú]a|para|det[eé]n|salta|"
        r"siguiente|anterior|sube|baja|silencia|mutea)\b.*\b("
        r"m[uú]sica|canci[oó]n|audio|spotify|youtube music|reproducci[oó]n|volumen)\b|"
        r"\b(pon m[uú]sica|pausa la m[uú]sica|siguiente canci[oó]n)\b", re.I),
     Domain.MULTIMEDIA, "multimedia", 0.93),

    (re.compile(
        r"\b(recu[eé]rdame|av[ií]same|notif[ií]came)\b|"
        r"\b(crea|pon|programa|lista|cancela|modifica|cambia)\b.*\b("
        r"recordatorio|recordatorios|aviso|avisos)\b", re.I),
     Domain.REMINDERS, "reminders", 0.94),

    (re.compile(
        r"\b(crea|haz|genera|prepara|edita|modifica|ampl[ií]a|redise[ñn]a)\b.*\b("
        r"presentaci[oó]n|presentaciones|diapositivas|powerpoint|pptx|deck)\b", re.I),
     Domain.PRESENTATIONS, "presentations", 0.94),

    (re.compile(
        r"\b(recuerda|acuérdate|acuerdate|no olvides|guarda en memoria|"
        r"qué sabes de|que sabes de|qué recuerdas|que recuerdas)\b", re.I),
     Domain.MEMORY, "memory", 0.9),

    (re.compile(
        r"\b(luz|bombilla|lámpara|lampara|puerta|sensor|ventilador|"
        r"encien|apag|prend|temperatura de casa|termostato|"
        r"persiana|cortina|calefacc|aire acondicionado)\b", re.I),
     Domain.HOME, "home", 0.9),

    (re.compile(
        r"\b(abre|cierra|minimiza|maximiza|ejecuta|lanza|inicia|"
        r"alt.tab|cambia de ventana)\b.*\b(programa|app|aplicación|aplicacion|"
        r"chrome|firefox|code|vscode|spotify|discord|terminal|explorador|"
        r"notepad|word|excel)\b", re.I),
     Domain.WINDOWS, "windows", 0.9),

    (re.compile(
        r"\b(abre|cierra|minimiza|maximiza|ejecuta|lanza|inicia)\s+"
        r"(chrome|firefox|code|vscode|vs\s*code|spotify|discord|terminal|"
        r"explorador|notepad|word|excel|steam|brave|edge|opera)\b", re.I),
     Domain.WINDOWS, "windows", 0.95),

    (re.compile(
        r"\b(archivo|carpeta|directorio|busca archivo|busca carpeta|"
        r"muestra archivos|lista archivos)\b", re.I),
     Domain.FILES, "files", 0.85),

    (re.compile(
        r"\b(pantalla|qué ves|que ves|lee esto|captura|screenshot|"
        r"qué hay en pantalla|que hay en pantalla|ocr)\b", re.I),
     Domain.VISION, "vision", 0.85),

    (re.compile(
        r"\b(con codex|con claude code|desarrolla|programa esto|"
        r"arregla el (código|codigo|bug|error)|haz un script|"
        r"crea una app)\b", re.I),
     Domain.DEVELOPMENT, "development", 0.85),

    (re.compile(
        r"\b(investiga|con work|con cowork|con claude|documenta esto|"
        r"analiza con|haz una investigación|haz una investigacion)\b", re.I),
     Domain.KNOWLEDGE, "knowledge", 0.8),

    (re.compile(
        r"\b(localmente|sin internet|usa ollama|usar ollama|resumen local|"
        r"analiza localmente|modelo local|ia local|i\.a\. local|"
        r"resp[oó]ndeme usando (?:la )?ia local)\b", re.I),
     Domain.LOCAL_AI, "local_ai", 0.92),

    (re.compile(
        r"\b(busca en google|busca en internet|qué tiempo hace|que tiempo hace|"
        r"noticias|wikipedia|busca online)\b", re.I),
     Domain.WEB, "web", 0.8),

    (re.compile(
        r"\b(hola|buenos días|buenos dias|buenas tardes|buenas noches|"
        r"gracias|cómo estás|como estas|cuéntame|cuentame|chiste|"
        r"quién eres|quien eres|qué puedes hacer|que puedes hacer)\b", re.I),
     Domain.CONVERSATION, "conversation", 0.7),
]


_AMBIGUITY_GAP = 0.1


def classify(text: str) -> RouteResult:
    """Clasifica la intención del usuario en un dominio.

    JL-R005: when two or more distinct domains match within
    ``_AMBIGUITY_GAP`` of the winner, ``params["ambiguous"]`` is set
    so the runtime can choose to ask for clarification.
    """
    matches: list[RouteResult] = []

    for pattern, domain, handler, confidence in _RULES:
        if pattern.search(text):
            matches.append(RouteResult(
                domain=domain,
                handler=handler,
                confidence=confidence,
                params={"raw_input": text},
            ))

    if not matches:
        return RouteResult(
            domain=Domain.CONVERSATION,
            handler="conversation",
            confidence=0.3,
            params={"raw_input": text, "fallback": True},
        )

    matches.sort(key=lambda r: r.confidence, reverse=True)
    best = matches[0]

    rival_domains = [
        m for m in matches[1:]
        if m.domain != best.domain
        and best.confidence - m.confidence <= _AMBIGUITY_GAP
    ]
    if rival_domains:
        best.params["ambiguous"] = True
        best.params["rival_domains"] = [m.domain.value for m in rival_domains]

    return best
