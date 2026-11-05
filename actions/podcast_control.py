"""Podcast search and playback for JARVIS.

Uses the iTunes/Apple Podcast Search API (free, no key required) to discover
podcasts and retrieve RSS feeds. Episodes are streamed or opened via ffplay
(Linux) or the system default media player (Windows/Mac).

Supported actions:
  search   — search for podcasts by name or topic
  episodes — list recent episodes of a podcast (by feed URL or search term)
  play     — play a specific episode URL or the latest from a podcast
  stop     — stop current episode
  status   — what is currently playing
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

_SYSTEM = platform.system()
_LOCK = threading.Lock()
_CURRENT_PROC: Optional[subprocess.Popen] = None
_CURRENT_TITLE: str = ""
_CURRENT_URL: str = ""

_ITUNES_SEARCH = "https://itunes.apple.com/search?media=podcast&entity=podcast&limit=5&term="
_UA = "JARVIS-AURORA/1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 8) -> bytes:
    req = Request(url, headers={"User-Agent": _UA, "Accept-Language": "es,en"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _search_podcasts(query: str) -> list[dict]:
    url = _ITUNES_SEARCH + quote_plus(query)
    data = json.loads(_http_get(url))
    return data.get("results", [])


def _fetch_rss_episodes(feed_url: str, max_ep: int = 5) -> list[dict]:
    xml_bytes = _http_get(feed_url)
    root = ElementTree.fromstring(xml_bytes)
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
    episodes = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        enclosure = item.find("enclosure")
        audio_url = ""
        if enclosure is not None:
            audio_url = enclosure.get("url", "")
        pub_date = item.findtext("pubDate", "")
        duration = item.findtext("itunes:duration", "", ns)
        if title and audio_url:
            episodes.append({
                "title": title,
                "url": audio_url,
                "pub_date": pub_date,
                "duration": duration,
            })
        if len(episodes) >= max_ep:
            break
    return episodes


def _find_ffplay() -> Optional[str]:
    for candidate in ["ffplay", "ffplay.exe"]:
        path = shutil.which(candidate)
        if path:
            return path
    if _SYSTEM == "Windows":
        for base in [r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"]:
            p = Path(base) / "ffplay.exe"
            if p.exists():
                return str(p)
    return None


def _stop_current() -> str:
    global _CURRENT_PROC, _CURRENT_TITLE, _CURRENT_URL
    with _LOCK:
        if _CURRENT_PROC is None and not _CURRENT_URL:
            return ""
        title = _CURRENT_TITLE
        if _CURRENT_PROC is not None:
            try:
                _CURRENT_PROC.terminate()
                _CURRENT_PROC.wait(timeout=3)
            except Exception:
                try:
                    _CURRENT_PROC.kill()
                except Exception:
                    pass
        _CURRENT_PROC = None
        _CURRENT_TITLE = ""
        _CURRENT_URL = ""
        return title


def _play_audio(url: str, title: str) -> str:
    global _CURRENT_PROC, _CURRENT_TITLE, _CURRENT_URL
    _stop_current()

    ffplay = _find_ffplay()
    if ffplay:
        cmd = [ffplay, "-nodisp", "-loglevel", "quiet", "-autoexit", "-i", url]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            with _LOCK:
                _CURRENT_PROC = proc
                _CURRENT_TITLE = title
                _CURRENT_URL = url
            return f"Reproduciendo: {title}"
        except Exception:
            pass

    # Fallback: open in OS default
    try:
        if _SYSTEM == "Windows":
            os.startfile(url)  # type: ignore[attr-defined]
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        with _LOCK:
            _CURRENT_PROC = None
            _CURRENT_TITLE = title
            _CURRENT_URL = url
        return f"Abriendo '{title}' en el reproductor del sistema."
    except Exception as exc:
        return f"No se pudo reproducir '{title}': {exc}"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _action_search(query: str) -> str:
    if not query:
        return "Especifica qué podcast buscar."
    try:
        results = _search_podcasts(query)
    except Exception as exc:
        return f"Error al buscar podcasts: {exc}"

    if not results:
        return f"No encontré podcasts para '{query}'."

    lines = [f"Podcasts encontrados para '{query}':"]
    for r in results[:5]:
        name = r.get("collectionName", "?")
        artist = r.get("artistName", "")
        feed = r.get("feedUrl", "")
        lines.append(f"  • {name}" + (f" — {artist}" if artist else "") + (f" [RSS: {feed}]" if feed else ""))
    return "\n".join(lines)


def _action_episodes(query: str, feed_url: str = "") -> str:
    if not feed_url:
        # Try to find feed via search
        if not query:
            return "Especifica el nombre del podcast o la URL del feed RSS."
        try:
            results = _search_podcasts(query)
        except Exception as exc:
            return f"Error al buscar: {exc}"
        if not results:
            return f"No encontré el podcast '{query}'."
        feed_url = results[0].get("feedUrl", "")
        if not feed_url:
            return f"El podcast '{results[0].get('collectionName', '')}' no tiene feed RSS disponible."

    try:
        episodes = _fetch_rss_episodes(feed_url, max_ep=5)
    except Exception as exc:
        return f"Error al leer el feed RSS: {exc}"

    if not episodes:
        return "No encontré episodios en ese feed."

    lines = [f"Últimos episodios:"]
    for i, ep in enumerate(episodes, 1):
        dur = f" ({ep['duration']})" if ep.get("duration") else ""
        lines.append(f"  {i}. {ep['title']}{dur}")
        lines.append(f"     URL: {ep['url']}")
    return "\n".join(lines)


def _action_play(query: str = "", feed_url: str = "", episode_url: str = "") -> str:
    # Direct episode URL
    if episode_url:
        return _play_audio(episode_url, episode_url)

    # Latest from feed or search
    if not query and not feed_url:
        return "Especifica el nombre del podcast o URL del episodio."

    if not feed_url:
        try:
            results = _search_podcasts(query)
        except Exception as exc:
            return f"Error al buscar: {exc}"
        if not results:
            return f"No encontré el podcast '{query}'."
        feed_url = results[0].get("feedUrl", "")
        podcast_name = results[0].get("collectionName", query)
        if not feed_url:
            return f"El podcast '{podcast_name}' no tiene feed RSS."
    else:
        podcast_name = feed_url

    try:
        episodes = _fetch_rss_episodes(feed_url, max_ep=1)
    except Exception as exc:
        return f"Error al leer el feed: {exc}"

    if not episodes:
        return "No encontré episodios en ese podcast."

    ep = episodes[0]
    return _play_audio(ep["url"], ep["title"])


def _action_stop() -> str:
    title = _stop_current()
    if title:
        return f"Detenido: {title}"
    return "No hay ningún podcast reproduciéndose."


def _action_status() -> str:
    with _LOCK:
        if not _CURRENT_URL:
            return "No hay ningún podcast reproduciéndose."
        alive = _CURRENT_PROC is not None and _CURRENT_PROC.poll() is None
        state = "reproduciendo" if alive else "abierto en reproductor del sistema"
        return f"Podcast {state}: {_CURRENT_TITLE}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def podcast_control(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "search").lower().strip()

    if action == "search":
        return _action_search(params.get("query", "") or params.get("text", ""))

    if action == "episodes":
        return _action_episodes(
            query=params.get("query", "") or params.get("podcast", ""),
            feed_url=params.get("feed_url", "") or params.get("feed", ""),
        )

    if action == "play":
        return _action_play(
            query=params.get("query", "") or params.get("podcast", ""),
            feed_url=params.get("feed_url", "") or params.get("feed", ""),
            episode_url=params.get("episode_url", "") or params.get("url", ""),
        )

    if action == "stop":
        return _action_stop()

    if action == "status":
        return _action_status()

    return (
        f"Acción '{action}' no reconocida. "
        "Acciones: search, episodes, play, stop, status."
    )
