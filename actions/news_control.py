"""E50 — Spoken news headlines from curated RSS feeds.

Fetches headlines from major Spanish and international news RSS feeds,
presents them as voice-ready summaries. No API key required.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

# ---------------------------------------------------------------------------
# Built-in RSS feeds (curated, no key required)

_BUILTIN_FEEDS: dict[str, tuple[str, str]] = {
    # Spanish national
    "rtve":        ("RTVE Noticias",      "https://www.rtve.es/api/noticias.rss"),
    "elpais":      ("El País",            "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
    "elmundo":     ("El Mundo",           "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml"),
    "elconfidencial": ("El Confidencial", "https://rss.elconfidencial.com/espana/"),
    "20minutos":   ("20 Minutos",         "https://www.20minutos.es/rss/"),
    # International (English)
    "bbc":         ("BBC News",           "http://feeds.bbci.co.uk/news/rss.xml"),
    "reuters":     ("Reuters",            "https://feeds.reuters.com/reuters/topNews"),
    # Technology
    "xataka":      ("Xataka",             "https://feeds.weblogssl.com/xataka2"),
    "hackernews":  ("Hacker News Top",    "https://hnrss.org/frontpage"),
    # Sports
    "marca":       ("Marca",              "https://www.marca.com/rss/portada.xml"),
}

_DEFAULT_FEED = "rtve"
_MAX_HEADLINES = 7


def _http_get(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "JARVIS-AURORA/1.0 (news_control)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_rss(xml_bytes: bytes, max_items: int = _MAX_HEADLINES) -> list[dict]:
    """Parse RSS 2.0 XML and return list of {title, description, link, pubDate}."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
        # Handle namespace-free and namespaced roots
        channel = root.find("channel")
        if channel is None:
            channel = root
        for item in channel.findall("item"):
            if len(items) >= max_items:
                break
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            date_el = item.find("pubDate")
            title = (title_el.text or "").strip() if title_el is not None else ""
            desc = (desc_el.text or "").strip() if desc_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            date = (date_el.text or "").strip() if date_el is not None else ""
            if title:
                items.append({"title": title, "description": desc[:200], "link": link, "pubDate": date})
    except ET.ParseError:
        pass
    return items


def _resolve_feed(source: str) -> Optional[tuple[str, str]]:
    """Return (name, url) for a source key or direct URL."""
    s = source.strip().lower()
    if s in _BUILTIN_FEEDS:
        return _BUILTIN_FEEDS[s]
    # Fuzzy match by name substring
    for key, (name, url) in _BUILTIN_FEEDS.items():
        if s in name.lower() or s in key:
            return name, url
    # Direct URL
    if source.startswith("http"):
        return source, source
    return None


# ---------------------------------------------------------------------------
# Actions


def _action_list_sources() -> str:
    lines = ["Fuentes de noticias disponibles:"]
    for key, (name, _) in _BUILTIN_FEEDS.items():
        lines.append(f"  • {key:16s} — {name}")
    return "\n".join(lines)


def _action_headlines(source: str = "", max_items: int = _MAX_HEADLINES) -> str:
    if not source.strip():
        source = _DEFAULT_FEED
    resolved = _resolve_feed(source)
    if resolved is None:
        return (f"Fuente '{source}' no encontrada. "
                f"Usa: {', '.join(_BUILTIN_FEEDS.keys())} o una URL RSS directa.")
    name, url = resolved
    try:
        raw = _http_get(url)
    except Exception as exc:
        return f"Error obteniendo noticias de '{name}': {exc}"

    items = _parse_rss(raw, max_items=max_items)
    if not items:
        return f"No se encontraron titulares en '{name}'."

    lines = [f"Últimas noticias de {name}:"]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['title']}")
        if item.get("description") and item["description"] != item["title"]:
            # Trim description for voice
            desc = item["description"]
            if len(desc) > 120:
                desc = desc[:117] + "..."
            lines.append(f"   {desc}")
    return "\n".join(lines)


def _action_summary(source: str = "") -> str:
    """Return headlines formatted as a natural spoken summary."""
    if not source.strip():
        source = _DEFAULT_FEED
    resolved = _resolve_feed(source)
    if resolved is None:
        return f"Fuente '{source}' no encontrada."
    name, url = resolved
    try:
        raw = _http_get(url)
    except Exception as exc:
        return f"Error obteniendo noticias de '{name}': {exc}"

    items = _parse_rss(raw, max_items=5)
    if not items:
        return f"No hay noticias disponibles en '{name}' ahora mismo."

    titles = [item["title"] for item in items]
    intro = f"Aquí tienes los titulares de {name}: "
    summary = ". ".join(titles) + "."
    return intro + summary


# ---------------------------------------------------------------------------
# Entry point


def news_control(parameters=None, response=None, player=None, session_memory=None) -> str:
    """NEST 68 E50 — Voice news headlines from curated RSS feeds."""
    if not parameters:
        return _action_summary()

    action = str(parameters.get("action", "summary")).strip().lower()
    source = str(parameters.get("source") or parameters.get("fuente") or "").strip()
    max_items = int(parameters.get("max_items") or parameters.get("count") or _MAX_HEADLINES)

    if action in ("headlines", "noticias", "titulares", "list"):
        return _action_headlines(source=source, max_items=max_items)
    elif action in ("summary", "resumen", "briefing"):
        return _action_summary(source=source)
    elif action in ("sources", "fuentes", "list_sources"):
        return _action_list_sources()
    else:
        return f"Acción '{action}' no reconocida. Usa: headlines, summary, sources."
